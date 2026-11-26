import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function todayIso() {
  const d = new Date();
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function newShiftForDay(weekday, defaultBranchId) {
  return {
    _key: Math.random().toString(36).slice(2),
    branch_id: defaultBranchId || null,
    weekday,
    start_time: '09:00',
    end_time: '18:00',
    break_start: '',
    break_end: '',
  };
}

export default function DoctorScheduleModal({ orgId, doctor, onClose }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [saving, setSaving] = useState(false);

  // { weekday: [shift, ...] }
  const [shiftsByDay, setShiftsByDay] = useState({});
  const [branches, setBranches] = useState([]);
  const [exceptions, setExceptions] = useState([]);

  const [unlimited, setUnlimited] = useState(true);
  const [stopDate, setStopDate] = useState('');

  const [excForm, setExcForm] = useState({ date_from: '', date_to: '', reason: '' });
  const [excBusy, setExcBusy] = useState(false);
  const [excError, setExcError] = useState('');

  async function load() {
    setStep('loading');
    try {
      const [scheduleData, excData, brData, docsData] = await Promise.all([
        adminApi.getDoctorSchedule(orgId, doctor.id),
        adminApi.getDoctorScheduleExceptions(orgId, doctor.id),
        adminApi.getBranches(orgId),
        adminApi.getDoctorsByOrg(orgId),
      ]);

      const brList = brData.branches || [];
      setBranches(brList);

      const byDay = {};
      for (let wd = 0; wd < 7; wd++) byDay[wd] = [];
      for (const sh of (scheduleData.shifts || [])) {
        byDay[sh.weekday].push({
          _key: `s${sh.id}`,
          branch_id: sh.branch_id,
          weekday: sh.weekday,
          start_time: sh.start_time,
          end_time: sh.end_time,
          break_start: sh.break_start || '',
          break_end: sh.break_end || '',
        });
      }
      setShiftsByDay(byDay);

      const fresh = (docsData.doctors || []).find((d) => d.id === doctor.id);
      const sd = fresh?.schedule_stop_date || null;
      if (sd) {
        setUnlimited(false);
        setStopDate(sd);
      } else {
        setUnlimited(true);
        setStopDate('');
      }

      setExceptions(excData.exceptions || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId, doctor.id]);

  function addShift(wd) {
    const defaultBranch = branches.length > 0 ? branches[0].id : null;
    setShiftsByDay((m) => ({ ...m, [wd]: [...(m[wd] || []), newShiftForDay(wd, defaultBranch)] }));
    setSaveMsg('');
  }

  function removeShift(wd, key) {
    setShiftsByDay((m) => ({ ...m, [wd]: (m[wd] || []).filter((s) => s._key !== key) }));
    setSaveMsg('');
  }

  function updateShift(wd, key, field, value) {
    setShiftsByDay((m) => ({
      ...m,
      [wd]: (m[wd] || []).map((s) => (s._key === key ? { ...s, [field]: value } : s)),
    }));
    setSaveMsg('');
  }

  function toggleBreak(wd, key) {
    setShiftsByDay((m) => ({
      ...m,
      [wd]: (m[wd] || []).map((s) => {
        if (s._key !== key) return s;
        const hasBreak = !!s.break_start;
        return {
          ...s,
          break_start: hasBreak ? '' : '13:00',
          break_end: hasBreak ? '' : '14:00',
        };
      }),
    }));
    setSaveMsg('');
  }

  async function handleSaveAndApply() {
    setSaving(true);
    setSaveMsg('');
    setError('');

    try {
      const shifts = [];
      for (const wd of Object.keys(shiftsByDay)) {
        for (const s of shiftsByDay[wd]) {
          if (!s.branch_id) {
            setError('У каждой смены должен быть выбран филиал');
            setSaving(false);
            return;
          }
          shifts.push({
            branch_id: parseInt(s.branch_id, 10),
            weekday: parseInt(wd, 10),
            start_time: s.start_time,
            end_time: s.end_time,
            break_start: s.break_start || null,
            break_end: s.break_end || null,
          });
        }
      }

      await adminApi.setDoctorSchedule(orgId, doctor.id, shifts);

      const newStopDate = unlimited ? null : (stopDate || null);
      const r = await adminApi.setDoctorScheduleStop(orgId, doctor.id, newStopDate);

      const regen = r.regenerate || {};
      setSaveMsg(
        `✅ Готово. Создано: ${regen.created ?? 0}, ` +
        `удалено пустых: ${regen.deleted ?? 0}, ` +
        `занятых: ${regen.skipped_booked ?? 0}`
      );
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddException() {
    setExcBusy(true);
    setExcError('');
    try {
      if (!excForm.date_from) {
        setExcError('Укажите дату начала');
        setExcBusy(false);
        return;
      }
      const date_to = excForm.date_to || excForm.date_from;
      await adminApi.createDoctorScheduleException(orgId, doctor.id, {
        date_from: excForm.date_from,
        date_to,
        reason: excForm.reason,
      });
      setExcForm({ date_from: '', date_to: '', reason: '' });
      await load();
    } catch (e) {
      setExcError(e.message);
    } finally {
      setExcBusy(false);
    }
  }

  async function handleDeleteException(excId) {
    if (!window.confirm('Удалить исключение?')) return;
    try {
      await adminApi.deleteDoctorScheduleException(orgId, doctor.id, excId);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  function branchName(bid) {
    const b = branches.find((x) => x.id === bid);
    return b ? b.name : `#${bid}`;
  }

  if (step === 'loading') return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="loading">Загрузка…</div>
      </div>
    </div>
  );

  if (step === 'error') return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="error-box">Ошибка: {error}</div>
        <div className="actions" style={{ marginTop: 12 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );

  if (!branches.length) return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="error-box">
          Сначала создайте хотя бы один филиал в разделе «🏢 Филиалы».
        </div>
        <div className="actions" style={{ marginTop: 12 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <h2 className="card-title">📅 График специалиста: {doctor.name}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0, marginBottom: 16 }}>
          По каждому дню — список смен. Можно добавить несколько смен в день,
          в разных филиалах. Время смен внутри одного дня не должно пересекаться.
        </p>

        <div style={{ marginBottom: 20 }}>
          {WEEKDAY_LABELS.map((label, wd) => {
            const dayShifts = shiftsByDay[wd] || [];
            return (
              <div key={wd} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: dayShifts.length ? 8 : 0 }}>
                  <span style={{ fontWeight: 600, minWidth: 40 }}>{label}</span>
                  {dayShifts.length === 0 && <span className="day-off">выходной</span>}
                  <button
                    type="button"
                    className="btn-link"
                    style={{ fontSize: 12, padding: '4px 8px', marginLeft: 'auto' }}
                    onClick={() => addShift(wd)}
                    disabled={saving}
                  >
                    + Смена
                  </button>
                </div>

                {dayShifts.map((s) => {
                  const hasBreak = !!s.break_start;
                  return (
                    <div
                      key={s._key}
                      style={{
                        marginLeft: 28,
                        marginTop: 8,
                        padding: 10,
                        background: 'var(--bg)',
                        borderRadius: 8,
                      }}
                    >
                      <div className="form-group" style={{ marginBottom: 6 }}>
                        <label className="form-label" style={{ fontSize: 12 }}>Филиал</label>
                        <select
                          className="form-input"
                          value={s.branch_id || ''}
                          onChange={(e) => updateShift(wd, s._key, 'branch_id', parseInt(e.target.value, 10) || null)}
                          disabled={saving}
                        >
                          <option value="">— выберите —</option>
                          {branches.map((b) => (
                            <option key={b.id} value={b.id}>{b.name}</option>
                          ))}
                        </select>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <input
                          className="time-input"
                          type="time"
                          value={s.start_time}
                          onChange={(e) => updateShift(wd, s._key, 'start_time', e.target.value)}
                          disabled={saving}
                        />
                        <span className="dash">—</span>
                        <input
                          className="time-input"
                          type="time"
                          value={s.end_time}
                          onChange={(e) => updateShift(wd, s._key, 'end_time', e.target.value)}
                          disabled={saving}
                        />
                        <button
                          type="button"
                          className="btn-link"
                          style={{ fontSize: 12, padding: '4px 8px' }}
                          onClick={() => toggleBreak(wd, s._key)}
                          disabled={saving}
                        >
                          {hasBreak ? '✕ Перерыв' : '+ Перерыв'}
                        </button>
                        <button
                          type="button"
                          className="btn-link"
                          style={{ fontSize: 12, padding: '4px 8px', color: 'var(--danger)', marginLeft: 'auto' }}
                          onClick={() => removeShift(wd, s._key)}
                          disabled={saving}
                        >
                          🗑 Удалить смену
                        </button>
                      </div>
                      {hasBreak && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 60 }}>Перерыв:</span>
                          <input
                            className="time-input"
                            type="time"
                            value={s.break_start}
                            onChange={(e) => updateShift(wd, s._key, 'break_start', e.target.value)}
                            disabled={saving}
                          />
                          <span className="dash">—</span>
                          <input
                            className="time-input"
                            type="time"
                            value={s.break_end}
                            onChange={(e) => updateShift(wd, s._key, 'break_end', e.target.value)}
                            disabled={saving}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        <div style={{ padding: 12, background: 'var(--bg)', borderRadius: 10, marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
            📅 Ограничение генерации слотов
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
            Если специалист уходит в отпуск / увольняется, укажите дату, до которой
            нужно генерировать слоты включительно. Всё, что дальше — удалится
            (забронированные слоты останутся).
          </div>
          <label className="checkbox-row" style={{ marginBottom: unlimited ? 0 : 8 }}>
            <input
              type="checkbox"
              checked={unlimited}
              onChange={(e) => {
                setUnlimited(e.target.checked);
                if (e.target.checked) setStopDate('');
              }}
              disabled={saving}
            />
            <span>Бессрочно (без ограничений)</span>
          </label>
          {!unlimited && (
            <div className="form-group" style={{ marginBottom: 0, marginTop: 8 }}>
              <label className="form-label">Генерировать до (включительно)</label>
              <input
                className="form-input"
                type="date"
                value={stopDate}
                min={todayIso()}
                onChange={(e) => setStopDate(e.target.value)}
                disabled={saving}
              />
            </div>
          )}
        </div>

        {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}

        <div className="actions" style={{ marginBottom: 8, flexWrap: 'wrap' }}>
          <button className="btn-action confirm" onClick={handleSaveAndApply} disabled={saving}>
            {saving ? 'Применение…' : '💾 Сохранить и применить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={saving}>
            Закрыть
          </button>
        </div>
        {saveMsg && (
          <div style={{ color: 'var(--accent)', fontSize: 13, marginBottom: 20, textAlign: 'center' }}>
            {saveMsg}
          </div>
        )}

        <h3 style={{ fontSize: 16, marginTop: 20, marginBottom: 8 }}>
          Исключения (отпуск, больничный)
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 0, marginBottom: 12 }}>
          В эти даты слоты не будут создаваться ни в одном филиале.
        </p>

        {!exceptions.length && (
          <div className="create-req-empty" style={{ marginBottom: 12 }}>
            Исключений пока нет.
          </div>
        )}

        {exceptions.map((e) => (
          <div key={e.id} className="dir-item" style={{ paddingLeft: 0, paddingRight: 0 }}>
            <div className="dir-main">
              <div className="dir-title">
                {e.date_from === e.date_to ? e.date_from : `${e.date_from} — ${e.date_to}`}
              </div>
              {e.reason && <div className="dir-meta">{e.reason}</div>}
            </div>
            <div className="dir-actions">
              <button
                className="dir-btn danger"
                onClick={() => handleDeleteException(e.id)}
                title="Удалить исключение"
              >🗑</button>
            </div>
          </div>
        ))}

        <div style={{ marginTop: 12, padding: 12, background: 'var(--bg)', borderRadius: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>➕ Добавить исключение</div>
          <div className="form-row-2" style={{ marginBottom: 8 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">С даты</label>
              <input
                className="form-input"
                type="date"
                value={excForm.date_from}
                onChange={(e) => { setExcForm({ ...excForm, date_from: e.target.value }); setExcError(''); }}
                disabled={excBusy}
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">По дату (необязательно)</label>
              <input
                className="form-input"
                type="date"
                value={excForm.date_to}
                onChange={(e) => setExcForm({ ...excForm, date_to: e.target.value })}
                disabled={excBusy}
              />
            </div>
          </div>
          <div className="form-group" style={{ marginBottom: 8 }}>
            <label className="form-label">Причина (необязательно)</label>
            <input
              className="form-input"
              type="text"
              placeholder="Отпуск, больничный и т.п."
              value={excForm.reason}
              onChange={(e) => setExcForm({ ...excForm, reason: e.target.value })}
              maxLength={200}
              disabled={excBusy}
            />
          </div>
          {excError && <div className="form-error" style={{ marginBottom: 8 }}>{excError}</div>}
          <div className="actions" style={{ marginTop: 8 }}>
            <button
              className="btn-action confirm"
              onClick={handleAddException}
              disabled={excBusy || !excForm.date_from}
            >
              {excBusy ? 'Добавление…' : '➕ Добавить'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}