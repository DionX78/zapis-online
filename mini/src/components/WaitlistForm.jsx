import { useState } from 'react';

function pad(n) { return n < 10 ? '0' + n : '' + n; }

function isoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

const PREFERRED = [
  { id: 'any', label: 'Любое' },
  { id: 'morning', label: 'Утро (до 12)' },
  { id: 'afternoon', label: 'День (12–17)' },
  { id: 'evening', label: 'Вечер (после 17)' },
];

export default function WaitlistForm({ service, doctor, date, api, onClose, onCreated }) {
  const baseDate = date ? new Date(date) : new Date();

  const [dateFrom, setDateFrom] = useState(isoDate(baseDate));
  const [dateTo, setDateTo] = useState(isoDate(addDays(baseDate, 7)));
  const [preferred, setPreferred] = useState('any');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const headerTitle = service ? service.name : (doctor ? doctor.name : '');
  const headerSub = service
    ? null
    : (doctor && doctor.specialty ? doctor.specialty : 'Любая услуга');

  async function submit() {
    setError('');
    if (!service && !doctor) {
      setError('Укажите услугу или специалиста');
      return;
    }
    if (!dateFrom || !dateTo) {
      setError('Укажите период');
      return;
    }
    if (dateTo < dateFrom) {
      setError('«По дату» не может быть раньше «С даты»');
      return;
    }
    setBusy(true);
    try {
      await api.createWaitlist({
        service_id: service ? service.id : null,
        doctor_id: doctor ? doctor.id : null,
        date_from: dateFrom,
        date_to: dateTo,
        preferred_time: preferred === 'any' ? null : preferred,
      });
      onCreated();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h2 className="card-title">🔔 Лист ожидания</h2>
        {headerTitle && (
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
            {service ? headerTitle : `👤 ${headerTitle}${headerSub ? ` · ${headerSub}` : ''}`}
          </p>
        )}

        <div className="form-group">
          <label className="form-label">С какой даты искать</label>
          <input
            className="form-input"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            disabled={busy}
          />
        </div>

        <div className="form-group">
          <label className="form-label">По какую дату</label>
          <input
            className="form-input"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            disabled={busy}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Удобное время</label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {PREFERRED.map((p) => (
              <button
                key={p.id}
                type="button"
                className={'filter-btn' + (preferred === p.id ? ' active' : '')}
                onClick={() => setPreferred(p.id)}
                disabled={busy}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{
          fontSize: 12, color: 'var(--text-muted)',
          padding: '8px 12px', background: 'var(--primary-soft)',
          borderRadius: 8, marginBottom: 12,
        }}>
          Мы пришлём уведомление, если освободится подходящее время.
          Заявка ни к чему не обязывает — записаться можно только по вашей команде.
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button
            className="btn-action confirm"
            onClick={submit}
            disabled={busy}
          >
            {busy ? 'Отправка…' : '🔔 Оставить заявку'}
          </button>
          <button
            className="btn-action reject"
            onClick={onClose}
            disabled={busy}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}