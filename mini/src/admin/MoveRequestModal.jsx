import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const MONTHS_SHORT = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];

function isoDate(d) {
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function humanDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]}`;
}

export default function MoveRequestModal({ orgId, request, onClose, onMoved }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [branches, setBranches] = useState([]);
  const [branchId, setBranchId] = useState('');
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [slots, setSlots] = useState([]);
  const [selectedSlotId, setSelectedSlotId] = useState('');
  const [busy, setBusy] = useState(false);
  const [slotsBusy, setSlotsBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      adminApi.getBranches(orgId).catch(() => ({ branches: [] })),
      adminApi.getServices(orgId).catch(() => ({ services: [] })),
    ]).then(([b]) => {
      const list = b.branches || [];
      setBranches(list);
      if (list.length) {
        const primary = list.find((x) => x.is_primary) || list[0];
        setBranchId(String(primary.id));
      }
      setStep('ready');
    });
  }, [orgId]);

  const slotsCount = request.slots_count || 1;

  useEffect(() => {
    if (!branchId) return;
    const today = new Date();
    const from = isoDate(today);
    const to = isoDate(addDays(today, 30));
    adminApi.getAvailableSlots(
      orgId,
      request.service_id || null,
      from, to,
      branchId,
      request.doctor_id || null,
      slotsCount,
    )
      .then((data) => {
        const free = (data.slots || []).filter((s) => s.id !== request.slot_id);
        const dateSet = new Set(free.map((s) => s.date));
        const sorted = Array.from(dateSet).sort();
        setDates(sorted);
        if (sorted.length && !sorted.includes(selectedDate)) {
          setSelectedDate(sorted[0]);
        }
      })
      .catch(() => setDates([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [branchId, request.service_id, request.doctor_id, slotsCount, orgId]);

  useEffect(() => {
    if (!selectedDate || !branchId) {
      setSlots([]); setSelectedSlotId('');
      return;
    }
    setSlotsBusy(true);
    adminApi.getAvailableSlots(
      orgId,
      request.service_id || null,
      selectedDate, selectedDate,
      branchId,
      request.doctor_id || null,
      slotsCount,
    )
      .then((data) => {
        const free = (data.slots || []).filter((s) => s.id !== request.slot_id);
        setSlots(free);
        setSelectedSlotId('');
      })
      .catch(() => setSlots([]))
      .finally(() => setSlotsBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate, branchId, request.service_id, request.doctor_id, slotsCount, orgId]);

  async function handleMove() {
    if (!selectedSlotId) {
      setError('Выберите новое время');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await adminApi.moveRequest(orgId, request.id, selectedSlotId);
      if (onMoved) onMoved();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (step === 'loading') return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="loading">Загрузка…</div>
      </div>
    </div>
  );

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
        <h2 className="card-title">🔄 Перенести запись</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0, marginBottom: 12 }}>
          #{request.id} · {request.service_name} · {request.scheduled_at}
        </p>

        {branches.length > 1 && (
          <div className="form-group">
            <label className="form-label">Филиал</label>
            <select
              className="form-input"
              value={branchId}
              onChange={(e) => { setBranchId(e.target.value); setSelectedSlotId(''); }}
              disabled={busy}
            >
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}{b.is_primary ? ' 🏠' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="form-group">
          <label className="form-label">Новая дата</label>
          {!dates.length ? (
            <div className="create-req-empty">Нет свободных дат в этом филиале.</div>
          ) : (
            <div className="create-req-dates">
              {dates.slice(0, 20).map((d) => (
                <button
                  key={d}
                  type="button"
                  className={'filter-btn' + (selectedDate === d ? ' active' : '')}
                  onClick={() => setSelectedDate(d)}
                  disabled={busy}
                >
                  {humanDate(d)}
                </button>
              ))}
            </div>
          )}
        </div>

        {selectedDate && (
          <div className="form-group">
            <label className="form-label">Новое время</label>
            {slotsBusy && <div className="loading" style={{ padding: 8 }}>Загрузка…</div>}
            {!slotsBusy && !slots.length && (
              <div className="create-req-empty">Нет свободных окон на эту дату.</div>
            )}
            {!slotsBusy && slots.length > 0 && (
              <div className="create-req-slots">
                {slots.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={'filter-btn' + (selectedSlotId === s.id ? ' active' : '')}
                    onClick={() => setSelectedSlotId(s.id)}
                    disabled={busy}
                  >
                    {s.time}{s.doctor_name ? ` · ${s.doctor_name}` : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={handleMove} disabled={busy || !selectedSlotId}>
            {busy ? 'Перенос…' : '✅ Перенести'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>Отмена</button>
        </div>
      </div>
    </div>
  );
}