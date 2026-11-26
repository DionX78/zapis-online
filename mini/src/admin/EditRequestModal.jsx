import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

function formatTime(h, m) {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export default function EditRequestModal({ orgId, request, onClose, onSaved }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [services, setServices] = useState([]);
  const [slotOptions, setSlotOptions] = useState(null);

  const [serviceId, setServiceId] = useState(request.service_id || '');
  const [slotsCount, setSlotsCount] = useState(String(request.slots_count || 1));
  const [busy, setBusy] = useState(false);

  async function loadSlotOptions() {
    try {
      const data = await adminApi.getRequestSlotOptions(orgId, request.id);
      setSlotOptions(data);
      return data;
    } catch (e) {
      console.warn('slot_options failed:', e);
      return null;
    }
  }

  useEffect(() => {
    Promise.all([
      adminApi.getServices(orgId),
      loadSlotOptions(),
    ])
      .then(([d]) => {
        setServices((d.services || []).filter((s) => s.active));
        setStep('ready');
      })
      .catch((e) => { setError(e.message); setStep('error'); });
  }, [orgId]);

  async function handleServiceChange(newServiceId) {
    setServiceId(newServiceId);
    const opts = await loadSlotOptions();
    if (newServiceId && opts && opts.suggested_by_service) {
      setSlotsCount(String(opts.suggested_by_service));
    } else {
      setSlotsCount('1');
    }
  }

  async function submit() {
    setError('');
    const n = parseInt(slotsCount, 10);
    if (!Number.isFinite(n) || n < 1 || n > 20) {
      setError('Количество слотов должно быть от 1 до 20');
      return;
    }
    if (slotOptions && n > slotOptions.max_consecutive) {
      setError(`Максимум ${slotOptions.max_consecutive} слотов подряд от текущего времени`);
      return;
    }
    setBusy(true);
    try {
      await adminApi.editRequest(orgId, request.id, {
        service_id: serviceId || null,
        slots_count: n,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (step === 'loading') {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="loading">Загрузка…</div>
        </div>
      </div>
    );
  }
  if (step === 'error') {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="error-box">Ошибка: {error}</div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn-action reject" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    );
  }

  const selectedService = services.find((s) => s.id === serviceId);
  const stepMin = slotOptions ? (slotOptions.step_min || 30) : 30;
  const maxSlots = slotOptions ? slotOptions.max_consecutive : 1;
  const currentValue = parseInt(slotsCount, 10) || 1;

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <h2 className="card-title">✏️ Редактировать запись</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
          #{request.id} · {request.scheduled_at}
        </p>

        <div className="form-group">
          <label className="form-label">Услуга</label>
          <select
            className="form-input"
            value={serviceId}
            onChange={(e) => handleServiceChange(e.target.value)}
            disabled={busy}
          >
            <option value="">— Не указана —</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}{s.duration_min ? ` · ${s.duration_min} мин` : ''}
              </option>
            ))}
          </select>
          {selectedService && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              {selectedService.price} ₽ · {selectedService.duration_min} мин
              {selectedService.buffer_min > 0 && ` + ${selectedService.buffer_min} мин буфер`}
            </div>
          )}
        </div>

        <div className="form-group">
          <label className="form-label">Сколько слотов занять</label>
          <select
            className="form-input"
            value={currentValue > maxSlots ? '' : String(currentValue)}
            onChange={(e) => setSlotsCount(e.target.value)}
            disabled={busy || maxSlots < 1}
          >
            {currentValue > maxSlots && (
              <option value="">— сейчас {currentValue}, но доступно только {maxSlots} —</option>
            )}
            {Array.from({ length: maxSlots }, (_, i) => i + 1).map((n) => {
              const totalMin = n * stepMin;
              const suffix = n === 1 ? 'слот' : n < 5 ? 'слота' : 'слотов';
              return (
                <option key={n} value={n}>
                  {n} {suffix} · {totalMin} мин
                </option>
              );
            })}
          </select>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            1 слот = <b>{stepMin} мин</b>
            {currentValue && currentValue <= maxSlots && (
              <> · выбрано: <b>{currentValue * stepMin} мин</b></>
            )}
          </div>
          {slotOptions && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              Доступно подряд: <b>{maxSlots}</b> · по услуге нужно: <b>{slotOptions.suggested_by_service}</b>
            </div>
          )}
          {slotOptions && slotOptions.limit_reason === 'break'
            && slotOptions.break_from && slotOptions.break_until && (
            <div style={{ fontSize: 12, color: '#8b5a00', marginTop: 2 }}>
              ⚠️ Перерыв в расписании: {slotOptions.break_from} — {slotOptions.break_until}.
              Приём после перерыва — отдельной записью.
            </div>
          )}
          {slotOptions && slotOptions.limit_reason === 'busy' && slotOptions.conflict_at && (
            <div style={{ fontSize: 12, color: '#8b5a00', marginTop: 2 }}>
              ⚠️ Слот на {slotOptions.conflict_at} занят другой записью.
            </div>
          )}
          {slotOptions && slotOptions.limit_reason === 'end_of_day' && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              Дальше — конец дня.
            </div>
          )}
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={submit} disabled={busy || currentValue > maxSlots}>
            {busy ? 'Сохранение…' : '✅ Сохранить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}