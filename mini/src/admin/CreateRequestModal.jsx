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

function isPastSlot(dateIso, timeStr) {
    const now = new Date();
    const [y, m, d] = dateIso.split('-').map(Number);
    const [h, mi] = timeStr.split(':').map(Number);
    const dt = new Date(y, m - 1, d, h, mi);
    return dt < now;
  }

function notifyMessage(result) {
  const st = result.notify_status;
  if (st === 'sent') return { text: 'Клиент уведомлён в MAX.', cls: 'ok' };
  if (st === 'no_max') return {
    text: 'У клиента нет MAX-аккаунта в системе. Свяжитесь по телефону.',
    cls: 'warn',
  };
  if (st === 'blocked') return {
    text: 'Клиент есть в MAX, но не подключал бот (или заблокировал). Свяжитесь по телефону.',
    cls: 'warn',
  };
  return {
    text: `Ошибка отправки: ${result.notify_error || 'неизвестная'}`,
    cls: 'err',
  };
}

function buildDailyLimitConfirmText(data) {
  const lines = [
    data.message || `У клиента уже ${data.existing_count} активных записей на этот день.`,
    '',
    'Существующие записи на этот день:',
  ];
  for (const b of data.existing_bookings || []) {
    let line = `• #${b.id} — ${b.service_name} · ${b.scheduled_at}`;
    if (b.doctor) line += ` · ${b.doctor}`;
    lines.push(line);
  }
  lines.push('');
  lines.push('Всё равно создать новую запись?');
  return lines.join('\n');
}

export default function CreateRequestModal({ orgId, onClose, onCreated }) {
  const [step, setStep] = useState('form');
  const [error, setError] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchBusy, setSearchBusy] = useState(false);

  const [phone, setPhone] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [selectedClient, setSelectedClient] = useState(null);

  const [services, setServices] = useState([]);
  const [branches, setBranches] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [serviceId, setServiceId] = useState('');
  const [branchId, setBranchId] = useState('');
  const [doctorId, setDoctorId] = useState('');
  const [slotsCount, setSlotsCount] = useState('1');

  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [slots, setSlots] = useState([]);
  const [selectedSlotId, setSelectedSlotId] = useState('');
  const [slotsBusy, setSlotsBusy] = useState(false);

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const doctorNameById = {};
  for (const d of doctors) doctorNameById[d.id] = d.name;

  const selectedService = services.find((s) => s.id === serviceId) || null;

  const sortedDoctors = (() => {
    if (!branchId) return doctors;
    const targetBid = parseInt(branchId, 10);
    return [...doctors].sort((a, b) => {
      const aIds = Array.isArray(a.branch_ids) && a.branch_ids.length > 0 ? a.branch_ids : [a.branch_id];
      const bIds = Array.isArray(b.branch_ids) && b.branch_ids.length > 0 ? b.branch_ids : [b.branch_id];
      const aIn = aIds.includes(targetBid) ? 0 : 1;
      const bIn = bIds.includes(targetBid) ? 0 : 1;
      return aIn - bIn;
    });
  })();

  useEffect(() => {
    Promise.all([
      adminApi.getServices(orgId).catch(() => ({ services: [] })),
      adminApi.getBranches(orgId).catch(() => ({ branches: [] })),
      adminApi.getDoctorsByOrg(orgId).catch(() => ({ doctors: [] })),
    ]).then(([s, b, d]) => {
      setServices((s.services || []).filter((x) => x.active));
      const brList = b.branches || [];
      setBranches(brList);
      setDoctors(d.doctors || []);
      if (brList.length > 0) {
        const primary = brList.find((x) => x.is_primary) || brList[0];
        setBranchId(String(primary.id));
      }
    });
  }, [orgId]);

  useEffect(() => {
    if ((!serviceId && !doctorId) || !branchId) {
      setDates([]); setSelectedDate(''); setSlots([]); setSelectedSlotId('');
      return;
    }
    const today = new Date();
    const from = isoDate(today);
    const to = isoDate(addDays(today, 30));
    adminApi.getAvailableSlots(orgId, serviceId || null, from, to, branchId, doctorId || null)
      .then((data) => {
        const free = data.slots || [];
        const dateSet = new Set(free.map((s) => s.date));
        const sorted = Array.from(dateSet).sort();
        setDates(sorted);
        if (sorted.length && !sorted.includes(selectedDate)) {
          setSelectedDate(sorted[0]);
        }
      })
      .catch(() => setDates([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceId, branchId, doctorId, orgId]);

  useEffect(() => {
    if (!selectedDate || (!serviceId && !doctorId) || !branchId) {
      setSlots([]); setSelectedSlotId('');
      return;
    }
    setSlotsBusy(true);
    adminApi.getAvailableSlots(orgId, serviceId || null, selectedDate, selectedDate, branchId, doctorId || null)
      .then((data) => {
        setSlots(data.slots || []);
        setSelectedSlotId('');
      })
      .catch(() => setSlots([]))
      .finally(() => setSlotsBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate, serviceId, branchId, doctorId, orgId]);

  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      return;
    }
    const t = setTimeout(() => {
      setSearchBusy(true);
      adminApi.searchClients(orgId, trimmed)
        .then((data) => setSearchResults(data.clients || []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchBusy(false));
    }, 300);
    return () => clearTimeout(t);
  }, [searchQuery, orgId]);

  function pickClient(client) {
    setSelectedClient(client);
    setPhone(client.phone || '');
    setFirstName(client.first_name || '');
    setLastName(client.last_name || '');
    setMiddleName(client.middle_name || '');
    setSearchResults([]);
    setSearchQuery('');
  }

  function clearSelectedClient() {
    setSelectedClient(null);
  }

  async function submit() {
    setError('');
    setInfoMsg('');
    if (!phone.trim()) { setError('Укажите телефон'); return; }
    if (!lastName.trim() || !firstName.trim()) { setError('Укажите фамилию и имя'); return; }
    if (!serviceId && !doctorId) {
      setError('Укажите услугу и/или специалиста');
      return;
    }
    if (!branchId) { setError('Выберите филиал'); return; }
    if (!selectedSlotId) { setError('Выберите время'); return; }

    setBusy(true);
    try {
      const basePayload = {
        phone,
        first_name: firstName,
        last_name: lastName,
        middle_name: middleName,
        service_id: serviceId,
        slot_id: selectedSlotId,
        slots_count_override: parseInt(slotsCount, 10) || 1,
      };
      if (selectedClient) basePayload.user_id = selectedClient.user_id;

      let r = await adminApi.createRequest(orgId, basePayload);

      // Двухфазный режим: лимит записей в день превышен — спрашиваем админа.
      if (r && r.ok === false && r.error_code === 'daily_limit_exceeded') {
        const confirmed = window.confirm(buildDailyLimitConfirmText(r));
        if (!confirmed) {
          setInfoMsg('Запись не создана — вы отменили подтверждение превышения лимита.');
          setBusy(false);
          return;
        }
        r = await adminApi.createRequest(orgId, { ...basePayload, confirm_over_daily_limit: true });
      }

      if (!r || r.ok === false) {
        setError((r && (r.message || r.note)) || 'Не удалось создать запись');
        return;
      }

      setResult(r);
      setStep('success');
      if (onCreated) onCreated(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const isSaving = busy;
  const noBranches = branches.length === 0;

  return (
    <div className="modal-backdrop" onClick={() => !isSaving && onClose()}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 560, width: '100%' }}
      >
        <h2 className="card-title">Создать запись</h2>

        {noBranches && (
          <div className="error-box" style={{ marginBottom: 12 }}>
            В организации нет филиалов. Сначала создайте филиал в разделе
            «Справочники → Филиалы», чтобы создавать записи.
          </div>
        )}

        {step === 'form' && !noBranches && (
          <>
            <div className="form-group">
              <label className="form-label">🔍 Найти клиента (ФИО или телефон)</label>
              <input
                className="form-input"
                type="text"
                placeholder="Иванов / 89123456789 / 4567"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                disabled={isSaving}
              />
              {searchBusy && <div className="create-req-search-hint">Поиск…</div>}
              {!searchBusy && searchQuery.trim().length >= 2 && searchResults.length === 0 && (
                <div className="create-req-search-hint">
                  Никого не нашли. Заполните поля ниже — создадим нового клиента.
                </div>
              )}
              {!selectedClient && searchResults.length > 0 && (
                <div className="create-req-search-results">
                  {searchResults.slice(0, 6).map((c) => (
                    <button
                      key={c.user_id}
                      type="button"
                      className="create-req-search-item"
                      onClick={() => pickClient(c)}
                    >
                      <div>
                        <b>{c.last_name} {c.first_name} {c.middle_name}</b>
                        {!c.has_max && <span className="create-req-tag">нет профиля</span>}
                      </div>
                      <div className="create-req-search-phone">{c.phone}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selectedClient && (
              <div className="create-req-selected">
                ✅ Выбран: <b>{selectedClient.last_name} {selectedClient.first_name}</b>
                {!selectedClient.has_max && ' (нет MAX-профиля)'}
                <button
                  type="button"
                  className="create-req-clear"
                  onClick={clearSelectedClient}
                >✕</button>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Телефон</label>
              <input
                className="form-input"
                type="tel"
                placeholder="+7 999 123-45-67"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={isSaving}
              />
            </div>

            <div className="form-row-2">
              <div className="form-group">
                <label className="form-label">Фамилия</label>
                <input
                  className="form-input"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  disabled={isSaving}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Имя</label>
                <input
                  className="form-input"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  disabled={isSaving}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Отчество (если есть)</label>
              <input
                className="form-input"
                value={middleName}
                onChange={(e) => setMiddleName(e.target.value)}
                disabled={isSaving}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Услуга (опционально)</label>
              <select
                className="form-input"
                value={serviceId}
                onChange={(e) => {
                  const newSid = e.target.value;
                  setServiceId(newSid);
                  const svc = services.find((s) => s.id === newSid);
                  if (svc && svc.duration_min) {
                    setSlotsCount(String(Math.max(1, Math.ceil(svc.duration_min / 30))));
                  } else {
                    setSlotsCount('1');
                  }
                }}
                disabled={isSaving}
              >
                <option value="">— Не указана —</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              {selectedService && (
                <div
                  style={{
                    marginTop: 8,
                    padding: '10px 12px',
                    background: 'var(--primary-soft)',
                    borderRadius: 8,
                    fontSize: 13,
                    color: 'var(--primary)',
                    lineHeight: 1.5,
                  }}
                >
                  <div>
                    <b>{selectedService.price} ₽</b> · {selectedService.duration_min} мин
                    {selectedService.buffer_min > 0 && ` + ${selectedService.buffer_min} мин буфер`}
                  </div>
                  {selectedService.prep && (
                    <div style={{ marginTop: 4, color: 'var(--text-muted)' }}>
                      Подготовка: {selectedService.prep}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="form-group">
              <label className="form-label">Сколько слотов занять</label>
              <input
                className="form-input"
                type="number"
                min="1"
                max="20"
                value={slotsCount}
                onChange={(e) => setSlotsCount(e.target.value)}
                disabled={isSaving}
              />
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                По умолчанию — по длительности услуги. Можно переопределить:
                например, для процедуры на 30 мин занять 3 слота (90 мин).
                Слоты должны идти подряд и быть свободны.
              </div>
            </div>

            {branches.length > 1 && (
              <div className="form-group">
                <label className="form-label">Филиал</label>
                <select
                  className="form-input"
                  value={branchId}
                  onChange={(e) => { setBranchId(e.target.value); setDoctorId(''); }}
                  disabled={isSaving}
                >
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}{b.is_primary ? ' 🏠' : ''}
                    </option>
                  ))}
                </select>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  По умолчанию — основной филиал. Если у специалиста смены только
                  в другом филиале — выберите его.
                </div>
              </div>
            )}

            {doctors.length > 0 && (
              <div className="form-group">
                <label className="form-label">Специалист</label>
                <select
                  className="form-input"
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  disabled={isSaving}
                >
                  <option value="">— любой —</option>
                  {sortedDoctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                      {d.services_count > 0 ? ` · ${d.services_count} усл.` : ' · все услуги'}
                    </option>
                  ))}
                </select>
                {branchId && (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    Сверху — специалисты, работающие в выбранном филиале.
                  </div>
                )}
              </div>
            )}

            {(serviceId || doctorId) && (
              <div className="form-group">
                <label className="form-label">Дата</label>
                {dates.length === 0 ? (
                  <div className="create-req-empty">
                    Нет свободных дат. Откройте «Расписание» и создайте слоты
                    в выбранном филиале.
                  </div>
                ) : (
                  <div className="create-req-dates">
                    {dates.slice(0, 20).map((d) => (
                      <button
                        key={d}
                        type="button"
                        className={'filter-btn' + (selectedDate === d ? ' active' : '')}
                        onClick={() => setSelectedDate(d)}
                        disabled={isSaving}
                      >
                        {humanDate(d)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedDate && (serviceId || doctorId) && (
              <div className="form-group">
                <label className="form-label">Время</label>
                {slotsBusy && <div className="loading" style={{ padding: 8 }}>Загрузка…</div>}
                {!slotsBusy && slots.length === 0 && (
                  <div className="create-req-empty">Нет свободных окон на эту дату.</div>
                )}
                {!slotsBusy && slots.length > 0 && (
                  <div className="create-req-slots">
                    {slots.filter((s) => !isPastSlot(s.date, s.time)).map((s) => {
                      const docName = s.doctor_id ? doctorNameById[s.doctor_id] : null;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          className={'filter-btn' + (selectedSlotId === s.id ? ' active' : '')}
                          onClick={() => setSelectedSlotId(s.id)}
                          disabled={isSaving}
                        >
                          {s.time}{docName ? ` · ${docName}` : ''}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {infoMsg && (
              <div
                style={{
                  marginTop: 12,
                  padding: '8px 12px',
                  background: '#fff4d9',
                  color: '#8b5a00',
                  borderRadius: 8,
                  fontSize: 13,
                }}
              >
                {infoMsg}
              </div>
            )}

            {error && <div className="form-error">{error}</div>}

            <div className="actions" style={{ marginTop: 16 }}>
              <button
                type="button"
                className="btn-action confirm"
                onClick={submit}
                disabled={isSaving}
              >
                {isSaving ? 'Создание…' : '✅ Создать запись'}
              </button>
              <button
                type="button"
                className="btn-action reject"
                onClick={onClose}
                disabled={isSaving}
              >
                Отмена
              </button>
            </div>
          </>
        )}

        {step === 'success' && result && (
          <div>
            <div className="success" style={{ padding: '20px 8px' }}>
              <div className="success-icon">✓</div>
              <h2 style={{ margin: '8px 0' }}>Запись создана</h2>
              <p style={{ color: 'var(--text-muted)' }}>
                Номер заявки: <b>#{result.id}</b>
              </p>
            </div>
            {(() => {
              const n = notifyMessage(result);
              return (
                <div className={'create-req-notify-hint create-req-notify-' + n.cls}>
                  {n.text}
                </div>
              );
            })()}
            <div className="actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn-action confirm"
                onClick={onClose}
              >
                Закрыть
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}