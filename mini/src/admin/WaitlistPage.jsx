import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const STATUS_LABELS = {
  active: '🟢 Активна',
  fulfilled: '✅ Выполнена',
  cancelled: '❌ Отменена',
  expired: '⏳ Истекла',
};

const STATUS_CLASS = {
  active: 'pending',
  fulfilled: 'confirmed',
  cancelled: 'cancelled',
  expired: 'cancelled',
};

const PREFERRED_LABELS = {
  morning: '🌅 Утро',
  afternoon: '☀️ День',
  evening: '🌇 Вечер',
  any: '🕐 Любое',
};

const STATUS_FILTERS = [
  { id: 'active', label: 'Активные' },
  { id: '', label: 'Все' },
  { id: 'fulfilled', label: '✅ Выполнены' },
  { id: 'cancelled', label: '❌ Отменены' },
  { id: 'expired', label: '⏳ Истекли' },
];

function humanDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  const months = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
  return `${d} ${months[m - 1]}`;
}

function humanTs(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.replace(' ', 'T'));
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth()+1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return iso; }
}

export default function WaitlistPage({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [entries, setEntries] = useState([]);
  const [statusFilter, setStatusFilter] = useState('active');
  const [services, setServices] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);

  async function load() {
    setStep('loading');
    setError('');
    try {
      const data = await adminApi.getWaitlist(orgId, {
        status: statusFilter || undefined,
        limit: 200,
      });
      setEntries(data.entries || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  async function loadServices() {
    try {
      const d = await adminApi.getServices(orgId);
      setServices((d.services || []).filter((s) => s.active));
    } catch (e) {}
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId, statusFilter]);
  useEffect(() => { loadServices(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleNotify(wid) {
    setBusyId('notify_' + wid);
    try {
      await adminApi.notifyWaitlist(orgId, wid);
      await load();
    } catch (e) {
      alert('Не удалось уведомить: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleFulfill(wid) {
    if (!window.confirm('Пометить заявку как выполненную?')) return;
    setBusyId('fulfill_' + wid);
    try {
      await adminApi.fulfillWaitlist(orgId, wid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleCancel(wid) {
    if (!window.confirm('Удалить заявку из листа?')) return;
    setBusyId('cancel_' + wid);
    try {
      await adminApi.cancelWaitlist(orgId, wid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (step === 'loading') return <div className="loading">Загрузка…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setCreating(true)}
      >
        ➕ Добавить в лист
      </button>

      <div className="filters-scroll">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id || 'all'}
            className={'filter-btn' + (statusFilter === f.id ? ' active' : '')}
            onClick={() => setStatusFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!entries.length && (
        <div className="dash-empty">
          Заявок нет.
        </div>
      )}

      {entries.map((e) => {
        const fio = [e.client_last_name, e.client_first_name, e.client_middle_name]
          .filter(Boolean).join(' ') || '—';
        const isActive = e.status === 'active';
        return (
          <div
            key={e.id}
            className="dir-item"
            style={{ flexDirection: 'column', alignItems: 'stretch' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div className="dir-main">
                <div className="dir-title">
                  {e.service_name}
                  <span
                    className={`status status-${STATUS_CLASS[e.status] || 'pending'}`}
                    style={{ marginLeft: 8 }}
                  >
                    {STATUS_LABELS[e.status] || e.status}
                  </span>
                </div>
                <div className="dir-meta">
                  📅 {humanDate(e.date_from)} — {humanDate(e.date_to)}
                  {e.preferred_time && ` · ${PREFERRED_LABELS[e.preferred_time] || e.preferred_time}`}
                </div>
                {e.doctor_name && <div className="dir-meta">👤 {e.doctor_name}</div>}
                {e.branch_name && <div className="dir-meta">🏢 {e.branch_name}</div>}
                <div className="dir-meta">
                  Клиент: <b>{fio}</b>
                  {e.client_phone && ` · ${e.client_phone}`}
                  {!e.has_max && <span className="tag tag-muted" style={{ marginLeft: 6 }}>нет MAX</span>}
                </div>
                {e.notes && <div className="dir-meta" style={{ fontSize: 12 }}>📝 {e.notes}</div>}
                {e.notified_count > 0 && (
                  <div className="dir-meta" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Уведомляли {e.notified_count} раз
                    {e.notified_at && `, последний — ${humanTs(e.notified_at)}`}
                  </div>
                )}
              </div>
            </div>

            {isActive && (
              <div className="actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
                <button
                  className="btn-action"
                  onClick={() => handleNotify(e.id)}
                  disabled={busyId === 'notify_' + e.id || !e.has_max}
                  title={!e.has_max ? 'У клиента нет MAX' : 'Найти ближайший свободный слот и отправить уведомление'}
                  style={{ flex: 1, minWidth: 110 }}
                >
                  {busyId === 'notify_' + e.id ? '…' : '🔔 Уведомить'}
                </button>
                <button
                  className="btn-action confirm"
                  onClick={() => handleFulfill(e.id)}
                  disabled={busyId === 'fulfill_' + e.id}
                  style={{ flex: 1, minWidth: 110 }}
                >
                  {busyId === 'fulfill_' + e.id ? '…' : '✅ Выполнено'}
                </button>
                <button
                  className="btn-action"
                  onClick={() => setEditing(e)}
                  style={{ flex: 1, minWidth: 80 }}
                  title="Редактировать"
                >
                  ✏️
                </button>
                <button
                  className="btn-action reject"
                  onClick={() => handleCancel(e.id)}
                  disabled={busyId === 'cancel_' + e.id}
                  style={{ flex: '0 0 60px' }}
                  title="Удалить"
                >
                  {busyId === 'cancel_' + e.id ? '…' : '🗑'}
                </button>
              </div>
            )}
          </div>
        );
      })}

      {creating && (
        <WaitlistEditModal
          orgId={orgId}
          services={services}
          onClose={() => setCreating(false)}
          onSaved={async () => { setCreating(false); await load(); }}
        />
      )}

      {editing && (
        <WaitlistEditModal
          orgId={orgId}
          services={services}
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await load(); }}
        />
      )}
    </div>
  );
}

function WaitlistEditModal({ orgId, services, initial, onClose, onSaved }) {
  const isEdit = !!initial;

  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);

  const [phone, setPhone] = useState(initial?.client_phone || '');
  const [firstName, setFirstName] = useState(initial?.client_first_name || '');
  const [lastName, setLastName] = useState(initial?.client_last_name || '');
  const [middleName, setMiddleName] = useState(initial?.client_middle_name || '');

  const [serviceId, setServiceId] = useState(initial?.service_id || '');
  const [doctorId, setDoctorId] = useState(initial?.doctor_id ? String(initial.doctor_id) : '');
  const [dateFrom, setDateFrom] = useState(initial?.date_from || '');
  const [dateTo, setDateTo] = useState(initial?.date_to || '');
  const [preferred, setPreferred] = useState(initial?.preferred_time || 'any');
  const [notes, setNotes] = useState(initial?.notes || '');

  const [doctors, setDoctors] = useState([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    adminApi.getDoctorsByOrg(orgId)
      .then((d) => setDoctors(d.doctors || []))
      .catch(() => {});
  }, [orgId]);

  useEffect(() => {
    if (isEdit || selectedClient) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) { setSearchResults([]); return; }
    const t = setTimeout(() => {
      setSearchBusy(true);
      adminApi.searchClients(orgId, trimmed)
        .then((d) => setSearchResults(d.clients || []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchBusy(false));
    }, 300);
    return () => clearTimeout(t);
  }, [query, orgId, isEdit, selectedClient]);

  function pickClient(c) {
    setSelectedClient(c);
    setPhone(c.phone || '');
    setFirstName(c.first_name || '');
    setLastName(c.last_name || '');
    setMiddleName(c.middle_name || '');
    setSearchResults([]);
    setQuery('');
  }

  function clearClient() {
    setSelectedClient(null);
  }

  async function submit() {
    setError('');
    if (!serviceId && !doctorId) {
      setError('Укажите услугу и/или специалиста');
      return;
    }
    if (!dateFrom || !dateTo) { setError('Укажите период'); return; }
    if (dateTo < dateFrom) { setError('«По дату» не может быть раньше «С даты»'); return; }
    if (!isEdit && !selectedClient && !phone.trim()) {
      setError('Выберите клиента или укажите телефон');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        service_id: serviceId,
        doctor_id: doctorId ? parseInt(doctorId, 10) : null,
        date_from: dateFrom,
        date_to: dateTo,
        preferred_time: preferred === 'any' ? null : preferred,
        notes,
      };
      if (!isEdit) {
        if (selectedClient) {
          payload.user_id = selectedClient.user_id;
        } else {
          payload.phone = phone.trim();
          payload.first_name = firstName.trim();
          payload.last_name = lastName.trim();
          payload.middle_name = middleName.trim();
        }
        await adminApi.createWaitlist(orgId, payload);
      } else {
        await adminApi.updateWaitlist(orgId, initial.id, payload);
      }
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
        <h2 className="card-title">
          {isEdit ? `Редактировать заявку #${initial.id}` : 'Новая заявка в лист'}
        </h2>

        {!isEdit && (
          <>
            <div className="form-group">
              <label className="form-label">🔍 Найти клиента (ФИО или телефон)</label>
              <input
                className="form-input"
                type="text"
                placeholder="Иванов / 89123456789 / 4567"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={busy || !!selectedClient}
              />
              {searchBusy && <div className="create-req-search-hint">Поиск…</div>}
              {!searchBusy && query.trim().length >= 2 && searchResults.length === 0 && (
                <div className="create-req-search-hint">
                  Никого не нашли — заполните поля ниже, создадим нового клиента.
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
                        {!c.has_max && <span className="create-req-tag">нет MAX</span>}
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
                {!selectedClient.has_max && ' (нет MAX)'}
                <button type="button" className="create-req-clear" onClick={clearClient}>✕</button>
              </div>
            )}

            {!selectedClient && (
              <>
                <div className="form-group">
                  <label className="form-label">Телефон</label>
                  <input
                    className="form-input"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    disabled={busy}
                    placeholder="+7 999 123-45-67"
                  />
                </div>
                <div className="form-row-2">
                  <div className="form-group">
                    <label className="form-label">Фамилия</label>
                    <input
                      className="form-input"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Имя</label>
                    <input
                      className="form-input"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Отчество (если есть)</label>
                  <input
                    className="form-input"
                    value={middleName}
                    onChange={(e) => setMiddleName(e.target.value)}
                    disabled={busy}
                  />
                </div>
              </>
            )}
          </>
        )}

        <div className="form-group">
          <label className="form-label">Услуга (опционально)</label>
          <select
            className="form-input"
            value={serviceId}
            onChange={(e) => setServiceId(e.target.value)}
            disabled={busy}
          >
            <option value="">— Не важно / любая —</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Если не выбрана, а выбран специалист — уведомим, когда у него освободится
            любой слот.
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Специалист (опционально)</label>
          <select
            className="form-input"
            value={doctorId}
            onChange={(e) => setDoctorId(e.target.value)}
            disabled={busy || !doctors.length}
          >
            <option value="">— Любой, кто оказывает услугу —</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Если выбрать специалиста — уведомления будут только по его слотам.
            Если оставить «Любой» — предложим любого, кто оказывает услугу.
          </div>
        </div>

        <div className="form-row-2">
          <div className="form-group">
            <label className="form-label">С даты</label>
            <input
              className="form-input"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="form-group">
            <label className="form-label">По дату</label>
            <input
              className="form-input"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              disabled={busy}
            />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Удобное время</label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { id: 'any', label: 'Любое' },
              { id: 'morning', label: 'Утро' },
              { id: 'afternoon', label: 'День' },
              { id: 'evening', label: 'Вечер' },
            ].map((p) => (
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

        <div className="form-group">
          <label className="form-label">Заметка (для админа)</label>
          <textarea
            className="form-input"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={busy}
            maxLength={500}
            placeholder="Например: клиент готов приехать даже утром в субботу"
          />
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={submit} disabled={busy}>
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