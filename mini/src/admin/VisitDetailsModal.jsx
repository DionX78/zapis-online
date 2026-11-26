import { adminApi } from './adminApi.js';

const STATUS_LABELS = {
  pending: 'ожидает подтверждения',
  confirmed: 'подтверждена',
  cancelled: 'отменена',
  done: 'пришёл',
  no_show: 'не пришёл',
};

const PAYMENT_LABELS = {
  cash: '💵 Наличные',
  card: '💳 Карта',
  transfer: '🏦 Перевод',
  other: '📝 Другое',
};

function humanTs(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.replace(' ', 'T'));
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return iso; }
}

export default function VisitDetailsModal({ visit, serviceName, onClose }) {
  if (!visit) return null;

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 200 }}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h2 className="card-title">📋 Визит #{visit.id}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0, marginBottom: 16 }}>
          {serviceName || '—'}
        </p>

        <div className="modal" style={{ padding: 0, boxShadow: 'none', border: 'none' }}>
          <div className="row"><span>Дата и время:</span> {humanTs(visit.scheduled_at)}</div>
          <div className="row"><span>Специалист:</span> {visit.doctor || '—'}</div>
          <div className="row"><span>Статус:</span> {STATUS_LABELS[visit.status] || visit.status}</div>
          {visit.slots_count > 1 && (
            <div className="row"><span>Длительность:</span> {visit.slots_count} слота подряд</div>
          )}
          {visit.actual_amount != null && (
            <div className="row">
              <span>Оплата:</span> {visit.actual_amount} ₽
              {visit.payment_method && ` · ${PAYMENT_LABELS[visit.payment_method] || visit.payment_method}`}
              {visit.done_auto && (
                <span style={{ color: '#8b5a00', marginLeft: 6, fontSize: 12 }}>
                  (авто, проверьте)
                </span>
              )}
            </div>
          )}
          {visit.actual_amount == null && visit.status === 'done' && (
            <div className="row">
              <span>Оплата:</span>
              <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                не указана
              </span>
            </div>
          )}
        </div>

        <div style={{ marginTop: 16, padding: 12, background: 'var(--bg)', borderRadius: 8, fontSize: 13 }}>
          <div style={{ color: 'var(--text-muted)', lineHeight: 1.5 }}>
            📝 Заметки о приёме, рекомендации и материалы появятся здесь в следующих обновлениях.
          </div>
        </div>

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}