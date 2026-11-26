import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

const DEFAULT_GEN = {
  days: 7,
  days_of_week: [0, 1, 2, 3, 4],
  time_start: '09:00',
  time_end: '18:00',
  step_min: 30,
  service_id: '',
  doctor_id: '',
};

const WORK_START = 8;
const WORK_END = 20;

const LS_LAST_DOCTOR = 'max_booking_last_doctor_id';
const LS_LAST_SERVICE = 'max_booking_last_service_id';

function pad(n) { return n < 10 ? '0' + n : '' + n; }

function isoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function startOfWeek(d) {
  const copy = new Date(d);
  const wd = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - wd);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function humanDay(d) {
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

function buildTimeRows(stepMin) {
  const rows = [];
  for (let m = WORK_START * 60; m < WORK_END * 60; m += stepMin) {
    const h = Math.floor(m / 60);
    const mm = m % 60;
    rows.push(`${pad(h)}:${pad(mm)}`);
  }
  return rows;
}

function isPastDate(isoStr, timeStr) {
  const now = new Date();
  const [y, mo, d] = isoStr.split('-').map(Number);
  const [h, mi] = timeStr.split(':').map(Number);
  const dt = new Date(y, mo - 1, d, h, mi);
  return dt < now;
}

const STATUS_LABELS = {
  pending: 'ожидает',
  confirmed: 'подтверждена',
  cancelled: 'отменена',
  done: 'завершена',
};

export default function SchedulePage({ orgId }) {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [slots, setSlots] = useState([]);
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const [activeSheet, setActiveSheet] = useState(null);
  const [showGenForm, setShowGenForm] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState(() => ({
    date: '',
    time: '09:00',
    service_id: localStorage.getItem(LS_LAST_SERVICE) || '',
    doctor_id: localStorage.getItem(LS_LAST_DOCTOR) || '',
  }));
  const [genForm, setGenForm] = useState(() => ({
    ...DEFAULT_GEN,
    service_id: localStorage.getItem(LS_LAST_SERVICE) || '',
    doctor_id: localStorage.getItem(LS_LAST_DOCTOR) || '',
  }));

  const [branches, setBranches] = useState([]);
  const [doctors, setDoctors] = useState([]);          // по фильтру филиала (для шапки)
  const [allOrgDoctors, setAllOrgDoctors] = useState([]); // // все специалисты org (для создания слота)
  const [services, setServices] = useState([]);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [selectedDoctor, setSelectedDoctor] = useState('');

  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const dateFrom = isoDate(weekDays[0]);
  const dateTo = isoDate(weekDays[6]);
  const timeRows = buildTimeRows(30);

  async function loadSlots() {
    try {
      const data = await adminApi.getSlots(
        orgId, dateFrom, dateTo,
        selectedBranch || null, selectedDoctor || null
      );
      setSlots(data.slots || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  async function loadBranches() {
    try {
      const data = await adminApi.getBranches(orgId);
      const list = data.branches || [];
      setBranches(list);
      if (list.length) {
        const primary = list.find((b) => b.is_primary) || list[0];
        setSelectedBranch(primary.id);
      }
    } catch (e) {}
  }

  async function loadServices() {
    try {
      const data = await adminApi.getServices(orgId);
      setServices((data.services || []).filter((s) => s.active));
    } catch (e) {}
  }

  async function loadAllOrgDoctors() {
    try {
      const data = await adminApi.getDoctorsByOrg(orgId);
      setAllOrgDoctors(data.doctors || []);
    } catch (e) {}
  }

  useEffect(() => {
    setStep('loading');
    loadSlots();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, dateFrom, selectedBranch, selectedDoctor]);

  useEffect(() => {
    loadBranches();
    loadServices();
    loadAllOrgDoctors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  useEffect(() => {
    if (!selectedBranch) {
      setDoctors([]);
      setSelectedDoctor('');
      return;
    }
    adminApi
      .getDoctors(selectedBranch)
      .then((data) => {
        setDoctors(data.doctors || []);
        setSelectedDoctor('');
      })
      .catch(() => setDoctors([]));
  }, [selectedBranch]);

  function rememberChoice(serviceId, doctorId) {
    if (serviceId) localStorage.setItem(LS_LAST_SERVICE, serviceId);
    else localStorage.removeItem(LS_LAST_SERVICE);
    if (doctorId) localStorage.setItem(LS_LAST_DOCTOR, String(doctorId));
    else localStorage.removeItem(LS_LAST_DOCTOR);
  }

  function prevWeek() { setWeekStart(addDays(weekStart, -7)); }
  function nextWeek() { setWeekStart(addDays(weekStart, 7)); }

    async function handleQuickCreateSave(date, time, serviceId, doctorId) {
    setBusy(true);
    try {
      const basePayload = {
        date, time,
        branch_id: selectedBranch ? parseInt(selectedBranch, 10) : null,
        doctor_id: doctorId ? parseInt(doctorId, 10) : null,
        service_id: serviceId || null,
      };
      let r = await adminApi.createSlot(orgId, basePayload);

      if (!r.ok && r.error_code === 'skill_mismatch') {
        const confirmed = window.confirm(
          r.message + '\n\nЕсли продолжить, эта услуга будет автоматически добавлена специалисту.'
        );
        if (!confirmed) {
          setBusy(false);
          return;
        }
        r = await adminApi.createSlot(orgId, { ...basePayload, confirm_skill_mismatch: true });
      }

      if (!r.ok) {
        alert(r.note || 'Не удалось создать слот. Возможно, такой слот уже существует.');
        return;
      }
      rememberChoice(serviceId, doctorId);
      setActiveSheet(null);
      await loadSlots();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSlot(slotId) {
    if (!window.confirm('Удалить слот?')) return;
    setBusy(true);
    try {
      const r = await adminApi.deleteSlot(orgId, slotId);
      if (!r.ok) alert('Не удалось удалить: ' + (r.note || 'слот занят'));
      await loadSlots();
      setActiveSheet(null);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancelRequest(slot) {
    if (!slot.request_id) return;
    if (!window.confirm('Отменить запись? Слот освободится.')) return;
    setBusy(true);
    try {
      await adminApi.rejectRequest(orgId, slot.request_id);
      await loadSlots();
      setActiveSheet(null);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

    async function handleAddSlot() {
    if (!selectedBranch) {
      alert('Сначала выберите филиал в фильтре выше.');
      return;
    }
    if (!addForm.date || !addForm.time) return;
    if (isPastDate(addForm.date, addForm.time)) {
      alert('Нельзя создать слот в прошлом');
      return;
    }
    setBusy(true);
    try {
      const basePayload = {
        date: addForm.date,
        time: addForm.time,
        branch_id: parseInt(selectedBranch, 10),
        doctor_id: addForm.doctor_id ? parseInt(addForm.doctor_id, 10) : null,
        service_id: addForm.service_id || null,
      };
      let r = await adminApi.createSlot(orgId, basePayload);

      if (!r.ok && r.error_code === 'skill_mismatch') {
        const confirmed = window.confirm(
          r.message + '\n\nЕсли продолжить, эта услуга будет автоматически добавлена специалисту.'
        );
        if (!confirmed) {
          setBusy(false);
          return;
        }
        r = await adminApi.createSlot(orgId, { ...basePayload, confirm_skill_mismatch: true });
      }

      if (!r.ok) {
        alert(r.note || 'Не удалось создать слот. Возможно, такой слот уже существует.');
        return;
      }
      rememberChoice(addForm.service_id, addForm.doctor_id);
      setShowAddForm(false);
      setAddForm({
        date: '',
        time: '09:00',
        service_id: addForm.service_id,
        doctor_id: addForm.doctor_id,
      });
      await loadSlots();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

    async function handleGenerate() {
    if (!selectedBranch) {
      alert('Сначала выберите филиал в фильтре выше.');
      return;
    }
    setBusy(true);
    try {
      const basePayload = {
        ...genForm,
        service_id: genForm.service_id || null,
        branch_id: parseInt(selectedBranch, 10),
        doctor_id: genForm.doctor_id ? parseInt(genForm.doctor_id, 10) : null,
        date_from: dateFrom,
      };
      let data = await adminApi.generateSlots(orgId, basePayload);

      if (!data.ok && data.error_code === 'skill_mismatch') {
        const confirmed = window.confirm(
          data.message + '\n\nЕсли продолжить, эта услуга будет автоматически добавлена специалисту.'
        );
        if (!confirmed) {
          setBusy(false);
          return;
        }
        data = await adminApi.generateSlots(orgId, { ...basePayload, confirm_skill_mismatch: true });
      }

      if (!data.ok) {
        alert(data.note || 'Не удалось сгенерировать слоты.');
        return;
      }
      rememberChoice(genForm.service_id, genForm.doctor_id);
      setShowGenForm(false);
      await loadSlots();
      if (data.created === 0) {
        alert('Слоты не созданы. Возможно, они уже есть на эти даты/время.');
      } else {
        alert(`Создано слотов: ${data.created}`);
      }
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerateAll() {
    if (!window.confirm(
      'Пересоздать слоты из графиков всех специалистов?\n\n' +
      'Будут удалены только пустые автогенерированные слоты в пределах горизонта. ' +
      'Забронированные записи и слоты, созданные вручную, не пострадают.'
    )) return;
    setBusy(true);
    try {
      const r = await adminApi.regenerateAllSlots(orgId);
      await loadSlots();
      alert(
        `Готово.\nСпециалистов обработано: ${r.doctors}\n` +
        `Создано слотов: ${r.created}\n` +
        `Удалено пустых: ${r.deleted}\n` +
        `Оставлено занятых: ${r.skipped_booked}` +
        (r.errors && r.errors.length ? `\nОшибок: ${r.errors.length}` : '')
      );
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleDayOfWeek(d) {
    setGenForm((f) => {
      const has = f.days_of_week.includes(d);
      return {
        ...f,
        days_of_week: has
          ? f.days_of_week.filter((x) => x !== d)
          : [...f.days_of_week, d].sort(),
      };
    });
  }

  if (step === 'loading') return <div className="loading">Загрузка расписания…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;
  if (!branches.length) {
    return (
      <div className="error-box">
        В организации нет филиалов. Создайте хотя бы один в разделе
        «Справочники → Филиалы», чтобы работать с расписанием.
      </div>
    );
  }

  const slotsByDate = {};
  const dayStats = {};
  for (const s of slots) {
    if (!slotsByDate[s.date]) slotsByDate[s.date] = {};
    if (!slotsByDate[s.date][s.time]) slotsByDate[s.date][s.time] = [];
    slotsByDate[s.date][s.time].push(s);

    if (!dayStats[s.date]) dayStats[s.date] = { total: 0, booked: 0 };
    dayStats[s.date].total += 1;
    if (s.is_booked) dayStats[s.date].booked += 1;
  }

  function handleCellClick(iso, time) {
    const cellSlots = slotsByDate[iso] && slotsByDate[iso][time];
    const past = isPastDate(iso, time);

    if (!cellSlots || !cellSlots.length) {
      if (past) return;
      setActiveSheet({ kind: 'create', date: iso, time });
      return;
    }

    setActiveSheet({ kind: 'cell', date: iso, time, slots: cellSlots, past });
  }

  return (
    <div>
      <div className="sched-filters">
        <select
          className="org-select"
          value={selectedBranch}
          onChange={(e) => setSelectedBranch(e.target.value)}
        >
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}{b.is_primary ? ' 🏠' : ''}
            </option>
          ))}
        </select>
        {selectedBranch && doctors.length > 0 && (
          <select
            className="org-select"
            value={selectedDoctor}
            onChange={(e) => setSelectedDoctor(e.target.value)}
          >
            <option value="">Все специалисты</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        )}
      </div>

      <div className="week-nav">
        <button className="week-btn" onClick={prevWeek}>‹</button>
        <div className="week-label">
          {humanDay(weekDays[0])} — {humanDay(weekDays[6])}
        </div>
        <button className="week-btn" onClick={nextWeek}>›</button>
      </div>

      <div className="schedule-scroll">
        <div
          className="schedule-grid"
          style={{ gridTemplateColumns: `54px repeat(7, minmax(70px, 1fr))` }}
        >
          <div className="sg-cell sg-head"></div>
          {weekDays.map((d, i) => {
            const iso = isoDate(d);
            const isToday = iso === isoDate(new Date());
            const stats = dayStats[iso];
            return (
              <div key={i} className={'sg-cell sg-head' + (isToday ? ' today' : '')}>
                <div className="sg-weekday">{WEEKDAYS_SHORT[i]}</div>
                <div className="sg-date">{d.getDate()}</div>
                {stats && <div className="sg-day-stat">{stats.booked}/{stats.total}</div>}
              </div>
            );
          })}

          {timeRows.map((time) => (
            <>
              <div key={'t-' + time} className="sg-cell sg-time">{time}</div>
              {weekDays.map((d) => {
                const iso = isoDate(d);
                const cellSlots = (slotsByDate[iso] && slotsByDate[iso][time]) || [];
                const past = isPastDate(iso, time);
                const count = cellSlots.length;
                const anyBooked = cellSlots.some((s) => s.is_booked);

                let cls = 'sg-cell sg-slot';
                if (count === 0 && past) cls += ' sg-past';
                else if (count === 0) cls += ' sg-empty';
                else if (count === 1 && cellSlots[0].is_booked) cls += ' sg-booked';
                else if (count >= 1) cls += ' sg-multi';
                if (count > 0 && past) cls += ' sg-past-data';

                return (
                  <div
                    key={iso + time}
                    className={cls}
                    onClick={() => handleCellClick(iso, time)}
                  >
                    {count === 0 && !past && <span className="sg-plus">+</span>}

                    {count === 1 && (
                      <>
                        {cellSlots[0].is_booked ? (
                          <div className="sg-booked-info">
                            <div className="sg-client">{cellSlots[0].client_fio || '—'}</div>
                            <div className="sg-service">{cellSlots[0].service_name || '—'}</div>
                            {cellSlots[0].doctor_name && (
                              <div className="sg-doctor-name">{cellSlots[0].doctor_name}</div>
                            )}
                          </div>
                        ) : (
                          <div className="sg-free-info">
                            {cellSlots[0].slot_service_name && (
                              <div className="sg-slot-svc">{cellSlots[0].slot_service_name}</div>
                            )}
                          </div>
                        )}
                      </>
                    )}

                    {count >= 2 && (
                      <div className="sg-multi-info">
                        <div className="sg-multi-count">×{count}</div>
                        {anyBooked && <div className="sg-multi-dot">●</div>}
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>

      <div className="sched-actions">
        {!showAddForm && (
          <button className="btn-generate" onClick={() => setShowAddForm(true)}>
            ➕ Добавить слот
          </button>
        )}
        {!showGenForm && (
          <button className="btn-generate" onClick={() => setShowGenForm(true)}>
            ⚡ Сгенерировать слоты
          </button>
        )}
        <button
          className="btn-generate"
          onClick={handleRegenerateAll}
          disabled={busy}
          title="Пересоздать слоты из графиков всех специалистов организации"
        >
          🔄 Пересоздать все слоты
        </button>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginTop: 12 }}>
          <h2 className="card-title">Добавить один слот</h2>
          <div className="form-row-2">
            <div className="form-group">
              <label className="form-label">Дата</label>
              <input
                className="form-input" type="date"
                value={addForm.date}
                onChange={(e) => setAddForm({ ...addForm, date: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Время</label>
              <input
                className="form-input" type="time" step="300"
                value={addForm.time}
                onChange={(e) => setAddForm({ ...addForm, time: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Услуга (опционально)</label>
            <select
              className="form-input"
              value={addForm.service_id}
              onChange={(e) => setAddForm({ ...addForm, service_id: e.target.value })}
            >
              <option value="">Универсальный слот</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {allOrgDoctors.length > 0 && (
            <div className="form-group">
              <label className="form-label">Специалист (опционально)</label>
              <select
                className="form-input"
                value={addForm.doctor_id}
                onChange={(e) => setAddForm({ ...addForm, doctor_id: e.target.value })}
              >
                <option value="">Любой специалист</option>
                {allOrgDoctors.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Специалиста можно выбрать любого — даже если у него нет смен в
                текущем филиале. Ручной слот не подчиняется графику.
              </div>
            </div>
          )}

          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn-action confirm" onClick={handleAddSlot} disabled={busy}>
              ✅ Добавить
            </button>
            <button className="btn-action reject" onClick={() => setShowAddForm(false)} disabled={busy}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {showGenForm && (
        <div className="card" style={{ marginTop: 12 }}>
          <h2 className="card-title">Массовая генерация</h2>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 12px' }}>
            Начиная с {humanDay(weekDays[0])} на {genForm.days} дн. Это разовый
            инструмент — если вы настроили график специалиста, используйте «🔄 Пересоздать все слоты».
          </p>

          <div className="form-group">
            <label className="form-label">Услуга (опционально)</label>
            <select
              className="form-input"
              value={genForm.service_id}
              onChange={(e) => setGenForm({ ...genForm, service_id: e.target.value })}
            >
              <option value="">Универсальные слоты</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {allOrgDoctors.length > 0 && (
            <div className="form-group">
              <label className="form-label">Специалист (опционально)</label>
              <select
                className="form-input"
                value={genForm.doctor_id}
                onChange={(e) => setGenForm({ ...genForm, doctor_id: e.target.value })}
              >
                <option value="">Любой специалист</option>
                {allOrgDoctors.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Дни недели</label>
            <div className="dow-row">
              {WEEKDAYS_SHORT.map((w, i) => (
                <button
                  key={i}
                  className={'dow-btn' + (genForm.days_of_week.includes(i) ? ' active' : '')}
                  onClick={() => toggleDayOfWeek(i)}
                >
                  {w}
                </button>
              ))}
            </div>
          </div>

          <div className="form-row-2">
            <div className="form-group">
              <label className="form-label">С</label>
              <input
                className="form-input" type="time"
                value={genForm.time_start}
                onChange={(e) => setGenForm({ ...genForm, time_start: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">До</label>
              <input
                className="form-input" type="time"
                value={genForm.time_end}
                onChange={(e) => setGenForm({ ...genForm, time_end: e.target.value })}
              />
            </div>
          </div>

          <div className="form-row-2">
            <div className="form-group">
              <label className="form-label">Шаг (мин)</label>
              <input
                className="form-input" type="number" min="5" max="240" step="5"
                value={genForm.step_min}
                onChange={(e) => setGenForm({ ...genForm, step_min: parseInt(e.target.value || '0', 10) })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Дней вперёд</label>
              <input
                className="form-input" type="number" min="1" max="90"
                value={genForm.days}
                onChange={(e) => setGenForm({ ...genForm, days: parseInt(e.target.value || '1', 10) })}
              />
            </div>
          </div>

          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn-action confirm" onClick={handleGenerate} disabled={busy}>
              ✅ Сгенерировать
            </button>
            <button className="btn-action reject" onClick={() => setShowGenForm(false)} disabled={busy}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {activeSheet && activeSheet.kind === 'create' && (
        <QuickCreateSheet
          date={activeSheet.date}
          time={activeSheet.time}
          services={services}
          doctors={allOrgDoctors}
          busy={busy}
          onSave={(sid, did) => handleQuickCreateSave(activeSheet.date, activeSheet.time, sid, did)}
          onClose={() => setActiveSheet(null)}
        />
      )}

      {activeSheet && activeSheet.kind === 'cell' && (
        <CellSheet
          date={activeSheet.date}
          time={activeSheet.time}
          slots={activeSheet.slots}
          past={activeSheet.past}
          busy={busy}
          onDeleteSlot={handleDeleteSlot}
          onCancelRequest={(s) => {
            setActiveSheet(null);
            handleCancelRequest(s);
          }}
          onAddAnother={() => {
            setActiveSheet({ kind: 'create', date: activeSheet.date, time: activeSheet.time });
          }}
          onClose={() => setActiveSheet(null)}
        />
      )}
    </div>
  );
}


function QuickCreateSheet({ date, time, services, doctors, busy, onSave, onClose }) {
  const [serviceId, setServiceId] = useState(localStorage.getItem(LS_LAST_SERVICE) || '');
  const [doctorId, setDoctorId] = useState(localStorage.getItem(LS_LAST_DOCTOR) || '');

  return (
    <div className="bottom-sheet-backdrop" onClick={() => !busy && onClose()}>
      <div className="bottom-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-handle" />
        <h2 className="sheet-title">Новый слот</h2>
        <p className="sheet-subtitle">{date} · {time}</p>

        <div className="form-group">
          <label className="form-label">Услуга (опционально)</label>
          <select
            className="form-input"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            disabled={busy}
          >
            <option value="">Универсальный слот (любая услуга)</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        {doctors.length > 0 && (
          <div className="form-group">
            <label className="form-label">Специалист (опционально)</label>
            <select
              className="form-input"
              value={doctorId}
              onChange={(e) => setDoctorId(e.target.value)}
              disabled={busy}
            >
              <option value="">Любой врач</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Специалиста можно выбрать любого — даже если у него нет смен в этом филиале.
            </div>
          </div>
        )}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={() => onSave(serviceId, doctorId)} disabled={busy}>
            {busy ? 'Создание…' : '✅ Создать'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}


function CellSheet({ date, time, slots, past, busy, onDeleteSlot, onCancelRequest, onAddAnother, onClose }) {
  return (
    <div className="bottom-sheet-backdrop" onClick={() => !busy && onClose()}>
      <div className="bottom-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-handle" />
        <h2 className="sheet-title">Слоты на {time}</h2>
        <p className="sheet-subtitle">
          {date} · всего {slots.length}
          {past && ' · прошедшие'}
        </p>

        <div className="cell-slot-list">
          {slots.map((s) => {
            return (
              <div key={s.id} className="cell-slot-item">
                <div className="cell-slot-info">
                  <div className="cell-slot-service">
                    {s.is_booked
                      ? (s.service_name || 'Запись')
                      : (s.slot_service_name || 'Свободный слот')}
                  </div>
                  <div className="cell-slot-meta">
                    {s.is_booked ? (
                      <>
                        {s.client_fio || '—'} · {STATUS_LABELS[s.status] || s.status}
                        {s.doctor_name && ` · ${s.doctor_name}`}
                      </>
                    ) : (
                      <>Свободен{s.doctor_name ? ` · ${s.doctor_name}` : ''}</>
                    )}
                  </div>
                  {s.branch_name && (
                    <div className="cell-slot-branch">🏢 {s.branch_name}</div>
                  )}
                </div>
                <div className="cell-slot-actions">
                  {s.is_booked ? (
                    <button
                      className="dir-btn danger"
                      onClick={() => onCancelRequest(s)}
                      disabled={busy}
                      title="Отменить запись"
                    >
                      ❌
                    </button>
                  ) : (
                    !past && (
                      <button
                        className="dir-btn danger"
                        onClick={() => onDeleteSlot(s.id)}
                        disabled={busy}
                        title="Удалить слот"
                      >
                        🗑
                      </button>
                    )
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="actions" style={{ marginTop: 16 }}>
          {!past && (
            <button className="btn-action confirm" onClick={onAddAnother} disabled={busy}>
              ➕ Добавить ещё слот
            </button>
          )}
          <button className="btn-action reject" onClick={onClose} disabled={busy}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}