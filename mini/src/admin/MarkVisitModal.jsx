import { useState } from 'react';

const PAYMENT_METHODS = [
  { id: 'cash', label: '💵 Наличные' },
  { id: 'card', label: '💳 Карта' },
  { id: 'transfer', label: '🏦 Перевод' },
  { id: 'other', label: '📝 Другое' },
];

const PAYMENT_LABELS = {
  cash: 'Наличные',
  card: 'Карта',
  transfer: 'Перевод',
  other: 'Другое',
};

export default function MarkVisitModal({ request, defaultPrice, onCancel, onConfirm }) {
  // Приоритет: уже сохранённая сумма > цена по прайсу > пусто.
  // Админ может «прошёпать» много записей без ввода суммы.
  const [amount, setAmount] = useState(() => {
    if (request.actual_amount != null) return String(request.actual_amount);
    if (defaultPrice != null) return String(defaultPrice);
    return '';
  });
  const [method, setMethod] = useState(request.payment_method || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleConfirm(withPayment) {
    setError('');
    setBusy(true);
    try {
      const payload = {};
      if (withPayment) {
        if (amount !== '') {
          const n = parseInt(amount, 10);
          if (!Number.isFinite(n) || n < 0) {
            setError('Сумма должна быть неотрицательным числом');
            setBusy(false);
            return;
          }
          payload.actual_amount = n;
        }
        if (method) {
          payload.payment_method = method;
        }
      }
      await onConfirm(payload);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onCancel()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <h2 className="card-title">Клиент пришёл</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
          #{request.id} · {request.service_name} · {request.scheduled_at}
        </p>

        <div className="form-group">
          <label className="form-label">Фактическая сумма, ₽</label>
          <input
            className="form-input"
            type="number"
            inputMode="numeric"
            min="0"
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="например, 5000"
            disabled={busy}
          />
          {defaultPrice != null && amount !== String(defaultPrice) && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              По прайсу: {defaultPrice} ₽
            </div>
          )}
        </div>

        <div className="form-group">
          <label className="form-label">Способ оплаты</label>
          <div className="payment-methods">
            {PAYMENT_METHODS.map((m) => (
              <button
                key={m.id}
                type="button"
                className={'filter-btn' + (method === m.id ? ' active' : '')}
                onClick={() => setMethod(method === m.id ? '' : m.id)}
                disabled={busy}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn-action confirm"
            onClick={() => handleConfirm(true)}
            disabled={busy}
            style={{ flex: 1, minWidth: 140 }}
          >
            {busy ? 'Сохранение…' : '✅ Сохранить'}
          </button>
          <button
            type="button"
            className="btn-action"
            onClick={() => handleConfirm(false)}
            disabled={busy}
            style={{ flex: 1, minWidth: 140 }}
            title="Отметить визит, не указывая сумму"
          >
            Без суммы
          </button>
          <button
            type="button"
            className="btn-action reject"
            onClick={onCancel}
            disabled={busy}
            style={{ flex: '0 0 80px' }}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}

export { PAYMENT_LABELS };