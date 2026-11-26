import { useEffect, useRef, useState } from 'react';
import { adminApi } from './adminApi.js';
import ClientMessageModal from './ClientMessageModal.jsx';
import ClientPrivacyModal from './ClientPrivacyModal.jsx';
import VisitDetailsModal from './VisitDetailsModal.jsx';

const STATUS_LABELS = {
  pending: 'ожидает',
  confirmed: 'подтверждена',
  cancelled: 'отменена',
  done: 'пришёл',
  no_show: 'не пришёл',
};

const STATUS_BADGE = {
  active:   { text: '🟢 Активный', bg: '#e3f5e9', color: '#1f5f36' },
  at_risk:  { text: '🟡 Под риском', bg: '#fff4d9', color: '#8b5a00' },
  lost:     { text: '🔴 Потерянный', bg: '#fdecec', color: '#a83c3c' },
  never:    { text: '⚪ Новый', bg: '#f0f2f5', color: '#6b7280' },
};

const HISTORY_FILTERS = [
  { id: 'all', label: 'Все' },
  { id: 'pending', label: '🟡 Ожидает' },
  { id: 'confirmed', label: '🔵 Подтверждена' },
  { id: 'done', label: '✅ Пришёл' },
  { id: 'no_show', label: '🚫 Не пришёл' },
  { id: 'cancelled', label: '❌ Отменён' },
];

const STATUS_CLASS_MAP = {
  pending: 'pending', confirmed: 'confirmed', cancelled: 'cancelled',
  done: 'confirmed', no_show: 'cancelled',
};

function humanTs(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.replace(' ', 'T'));
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return iso; }
}

export default function ClientCardModal({ orgId, userId, onClose, onChanged }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [reviewStats, setReviewStats] = useState(null);
  const [photoUploading, setPhotoUploading] = useState(false);

  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState([]);
  const [tagInput, setTagInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [busyAction, setBusyAction] = useState(null);

  const [expandedServices, setExpandedServices] = useState({});
  const [historyFilter, setHistoryFilter] = useState('all');
  const [messageOpen, setMessageOpen] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportBusy, setExportBusy] = useState(null);
  const [exportMsg, setExportMsg] = useState('');
  const [exportTarget, setExportTarget] = useState('admin');

  const [visitDetails, setVisitDetails] = useState(null);
  const photoInputRef = useRef(null);

  async function load() {
    setStep('loading');
    try {
      const d = await adminApi.getClientCard(orgId, userId);
      setData(d);
      setNotes(d.notes || '');
      setTags(d.tags || []);
      setStep('ready');
      adminApi.getClientReviews(orgId, userId)
        .then((r) => setReviewStats(r))
        .catch(() => setReviewStats(null));
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId, userId]);

  async function handlePhotoUpload(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (photoInputRef.current) photoInputRef.current.value = '';
    if (!f.type || !['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'].includes(f.type)) {
      alert('Только JPEG/PNG/WebP/GIF');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      alert('Файл больше 10 МБ');
      return;
    }
    setPhotoUploading(true);
    try {
      const r = await adminApi.uploadClientPhoto(orgId, userId, f);
      setData((d) => ({ ...d, photo_url: r.photo_url }));
      if (onChanged) onChanged();
    } catch (e2) {
      alert('Ошибка загрузки: ' + e2.message);
    } finally {
      setPhotoUploading(false);
    }
  }

  async function handlePhotoDelete() {
    if (!window.confirm('Удалить фото клиента?')) return;
    setPhotoUploading(true);
    try {
      await adminApi.deleteClientPhoto(orgId, userId);
      setData((d) => ({ ...d, photo_url: null }));
      if (onChanged) onChanged();
    } catch (e) {
      alert('Ошибка удаления: ' + e.message);
    } finally {
      setPhotoUploading(false);
    }
  }

  function addTag() {
    const t = tagInput.trim().slice(0, 50);
    if (!t || tags.includes(t) || tags.length >= 20) { setTagInput(''); return; }
    setTags([...tags, t]);
    setTagInput('');
    setSaveMsg('');
  }

  function removeTag(t) {
    setTags(tags.filter((x) => x !== t));
    setSaveMsg('');
  }

  async function handleSaveCard() {
    setSaving(true);
    setSaveMsg('');
    try {
      await adminApi.updateClientCard(orgId, userId, { notes, tags });
      setSaveMsg('✅ Сохранено');
      if (onChanged) onChanged();
    } catch (e) {
      setSaveMsg('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleResetNoShow() {
    if (!window.confirm('Сбросить счётчик неявок?')) return;
    setBusyAction('reset');
    try {
      await adminApi.resetClientNoShow(orgId, userId);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleToggleMarketing() {
    if (!data) return;
    const newVal = !data.marketing_opt_out;
    if (!window.confirm(newVal ? 'Отписать от рассылок?' : 'Вернуть в рассылки?')) return;
    setBusyAction('marketing');
    try {
      await adminApi.setMarketingOptOut(orgId, userId, newVal);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleToggleBlock() {
    if (!data) return;
    const newVal = !data.blocked;
    if (!window.confirm(newVal ? 'Заблокировать клиента?' : 'Разблокировать клиента?')) return;
    let reason = '';
    if (newVal) {
      const input = window.prompt('Причина блокировки (необязательно):', '');
      if (input === null) return;
      reason = input;
    }
    setBusyAction('block');
    try {
      if (newVal) await adminApi.blockClient(orgId, userId, reason);
      else await adminApi.unblockClient(orgId, userId);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCancelRequest(requestId) {
    if (!window.confirm('Отменить запись?')) return;
    setBusyAction('cancel_' + requestId);
    try {
      await adminApi.rejectRequest(orgId, requestId);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleExport(format) {
    if (exportTarget === 'client') {
      if (isPhoneOnly) {
        setExportMsg('❌ У клиента нет MAX-профиля');
        return;
      }
      if (data && data.blocked) {
        setExportMsg('❌ Клиент заблокирован');
        return;
      }
      if (!window.confirm(`Отправить файл клиенту ${fullName}?`)) {
        return;
      }
    }
    setExportBusy(format);
    setExportMsg('');
    try {
      const r = await adminApi.exportClientFile(orgId, userId, format, exportTarget);
      if (r && r.ok) {
        if (exportTarget === 'client') {
          if (r.sent_to_chat) {
            setExportMsg(`✅ Файл отправлен клиенту ${fullName} в MAX.`);
          } else {
            setExportMsg(`⚠️ Не удалось отправить клиенту (${r.send_error || 'ошибка'}). Ссылка: ${r.full_url}`);
          }
        } else {
          if (r.sent_to_chat) {
            setExportMsg(`✅ Файл отправлен в чат MAX. Откройте сообщения от бота.`);
          } else {
            setExportMsg(`⚠️ Отправка в чат не удалась. Скачать: ${r.full_url}`);
          }
        }
      } else {
        setExportMsg('❌ Не удалось сформировать файл');
      }
    } catch (e) {
      setExportMsg('❌ ' + e.message);
    } finally {
      setExportBusy(null);
    }
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

  if (!data) return null;

  const fullName = [data.last_name, data.first_name, data.middle_name].filter(Boolean).join(' ') || '—';
  const agg = data.aggregates;
  const statusBadge = STATUS_BADGE[data.status_label] || STATUS_BADGE.never;
  const isPhoneOnly = String(data.user_id || '').startsWith('phone:');

  // Плоский список всех визитов. Берём из services_list (там точно есть),
  // fallback на data.history.
  const flatFromServices = (data.services_list || []).flatMap((svc) =>
    (svc.visits || []).map((v) => ({ ...v, service_name: svc.service_name }))
  );
  const flatHistory = flatFromServices.length > 0 ? flatFromServices : (data.history || []);
  const filteredHistory = historyFilter === 'all'
    ? flatHistory
    : flatHistory.filter((h) => String(h.status || '') === historyFilter);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal client-card-print" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 760 }}>

        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', marginBottom: 12 }}>
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <div
              onClick={() => !photoUploading && photoInputRef.current?.click()}
              title={data.photo_url ? 'Нажмите, чтобы заменить фото' : 'Нажмите, чтобы загрузить фото'}
              style={{
                width: 84, height: 84, borderRadius: '50%',
                border: '2px solid var(--border)',
                background: data.photo_url ? 'var(--bg)' : 'var(--primary-soft)',
                color: 'var(--primary)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: data.photo_url ? 0 : 32, fontWeight: 600,
                overflow: 'hidden', cursor: photoUploading ? 'wait' : 'pointer',
                position: 'relative',
              }}
            >
              {data.photo_url ? (
                <img
                  src={data.photo_url}
                  alt={fullName}
                  style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                />
              ) : (
                [data.first_name, data.last_name].filter(Boolean).map((x) => x[0]).join('').toUpperCase() || '👤'
              )}
              {photoUploading && (
                <div
                  style={{
                    position: 'absolute', inset: 0,
                    background: 'rgba(0,0,0,0.45)', color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11,
                  }}
                >
                  …
                </div>
              )}
            </div>
            {data.photo_url && !photoUploading && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); handlePhotoDelete(); }}
                title="Удалить фото"
                style={{
                  position: 'absolute', top: -2, right: -2,
                  width: 24, height: 24, borderRadius: '50%',
                  background: '#fff', border: '1px solid var(--border)',
                  color: 'var(--danger)', cursor: 'pointer',
                  fontSize: 12, lineHeight: 1, padding: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
                }}
              >
                ✕
              </button>
            )}
            <input
              ref={photoInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handlePhotoUpload}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 className="card-title" style={{ marginBottom: 4 }}>
              {fullName}
              <span className="tag" style={{ marginLeft: 8, ...statusBadge }}>{statusBadge.text}</span>
              {(data.channels || []).length > 0 && (
                <span className="tag tag-muted" style={{ marginLeft: 8 }}>
                  {(data.channels || []).map((p) => p.toUpperCase()).join('+')}
                </span>
              )}
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0' }}>
              {data.phone || '—'}
              {data.blocked && <span className="tag" style={{ marginLeft: 8, background: '#fdecec', color: '#a83c3c' }}>🚫 заблокирован</span>}
              {data.marketing_opt_out && <span className="tag tag-muted" style={{ marginLeft: 8 }}>🚫 отписан</span>}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          {!isPhoneOnly && (
            <button className="btn-action confirm" style={{ flex: '0 0 auto', padding: '10px 14px' }} onClick={() => setMessageOpen(true)}>
              ✉️ Написать
            </button>
          )}
          <button className="btn-action" style={{ flex: '0 0 auto', padding: '10px 14px' }} onClick={() => setExportOpen(true)}>
            📥 Экспорт
          </button>
          <button className="btn-action" style={{ flex: '0 0 auto', padding: '10px 14px' }} onClick={() => setPrivacyOpen(true)}>
            🔒 Данные (152-ФЗ)
          </button>
        </div>

        <div className="dash-cards" style={{ marginBottom: 16 }}>
          <div className="dash-card dash-card-done">
            <div className="dash-card-label">✅ Визитов</div>
            <div className="dash-card-value">{agg.visits_done}</div>
          </div>
          <div className="dash-card dash-card-noshow">
            <div className="dash-card-label">🚫 Неявок</div>
            <div className="dash-card-value">{agg.visits_no_show}</div>
          </div>
          <div className="dash-card dash-card-revenue">
            <div className="dash-card-label">💰 Выручка</div>
            <div className="dash-card-value">{agg.total_revenue} ₽</div>
          </div>
        </div>

        {reviewStats && reviewStats.total > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 15, marginBottom: 8, marginTop: 0 }}>
              ⭐ Отзывы клиента
            </h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: 12, background: 'var(--bg)', borderRadius: 10 }}>
              <div style={{ textAlign: 'center', minWidth: 80 }}>
                <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--primary)' }}>
                  {reviewStats.avg_rating.toFixed(1)}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  из 5 · {reviewStats.total} отзыв{reviewStats.total === 1 ? '' : reviewStats.total < 5 ? 'а' : 'ов'}
                </div>
              </div>
              <div style={{ flex: 1 }}>
                {[5, 4, 3, 2, 1].map((r) => {
                  const count = reviewStats.distribution[String(r)] || 0;
                  const pct = reviewStats.total > 0 ? (count / reviewStats.total * 100) : 0;
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
            {reviewStats.recent.length > 0 && (
              <div style={{ marginTop: 8 }}>
                {reviewStats.recent.map((rv) => (
                  <div key={rv.id} style={{ padding: '8px 12px', background: 'var(--bg)', borderRadius: 8, marginBottom: 4, fontSize: 13 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                      <span style={{ fontWeight: 600 }}>
                        {'⭐'.repeat(rv.rating)}{'☆'.repeat(5 - rv.rating)}
                      </span>
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                        {humanTs(rv.created_at)}
                      </span>
                    </div>
                    {rv.comment && <div style={{ color: 'var(--text)' }}>{rv.comment}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
          <div><b>Пол:</b> {data.gender === 'male' ? 'Мужской' : data.gender === 'female' ? 'Женский' : '—'}</div>
          <div><b>Дата рождения:</b> {data.birth_date || '—'}</div>
          <div><b>Любимый специалист:</b> {data.favorite_doctor_name || '—'}</div>
          {data.specialists_list && data.specialists_list.length > 0 && (
            <div>
              <b>Посещённые специалисты:</b>{' '}
              {data.specialists_list.map((s) => `${s.name} (${s.visits})`).join(', ')}
            </div>
          )}
          <div>
            <b>Согласие 152-ФЗ:</b>{' '}
            {data.consent_152fz ? `✅ да (${humanTs(data.consent_given_at)})` : '— не дано'}
          </div>
          <div><b>Последний визит:</b> {agg.last_done_at ? humanTs(agg.last_done_at) : '—'}</div>
          {data.no_show_count > 0 && (
            <div>
              <b>Неявок всего:</b> {data.no_show_count}
              {data.no_show_last_at && ` · последняя ${humanTs(data.no_show_last_at)}`}{' '}
              <button className="btn-link" style={{ fontSize: 12, padding: 0 }} onClick={handleResetNoShow} disabled={busyAction === 'reset'}>
                {busyAction === 'reset' ? '…' : '↺ Сбросить'}
              </button>
            </div>
          )}
        </div>

        {data.upcoming && data.upcoming.length > 0 && (
          <div className="upcoming-block" style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 15, marginBottom: 8, marginTop: 0 }}>📅 Предстоящие записи</h3>
            {data.upcoming.map((u) => (
              <div key={u.id} className="upcoming-item"
                onClick={() => setVisitDetails({
                  visit: { ...u, actual_amount: null, payment_method: null, done_auto: false },
                  serviceName: u.service_name,
                })}>
                <div className="upcoming-item-main">
                  <div className="upcoming-item-title">#{u.id} · {u.service_name}</div>
                  <div className="upcoming-item-meta">
                    {humanTs(u.scheduled_at)}{u.doctor ? ` · ${u.doctor}` : ''}
                    {u.slots_count > 1 ? ` · ${u.slots_count} слота` : ''}
                  </div>
                </div>
                <div className="upcoming-item-actions">
                  <span className={`status status-${u.status === 'confirmed' ? 'confirmed' : 'pending'}`}>
                    {STATUS_LABELS[u.status] || u.status}
                  </span>
                  <button className="dir-btn danger"
                    onClick={(e) => { e.stopPropagation(); handleCancelRequest(u.id); }}
                    disabled={busyAction === 'cancel_' + u.id} title="Отменить запись">
                    {busyAction === 'cancel_' + u.id ? '…' : '❌'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="form-group">
          <label className="form-label">📝 Заметки администратора</label>
          <textarea className="form-input" rows={3}
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setSaveMsg(''); }}
            placeholder="Аллергия на латекс, боится боли..." disabled={saving} maxLength={5000} />
        </div>

        <div className="form-group">
          <label className="form-label">🏷 Теги</label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            {tags.map((t) => (
              <span key={t} className="tag tag-muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                {t}
                <button type="button" style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, padding: 0, color: 'inherit' }}
                  onClick={() => removeTag(t)} disabled={saving}>✕</button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="form-input" type="text" value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
              placeholder="VIP, сложный..." maxLength={50} disabled={saving} style={{ flex: 1 }} />
            <button type="button" className="btn-action confirm" onClick={addTag}
              disabled={saving || !tagInput.trim() || tags.length >= 20}
              style={{ flex: '0 0 auto', minWidth: 80 }}>+ Добавить</button>
          </div>
        </div>

        {saveMsg && <div style={{ color: saveMsg.startsWith('✅') ? 'var(--accent)' : 'var(--danger)', fontSize: 13, marginBottom: 12 }}>{saveMsg}</div>}

        <div className="actions" style={{ marginBottom: 16 }}>
          <button className="btn-action confirm" onClick={handleSaveCard} disabled={saving}>
            {saving ? 'Сохранение…' : '💾 Сохранить карточку'}
          </button>
        </div>

        <h3 style={{ fontSize: 15, marginBottom: 8 }}>📋 История визитов</h3>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          {HISTORY_FILTERS.map((f) => (
            <button key={f.id} type="button"
              className={'filter-btn' + (historyFilter === f.id ? ' active' : '')}
              onClick={() => setHistoryFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>

        {historyFilter === 'all' && data.services_list && data.services_list.length > 0 && (
          <div>
            {data.services_list.map((svc) => {
              const isExpanded = !!expandedServices[svc.service_name];
              return (
                <div key={svc.service_name} className="service-group-in-card">
                  <button type="button"
                    onClick={() => setExpandedServices((m) => ({ ...m, [svc.service_name]: !isExpanded }))}
                    className="service-group-in-card-header">
                    <span><b>{isExpanded ? '▼' : '▶'} {svc.service_name}</b></span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {svc.visits_total} визит{svc.visits_total === 1 ? '' : svc.visits_total < 5 ? 'а' : 'ов'}
                      {svc.total_amount > 0 && ` · ${svc.total_amount} ₽`}
                    </span>
                  </button>
                  {isExpanded && (
                    <div style={{ padding: '4px 12px 10px' }}>
                      {svc.visits.map((v) => (
                        <div key={v.id} className="dir-item visit-clickable"
                          onClick={() => setVisitDetails({ visit: v, serviceName: svc.service_name })}>
                          <div className="dir-main">
                            <div className="dir-title" style={{ fontSize: 13 }}>
                              #{v.id} · {humanTs(v.scheduled_at)}
                              {v.done_auto && <span className="tag" style={{ marginLeft: 6, background: '#fff4d9', color: '#8b5a00' }}>⚠️ авто</span>}
                            </div>
                            <div className="dir-meta" style={{ fontSize: 12 }}>
                              {v.doctor || '—'}{v.actual_amount != null && ` · 💰 ${v.actual_amount} ₽`}
                            </div>
                          </div>
                          <span className={`status status-${STATUS_CLASS_MAP[v.status] || 'pending'}`}>
                            {STATUS_LABELS[v.status] || v.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {historyFilter !== 'all' && filteredHistory.length > 0 && (
          <div>
            {filteredHistory.map((h) => (
              <div key={h.id} className="dir-item visit-clickable"
                onClick={() => setVisitDetails({ visit: h, serviceName: h.service_name })}>
                <div className="dir-main">
                  <div className="dir-title" style={{ fontSize: 14 }}>#{h.id} · {h.service_name}</div>
                  <div className="dir-meta">
                    {humanTs(h.scheduled_at)}{h.doctor && ` · ${h.doctor}`}
                    {h.actual_amount != null && ` · 💰 ${h.actual_amount} ₽`}
                  </div>
                </div>
                <span className={`status status-${STATUS_CLASS_MAP[h.status] || 'pending'}`}>
                  {STATUS_LABELS[h.status] || h.status}
                </span>
              </div>
            ))}
          </div>
        )}

        {historyFilter !== 'all' && filteredHistory.length === 0 && (
          <div className="create-req-empty">
            Нет записей со статусом «{STATUS_LABELS[historyFilter] || historyFilter}».
            {flatHistory.length > 0 && (
              <div style={{ fontSize: 12, marginTop: 6, color: 'var(--text-muted)' }}>
                Всего визитов: {flatHistory.length}. Статусы в истории:{' '}
                {[...new Set(flatHistory.map((h) => h.status))].join(', ')}.
              </div>
            )}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
          <button className="btn-link" style={{ fontSize: 13 }}
            onClick={handleToggleMarketing} disabled={busyAction === 'marketing'}>
            {data.marketing_opt_out ? '↩ Вернуть в рассылки' : '🚫 Отписать от рассылок'}
          </button>
          <button className="btn-link" style={{ fontSize: 13, color: data.blocked ? 'var(--accent)' : 'var(--danger)' }}
            onClick={handleToggleBlock} disabled={busyAction === 'block'}>
            {data.blocked ? '↩ Разблокировать' : '🚫 Заблокировать'}
          </button>
        </div>

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>

      {messageOpen && (
        <ClientMessageModal orgId={orgId} userId={userId} clientName={fullName}
          onClose={() => setMessageOpen(false)} />
      )}

      {privacyOpen && (
        <ClientPrivacyModal orgId={orgId} userId={userId} clientName={fullName}
          onClose={() => setPrivacyOpen(false)}
          onDeleted={async () => { if (onChanged) onChanged(); onClose(); }} />
      )}

      {visitDetails && (
        <VisitDetailsModal visit={visitDetails.visit} serviceName={visitDetails.serviceName}
          onClose={() => setVisitDetails(null)} />
      )}

            {exportOpen && (
        <div className="modal-backdrop" onClick={() => !exportBusy && setExportOpen(false)} style={{ zIndex: 200 }}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <h2 className="card-title">📥 Экспорт данных</h2>

            <div style={{ marginBottom: 16 }}>
              <div className="form-label" style={{ marginBottom: 8 }}>Кому отправить файл</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  type="button"
                  className={'filter-btn' + (exportTarget === 'admin' ? ' active' : '')}
                  onClick={() => { setExportTarget('admin'); setExportMsg(''); }}
                  disabled={!!exportBusy}
                  style={{ flex: 1 }}
                >
                  👤 Себе
                </button>
                <button
                  type="button"
                  className={'filter-btn' + (exportTarget === 'client' ? ' active' : '')}
                  onClick={() => { setExportTarget('client'); setExportMsg(''); }}
                  disabled={!!exportBusy || isPhoneOnly || (data && data.blocked)}
                  style={{ flex: 1 }}
                  title={
                    isPhoneOnly ? 'У клиента нет MAX-профиля'
                    : (data && data.blocked) ? 'Клиент заблокирован'
                    : 'Отправить в чат клиенту'
                  }
                >
                  📨 Клиенту
                </button>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
                {exportTarget === 'admin'
                  ? 'Файл придёт вам в чат MAX. Полный экспорт с внутренними данными (заметки, теги, счётчик неявок).'
                  : 'Файл придёт клиенту в чат MAX. Без внутренних данных — только его визиты и суммы.'}
              </div>
            </div>

            <div className="actions" style={{ flexDirection: 'column', gap: 8 }}>
              <button
                type="button"
                className="btn-action confirm"
                onClick={() => handleExport('csv')}
                disabled={!!exportBusy || exportTarget === 'client'}
                title={exportTarget === 'client' ? 'Клиенту CSV недоступен — только PDF и XLSX' : undefined}
              >
                {exportBusy === 'csv' ? 'Отправка…' : '📄 CSV (Excel, Google Sheets)'}
              </button>
              <button type="button" className="btn-action confirm" onClick={() => handleExport('xlsx')} disabled={!!exportBusy}>
                {exportBusy === 'xlsx' ? 'Отправка…' : '📊 XLSX (с форматированием)'}
              </button>
              <button type="button" className="btn-action confirm" onClick={() => handleExport('pdf')} disabled={!!exportBusy}>
                {exportBusy === 'pdf' ? 'Отправка…' : '📕 PDF (для печати)'}
              </button>
              <button type="button" className="btn-action reject" onClick={() => setExportOpen(false)} disabled={!!exportBusy}>
                Закрыть
              </button>
            </div>

            {exportMsg && (
              <div style={{
                marginTop: 12,
                fontSize: 13,
                color: exportMsg.startsWith('✅') ? 'var(--accent)'
                     : exportMsg.startsWith('⚠️') ? '#8b5a00' : 'var(--danger)',
                wordBreak: 'break-all',
              }}>
                {exportMsg}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}