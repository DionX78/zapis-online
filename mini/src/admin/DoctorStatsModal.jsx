import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

function fmtMoney(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
}

function fmtPct(n) {
  if (n == null) return '—';
  return n.toFixed(1) + '%';
}

function MetricCard({ label, value, hint }) {
  return (
    <div className="dash-card" style={{ textAlign: 'left', padding: 12 }}>
      <div className="dash-card-label" style={{ marginBottom: 6 }}>{label}</div>
      <div className="dash-card-value" style={{ fontSize: 22 }}>{value}</div>
      {hint && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

export default function DoctorStatsModal({ orgId, doctorId, doctorName, dateFrom, dateTo, onClose }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [data, setData] = useState(null);

  useEffect(() => {
    setStep('loading');
    setError('');
    adminApi.getAnalyticsDoctor(orgId, doctorId, { date_from: dateFrom, date_to: dateTo })
      .then((d) => { setData(d); setStep('ready'); })
      .catch((e) => { setError(e.message); setStep('error'); });
  }, [orgId, doctorId, dateFrom, dateTo]);

  const maxService = data && data.top_services.length > 0
    ? Math.max(...data.top_services.map((s) => s.count))
    : 0;

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 200 }}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <h2 className="card-title">👤 {doctorName}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
          {dateFrom} — {dateTo}
        </p>

        {step === 'loading' && <div className="loading">Загрузка…</div>}
        {step === 'error' && <div className="error-box">Ошибка: {error}</div>}

        {step === 'ready' && data && (
          <>
            <div className="dash-cards">
              <MetricCard label="💰 Выручка" value={fmtMoney(data.current.revenue)} />
              <MetricCard label="✅ Пришли" value={data.current.done} />
              <MetricCard label="📋 Всего записей" value={data.current.total} />
              <MetricCard label="💵 Средний чек" value={fmtMoney(data.current.avg_check)} />
              <MetricCard label="🚫 Неявки" value={fmtPct(data.current.no_show_pct)} />
              <MetricCard
                label="📊 Загрузка"
                value={fmtPct(data.current.load_pct)}
                hint={`${data.current.booked_slots} из ${data.current.total_slots} слотов`}
              />
            </div>

            <div className="dash-cards" style={{ marginTop: 8 }}>
              <MetricCard label="👥 Клиентов" value={data.current.unique_clients} />
              <MetricCard label="🆕 Новых (к специалисту)" value={data.current.new_clients} />
              <MetricCard label="🔁 Постоянных" value={data.current.returning_clients} />
            </div>

            {data.top_services.length > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <h2 className="card-title">🏆 Топ услуг</h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {data.top_services.map((s, i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 2 }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>
                          {i + 1}. {s.name}
                        </span>
                        <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap', marginLeft: 8 }}>
                          <b style={{ color: 'var(--text)' }}>{s.count}</b>
                          {s.revenue > 0 && ` · ${fmtMoney(s.revenue)}`}
                        </span>
                      </div>
                      <div style={{ height: 8, background: 'var(--bg)', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${maxService > 0 ? (s.count / maxService * 100) : 0}%`,
                          background: 'var(--primary)', borderRadius: 4,
                        }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.top_services.length === 0 && (
              <div className="create-req-empty" style={{ marginTop: 16 }}>
                За этот период нет завершённых визитов.
              </div>
            )}

            {data.review_stats && data.review_stats.total > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <h2 className="card-title">⭐ Отзывы о специалисте</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: 12, background: 'var(--bg)', borderRadius: 10 }}>
                  <div style={{ textAlign: 'center', minWidth: 80 }}>
                    <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--primary)' }}>
                      {data.review_stats.avg_rating.toFixed(1)}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      из 5 · {data.review_stats.total} отзыв{data.review_stats.total === 1 ? '' : data.review_stats.total < 5 ? 'а' : 'ов'}
                    </div>
                  </div>
                  <div style={{ flex: 1 }}>
                    {[5, 4, 3, 2, 1].map((r) => {
                      const count = (data.review_stats.distribution || {})[String(r)] || 0;
                      const pct = data.review_stats.total > 0
                        ? (count / data.review_stats.total * 100)
                        : 0;
                      return (
                        <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 2 }}>
                          <span style={{ width: 22, color: 'var(--text-muted)' }}>{r}⭐</span>
                          <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: pct + '%', background: 'var(--primary)' }} />
                          </div>
                          <span style={{ width: 20, textAlign: 'right', color: 'var(--text-muted)' }}>{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {data.review_stats.recent && data.review_stats.recent.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
                      Полный список — в разделе «⭐ Отзывы» (там можно фильтровать
                      по специалисту и по конкретной оценке).
                    </div>
                    {data.review_stats.recent.slice(0, 5).map((rv) => (
                      <div key={rv.id} style={{ padding: '8px 10px', background: 'var(--bg)', borderRadius: 8, marginBottom: 4, fontSize: 13 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                          <span style={{ fontWeight: 600 }}>
                            {'⭐'.repeat(rv.rating)}{'☆'.repeat(5 - rv.rating)}
                            <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>
                              {rv.client_name}
                            </span>
                          </span>
                          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                            {rv.created_at?.slice(0, 10) || ''}
                          </span>
                        </div>
                        {rv.service_name && (
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            {rv.service_name}{rv.scheduled_at && ` · ${rv.scheduled_at}`}
                          </div>
                        )}
                        {rv.comment && (
                          <div style={{ fontStyle: 'italic', marginTop: 2 }}>«{rv.comment}»</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}