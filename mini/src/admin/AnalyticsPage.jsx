import { useEffect, useMemo, useState } from 'react';
import { adminApi } from './adminApi.js';
import DoctorStatsModal from './DoctorStatsModal.jsx';

const MONTHS_SHORT = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];

function pad(n) { return n < 10 ? '0' + n : '' + n; }

function isoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function humanDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]} ${y}`;
}

const PRESETS = [
  { id: 'today', label: 'Сегодня' },
  { id: '7',     label: '7 дней' },
  { id: '30',    label: '30 дней' },
  { id: '90',    label: '90 дней' },
  { id: '365',   label: 'Год' },
  { id: 'custom', label: 'Свой период' },
];

const MONTHLY_PRESETS = [
  { id: 'this_month', label: 'Этот месяц' },
  { id: 'prev_month', label: 'Прошлый месяц' },
  { id: 'this_year',  label: 'Этот год' },
];

function presetRange(id) {
  const today = new Date();
  if (id === 'today') return { from: isoDate(today), to: isoDate(today) };
  if (id === '7')     return { from: isoDate(addDays(today, -6)), to: isoDate(today) };
  if (id === '30')    return { from: isoDate(addDays(today, -29)), to: isoDate(today) };
  if (id === '90')    return { from: isoDate(addDays(today, -89)), to: isoDate(today) };
  if (id === '365')   return { from: isoDate(addDays(today, -364)), to: isoDate(today) };
  if (id === 'this_month') {
    return {
      from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
      to: isoDate(today),
    };
  }
  if (id === 'prev_month') {
    const firstPrev = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const lastPrev = new Date(today.getFullYear(), today.getMonth(), 0);
    return { from: isoDate(firstPrev), to: isoDate(lastPrev) };
  }
  if (id === 'this_year') {
    return {
      from: isoDate(new Date(today.getFullYear(), 0, 1)),
      to: isoDate(today),
    };
  }
  return null;
}

function fmtMoney(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
}

function fmtPct(n) {
  if (n == null) return '—';
  return n.toFixed(1) + '%';
}

function DeltaBadge({ value, suffix = '%', invert = false }) {
  if (value == null) return null;
  const positive = value > 0;
  const negative = value < 0;
  // invert=true для no-show и подобных — рост плохой
  const good = invert ? negative : positive;
  const bad = invert ? positive : negative;
  let color = 'var(--text-muted)';
  if (good) color = '#1f5f36';
  else if (bad) color = '#a83c3c';
  const arrow = positive ? '↑' : (negative ? '↓' : '→');
  return (
    <span style={{
      fontSize: 12, color, fontWeight: 600,
    }}>
      {arrow}{Math.abs(value).toFixed(1)}{suffix}
    </span>
  );
}

function MetricCard({ label, value, delta, invert = false, hint }) {
  return (
    <div className="dash-card" style={{ textAlign: 'left', padding: 12 }}>
      <div className="dash-card-label" style={{ marginBottom: 6 }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
        <div className="dash-card-value" style={{ fontSize: 22 }}>{value}</div>
        {delta !== undefined && <DeltaBadge value={delta} invert={invert} />}
      </div>
      {hint && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function BarChart({ items, valueKey = 'count', labelKey = 'name', valueSuffix = '', showRevenue = false, onItemClick = null }) {
  if (!items.length) {
    return <div className="create-req-empty">Нет данных за период.</div>;
  }
  const max = Math.max(...items.map((i) => i[valueKey]));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map((it, i) => (
        <div
          key={i}
          onClick={onItemClick ? () => onItemClick(it) : undefined}
          style={{ cursor: onItemClick ? 'pointer' : 'default' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 2 }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>
              {i + 1}. {it[labelKey]}
              {it.avg_rating > 0 && (
                <span style={{ color: '#8b5a00', marginLeft: 6, fontWeight: 500 }}>
                  ⭐ {it.avg_rating.toFixed(1)}
                </span>
              )}
            </span>
            <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap', marginLeft: 8 }}>
              <b style={{ color: 'var(--text)' }}>{it[valueKey]}</b>{valueSuffix}
              {showRevenue && it.revenue > 0 && ` · ${fmtMoney(it.revenue)}`}
            </span>
          </div>
          <div style={{
            height: 8, background: 'var(--bg)', borderRadius: 4, overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', width: `${max > 0 ? (it[valueKey] / max * 100) : 0}%`,
              background: 'var(--primary)', borderRadius: 4, transition: 'width 0.3s',
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsPage({ orgId }) {
  const [preset, setPreset] = useState('30');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [branchId, setBranchId] = useState('');
  const [doctorId, setDoctorId] = useState('');

  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [data, setData] = useState(null);

  const [branches, setBranches] = useState([]);
  const [doctors, setDoctors] = useState([]);

  const [exportOpen, setExportOpen] = useState(false);
  const [exportBusy, setExportBusy] = useState(null);
  const [exportMsg, setExportMsg] = useState('');

  const [doctorStatsModal, setDoctorStatsModal] = useState(null);

  const range = useMemo(() => {
    if (preset === 'custom') return { from: customFrom, to: customTo };
    return presetRange(preset);
  }, [preset, customFrom, customTo]);

  useEffect(() => {
    Promise.all([
      adminApi.getBranches(orgId).catch(() => ({ branches: [] })),
      adminApi.getDoctorsByOrg(orgId).catch(() => ({ doctors: [] })),
    ]).then(([b, d]) => {
      setBranches(b.branches || []);
      setDoctors(d.doctors || []);
    });
  }, [orgId]);

  useEffect(() => {
    if (!range || !range.from || !range.to) return;
    setStep('loading');
    setError('');
    adminApi.getAnalyticsSummary(orgId, {
      date_from: range.from,
      date_to: range.to,
      branch_id: branchId || undefined,
      doctor_id: doctorId || undefined,
    })
      .then((d) => { setData(d); setStep('ready'); })
      .catch((e) => { setError(e.message); setStep('error'); });
  }, [orgId, range, branchId, doctorId]);

  function choosePreset(id) {
    setPreset(id);
    if (id === 'custom' && !customFrom && !customTo) {
      const today = new Date();
      setCustomFrom(isoDate(addDays(today, -29)));
      setCustomTo(isoDate(today));
    }
  }

  async function handleExport(format) {
    if (!range || !range.from || !range.to) return;
    setExportBusy(format);
    setExportMsg('');
    try {
      const r = await adminApi.exportAnalytics(orgId, {
        date_from: range.from,
        date_to: range.to,
        format,
        branch_id: branchId || undefined,
        doctor_id: doctorId || undefined,
      });
      if (r && r.ok) {
        if (r.sent_to_chat) {
          setExportMsg('✅ Файл отправлен в чат MAX.');
        } else {
          setExportMsg(`⚠️ Отправка в чат не удалась. Скачать: ${r.full_url || r.url}`);
        }
      } else {
        setExportMsg('❌ Не удалось сформировать файл');
      }
    } catch (e) {
      setExportMsg('❌ ' + e.message);
    } finally {
      setExportBusy(null);
    }
  }

  return (
    <div>
      <div className="filters-scroll" style={{ marginBottom: 8 }}>
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={'filter-btn' + (preset === p.id ? ' active' : '')}
            onClick={() => choosePreset(p.id)}
          >
            {p.label}
          </button>
        ))}
        {MONTHLY_PRESETS.map((p) => (
          <button
            key={p.id}
            className={'filter-btn' + (preset === p.id ? ' active' : '')}
            onClick={() => choosePreset(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {preset === 'custom' && (
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">С</label>
            <input
              className="form-input"
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
            />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">По</label>
            <input
              className="form-input"
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="sched-filters" style={{ marginBottom: 12 }}>
        {branches.length > 1 && (
          <select
            className="org-select"
            value={branchId}
            onChange={(e) => setBranchId(e.target.value)}
          >
            <option value="">Все филиалы</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}{b.is_primary ? ' 🏠' : ''}
              </option>
            ))}
          </select>
        )}
        {doctors.length > 0 && (
          <select
            className="org-select"
            value={doctorId}
            onChange={(e) => setDoctorId(e.target.value)}
          >
            <option value="">Все специалисты</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        )}
      </div>

      {step === 'loading' && <div className="loading">Загрузка…</div>}
      {step === 'error' && <div className="error-box">Ошибка: {error}</div>}

      {step === 'ready' && data && (
        <>
          <div style={{
            fontSize: 12, color: 'var(--text-muted)', marginBottom: 8,
          }}>
            {humanDate(data.period.date_from)} — {humanDate(data.period.date_to)}
            {' '}({data.period.days} дн.)
            {' · '}сравнение с {humanDate(data.previous_period.date_from)} — {humanDate(data.previous_period.date_to)}
          </div>

          <div className="dash-cards">
            <MetricCard
              label="💰 Выручка"
              value={fmtMoney(data.current.revenue)}
              delta={data.delta.revenue_pct}
            />
            <MetricCard
              label="✅ Пришли"
              value={data.current.done}
              delta={data.delta.done_pct}
            />
            <MetricCard
              label="📋 Всего записей"
              value={data.current.total}
              delta={data.delta.total_pct}
            />
            <MetricCard
              label="💵 Средний чек"
              value={fmtMoney(data.current.avg_check_per_visit ?? data.current.avg_check)}
              delta={data.delta.avg_check_pct}
            />
            <MetricCard
              label="🚫 Неявки"
              value={fmtPct(data.current.no_show_pct)}
              delta={data.delta.no_show_pct_pp}
              invert={true}
            />
            <MetricCard
              label="📊 Загрузка"
              value={fmtPct(data.current.load_pct)}
              delta={data.delta.load_pct_pp}
              hint={`${data.current.booked_slots} из ${data.current.total_slots} слотов`}
            />
          </div>

          <div className="dash-cards" style={{ marginTop: 8 }}>
            <MetricCard
              label="👥 Клиентов"
              value={data.current.unique_clients}
            />
            <MetricCard
              label="🆕 Новых"
              value={data.current.new_clients}
              delta={data.delta.new_clients_pct}
            />
            <MetricCard
              label="🔁 Постоянных"
              value={data.current.returning_clients}
            />
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h2 className="card-title">🏆 Топ услуг (по визитам)</h2>
            <BarChart items={data.top_services} valueKey="count" labelKey="name" showRevenue />
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 className="card-title">👤 Топ специалистов (по визитам)</h2>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              Нажмите на специалиста, чтобы увидеть подробные метрики.
            </div>
            <BarChart
              items={data.top_doctors}
              valueKey="count"
              labelKey="name"
              showRevenue
              onItemClick={(it) => {
                if (!it.doctor_id) return;
                setDoctorStatsModal({ id: it.doctor_id, name: it.name });
              }}
            />
          </div>

          <div style={{ marginTop: 16 }}>
            <button
              className="btn-generate"
              onClick={() => setExportOpen(true)}
            >
              📥 Экспорт аналитики
            </button>
          </div>

          {exportOpen && (
            <div
              className="modal-backdrop"
              onClick={() => !exportBusy && setExportOpen(false)}
              style={{ zIndex: 200 }}
            >
              <div
                className="modal"
                onClick={(e) => e.stopPropagation()}
                style={{ maxWidth: 460 }}
              >
                <h2 className="card-title">📥 Экспорт аналитики</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
                  {humanDate(range.from)} — {humanDate(range.to)}
                </p>

                <div className="actions" style={{ flexDirection: 'column', gap: 8, marginTop: 12 }}>
                  <button
                    type="button"
                    className="btn-action confirm"
                    onClick={() => handleExport('xlsx')}
                    disabled={!!exportBusy}
                  >
                    {exportBusy === 'xlsx' ? 'Отправка…' : '📊 XLSX (с графиком по дням)'}
                  </button>
                  <button
                    type="button"
                    className="btn-action confirm"
                    onClick={() => handleExport('pdf')}
                    disabled={!!exportBusy}
                  >
                    {exportBusy === 'pdf' ? 'Отправка…' : '📕 PDF (для печати)'}
                  </button>
                  <button
                    type="button"
                    className="btn-action confirm"
                    onClick={() => handleExport('csv')}
                    disabled={!!exportBusy}
                  >
                    {exportBusy === 'csv' ? 'Отправка…' : '📄 CSV (Excel, Google Sheets)'}
                  </button>
                  <button
                    type="button"
                    className="btn-action reject"
                    onClick={() => setExportOpen(false)}
                    disabled={!!exportBusy}
                  >
                    Закрыть
                  </button>
                </div>

                {exportMsg && (
                  <div style={{
                    marginTop: 12,
                    fontSize: 13,
                    color: exportMsg.startsWith('✅') ? 'var(--accent)'
                         : exportMsg.startsWith('⚠️') ? '#8b5a00' : 'var(--danger)',
                    wordBreak: 'break-all',
                  }}>
                    {exportMsg}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {doctorStatsModal && range && range.from && range.to && (
        <DoctorStatsModal
          orgId={orgId}
          doctorId={doctorStatsModal.id}
          doctorName={doctorStatsModal.name}
          dateFrom={range.from}
          dateTo={range.to}
          onClose={() => setDoctorStatsModal(null)}
        />
      )}
    </div>
  );
}