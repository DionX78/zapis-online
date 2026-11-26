import { useEffect, useRef, useState } from 'react';
import { adminApi } from './adminApi.js';

const ACTIVITY_OPTIONS = [
  { id: 'all', label: 'Все клиенты' },
  { id: 'active_recent', label: 'Активные (по настройке)' },
  { id: 'at_risk', label: 'Под риском (по настройке)' },
  { id: 'lost', label: 'Потерянные (по настройке)' },
  { id: 'never', label: 'Никогда не были' },
];

const GENDER_OPTIONS = [
  { id: 'all', label: 'Все' },
  { id: 'male', label: 'Мужчины' },
  { id: 'female', label: 'Женщины' },
];

const STATUS_LABELS = {
  draft: 'черновик',
  scheduled: 'запланирована',
  sending: 'отправляется',
  sent: 'отправлена',
  cancelled: 'отменена',
};

const STATUS_CLASS = {
  draft: 'pending',
  scheduled: 'pending',
  sending: 'pending',
  sent: 'confirmed',
  cancelled: 'cancelled',
};

const AUTO_TYPES = {
  birthday: 'День рождения',
  inactive: 'Спящие клиенты',
  after_visit: 'После визита',
  welcome_first: 'Приветствие нового',
  revisit_cycle: 'Повторный визит по циклу',
};

function formatScheduled(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return iso; }
}

export default function BroadcastsPage({ orgId }) {
  const [mode, setMode] = useState('manual');

  return (
    <div>
      <div className="filters" style={{ marginBottom: 16 }}>
        <button
          className={'filter-btn' + (mode === 'manual' ? ' active' : '')}
          onClick={() => setMode('manual')}
        >
          Ручные
        </button>
        <button
          className={'filter-btn' + (mode === 'auto' ? ' active' : '')}
          onClick={() => setMode('auto')}
        >
          Автоматические
        </button>
      </div>

      {mode === 'manual' && <ManualBroadcasts orgId={orgId} />}
      {mode === 'auto' && <AutoBroadcasts orgId={orgId} />}
    </div>
  );
}

// ==================== РУЧНЫЕ ====================

function ManualBroadcasts({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [broadcasts, setBroadcasts] = useState([]);
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);

  async function load() {
    try {
      const data = await adminApi.getBroadcasts(orgId);
      setBroadcasts(data.broadcasts || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(() => {
      if (broadcasts.some((b) => b.status === 'sending' || b.status === 'scheduled')) load();
    }, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, broadcasts]);

  async function openEdit(b) {
    if (b) {
      try {
        const details = await adminApi.getBroadcastDetails(orgId, b.id);
        const d = details.broadcast;
        const segment = typeof d.segment === 'string'
          ? JSON.parse(d.segment || '{}')
          : (d.segment || {});
        if (!segment.service_ids && segment.service_id) {
          segment.service_ids = [segment.service_id];
        }
        setEditing({
          id: b.id,
          isNew: false,
          text: d.text,
          segment,
          image_id: d.image_id || null,
          preview_url: d.preview_url || null,
          scheduled_at: d.scheduled_at || null,
          status: d.status,
        });
      } catch (e) {
        alert('Ошибка: ' + e.message);
      }
    } else {
      setEditing({
        isNew: true,
        text: '',
        segment: { activity: 'all', gender: 'all', service_ids: [], birthday_within_days: null },
        image_id: null,
        preview_url: null,
        scheduled_at: null,
        status: 'draft',
      });
    }
  }

  async function handleDuplicate(bid) {
    try {
      const r = await adminApi.duplicateBroadcast(orgId, bid);
      await load();
      if (r && r.id) openEdit({ id: r.id });
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handleCancel(bid) {
    if (!window.confirm('Отменить рассылку? Уже отправленные останутся.')) return;
    try {
      await adminApi.cancelBroadcast(orgId, bid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handleUnschedule(bid) {
    if (!window.confirm('Снять с планирования? Рассылка станет черновиком.')) return;
    try {
      await adminApi.unscheduleBroadcast(orgId, bid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handleDelete(bid) {
    if (!window.confirm('Удалить рассылку? Действие необратимо.')) return;
    try {
      await adminApi.deleteBroadcast(orgId, bid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  if (step === 'loading') return <div className="loading">Загрузка…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  return (
    <div>
      {!editing && (
        <button
          className="btn-generate"
          style={{ marginBottom: 12 }}
          onClick={() => openEdit(null)}
        >
          ➕ Создать рассылку
        </button>
      )}

      {editing && (
        <ManualBroadcastForm
          orgId={orgId}
          initial={editing}
          onSaved={async () => { setEditing(null); await load(); }}
          onCancel={() => setEditing(null)}
        />
      )}

      <h2 className="card-title" style={{ marginTop: 16 }}>История рассылок</h2>

      {!broadcasts.length && (
        <p style={{ color: 'var(--text-muted)' }}>Рассылок пока не было.</p>
      )}

      {broadcasts.map((b) => {
        const progress = b.total_recipients > 0
          ? Math.round((b.sent_count / b.total_recipients) * 100)
          : 0;

        return (
          <div key={b.id} className="broadcast-item">
            <div className="broadcast-head">
              <div style={{ flex: 1 }}>
                <div className="broadcast-text">
                  {b.has_image && <span style={{ marginRight: 4 }}>🖼</span>}
                  {b.text}
                </div>
                <div className="broadcast-meta">
                  #{b.id} · {b.created_at ? b.created_at.slice(0, 16).replace('T', ' ') : ''}
                  {b.scheduled_at && b.status === 'scheduled' && (
                    <span style={{ marginLeft: 6, color: 'var(--primary)' }}>
                      · запуск {formatScheduled(b.scheduled_at)}
                    </span>
                  )}
                </div>
              </div>
              <div className={`status status-${STATUS_CLASS[b.status] || 'pending'}`}>
                {STATUS_LABELS[b.status] || b.status}
              </div>
            </div>

            {b.status === 'sending' && (
              <>
                <div className="broadcast-progress-bar">
                  <div className="broadcast-progress-fill" style={{ width: progress + '%' }} />
                </div>
                <div className="broadcast-stats">
                  Отправлено: {b.sent_count} из {b.total_recipients}
                  {b.failed_count > 0 && ` · ошибок: ${b.failed_count}`}
                </div>
              </>
            )}

            {(b.status === 'sent' || b.status === 'cancelled') && b.total_recipients > 0 && (
              <div className="broadcast-stats">
                Доставлено: {b.sent_count} из {b.total_recipients}
                {b.failed_count > 0 && ` · ошибок: ${b.failed_count}`}
              </div>
            )}

            <div className="actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
              {(b.status === 'draft' || b.status === 'scheduled') && (
                <button className="btn-action confirm" onClick={() => openEdit(b)}>
                  ✏️ Редактировать
                </button>
              )}
              {(b.status === 'sent' || b.status === 'cancelled') && (
                <button className="btn-action confirm" onClick={() => setViewing(b.id)}>
                  👁 Детали
                </button>
              )}
              <button
                className="btn-action"
                onClick={() => handleDuplicate(b.id)}
                title="Создать копию как черновик"
              >
                📋 Копировать
              </button>
              {b.status === 'scheduled' && (
                <button className="btn-action" onClick={() => handleUnschedule(b.id)}>
                  ⏸ Снять с плана
                </button>
              )}
              {(b.status === 'scheduled' || b.status === 'sending') && (
                <button className="btn-action reject" onClick={() => handleCancel(b.id)}>
                  ⏹ Отменить
                </button>
              )}
              <button
                className="btn-action reject"
                onClick={() => handleDelete(b.id)}
                title="Удалить рассылку"
              >
                🗑 Удалить
              </button>
            </div>
          </div>
        );
      })}

      {viewing && (
        <ManualBroadcastDetailsModal
          orgId={orgId}
          bid={viewing}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}

function ManualBroadcastForm({ orgId, initial, onSaved, onCancel }) {
  const [text, setText] = useState(initial.text || '');
  const [segment, setSegment] = useState(initial.segment || {});
  const [services, setServices] = useState([]);
  const [previewCount, setPreviewCount] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  const [imageId, setImageId] = useState(initial.image_id || null);
  const [previewUrl, setPreviewUrl] = useState(initial.preview_url || null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [scheduleMode, setScheduleMode] = useState(
    initial.status === 'scheduled' ? 'scheduled' : 'now'
  );
  const [scheduledAt, setScheduledAt] = useState(
    initial.scheduled_at ? initial.scheduled_at.slice(0, 16) : ''
  );

  useEffect(() => {
    adminApi.getServices(orgId).then((d) => setServices(d.services || [])).catch(() => {});
  }, [orgId]);

  function upd(key, value) {
    setSegment((s) => ({ ...s, [key]: value }));
    setPreviewCount(null);
  }

  function toggleService(sid) {
    setSegment((s) => {
      const cur = s.service_ids || [];
      const next = cur.includes(sid) ? cur.filter((x) => x !== sid) : [...cur, sid];
      return { ...s, service_ids: next };
    });
    setPreviewCount(null);
  }

  function selectAllServices() {
    setSegment((s) => {
      const cur = s.service_ids || [];
      const allIds = services.map((x) => x.id);
      const allSelected = cur.length === allIds.length && allIds.every((id) => cur.includes(id));
      return { ...s, service_ids: allSelected ? [] : allIds };
    });
    setPreviewCount(null);
  }

  async function handlePreview() {
    setPreviewBusy(true);
    try {
      const r = await adminApi.previewBroadcast(orgId, segment);
      setPreviewCount(r.count);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setPreviewBusy(false);
    }
  }

  async function handleFileChange(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('Файл больше 10 МБ');
      return;
    }
    setUploadError('');
    setUploading(true);
    try {
      const r = await adminApi.uploadImage(orgId, file);
      setImageId(r.upload_id);
      setPreviewUrl(r.preview_url);
    } catch (err) {
      setUploadError('Не удалось загрузить: ' + err.message);
      setImageId(null);
      setPreviewUrl(null);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function handleRemoveImage() {
    setImageId(null);
    setPreviewUrl(null);
    setUploadError('');
  }

  function buildPayload() {
    return { text, segment, image_id: imageId };
  }

  async function handleSaveDraft() {
    setError('');
    setBusy(true);
    try {
      if (initial.id) {
        await adminApi.updateBroadcast(orgId, initial.id, buildPayload());
      } else {
        await adminApi.createBroadcast(orgId, { ...buildPayload(), start_now: false });
      }
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSendNow() {
    if (!window.confirm('Отправить рассылку сейчас?')) return;
    setError('');
    setBusy(true);
    try {
      if (initial.id) {
        await adminApi.updateBroadcast(orgId, initial.id, buildPayload());
        const r = await adminApi.startBroadcast(orgId, initial.id);
        if (!r.ok && r.note) alert(r.note);
      } else {
        const r = await adminApi.createBroadcast(orgId, { ...buildPayload(), start_now: true });
        if (!r.ok && r.note) alert(r.note);
      }
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSchedule() {
    if (!scheduledAt) {
      setError('Укажите дату и время запуска');
      return;
    }
    setError('');
    setBusy(true);
    try {
      let bid = initial.id;
      if (bid) {
        await adminApi.updateBroadcast(orgId, bid, buildPayload());
      } else {
        const r = await adminApi.createBroadcast(orgId, { ...buildPayload(), start_now: false });
        bid = r.id;
      }
      const dateForServer = scheduledAt.length === 16 ? `${scheduledAt}:00` : scheduledAt;
      await adminApi.scheduleBroadcast(orgId, bid, dateForServer);
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const birthday = segment.birthday_within_days || '';
  const selectedServices = segment.service_ids || [];
  const allSelected = services.length > 0 && selectedServices.length === services.length;

  return (
    <div className="card">
      <h2 className="card-title">
        {initial.id ? `Редактирование #${initial.id}` : 'Новая рассылка'}
      </h2>

      <div className="form-group">
        <label className="form-label">Текст (поддерживает markdown)</label>
        <textarea
          className="form-input"
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="**Скидка 20%** на УЗИ до конца месяца!"
          disabled={busy}
        />
      </div>

      <div className="form-group">
        <label className="form-label">
          Картинка {imageId ? '(прикреплена)' : '(опционально)'}
        </label>
        {previewUrl && (
          <div className="broadcast-image-preview" style={{ marginBottom: 8 }}>
            <img src={previewUrl} alt="preview" />
            <button type="button" className="dir-btn danger" onClick={handleRemoveImage} disabled={busy}>
              ✕
            </button>
          </div>
        )}
        {uploading && <div className="loading" style={{ padding: 16 }}>Загрузка…</div>}
        {!uploading && (
          <button
            className="btn-generate"
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
          >
            {imageId ? '🖼 Заменить картинку' : '📎 Прикрепить картинку'}
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        {uploadError && <div className="form-error">{uploadError}</div>}
      </div>

      <div className="form-group">
        <label className="form-label">Кому отправить</label>
        <select
          className="form-input"
          value={segment.activity || 'all'}
          onChange={(e) => upd('activity', e.target.value)}
          disabled={busy}
        >
          {ACTIVITY_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="form-row-2">
        <div className="form-group">
          <label className="form-label">Пол</label>
          <select
            className="form-input"
            value={segment.gender || 'all'}
            onChange={(e) => upd('gender', e.target.value)}
            disabled={busy}
          >
            {GENDER_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">ДР в ближайшие N дней</label>
          <input
            className="form-input"
            type="number"
            min="1"
            max="365"
            value={birthday}
            onChange={(e) => upd('birthday_within_days', e.target.value ? parseInt(e.target.value, 10) : null)}
            placeholder="7"
            disabled={busy}
          />
        </div>
      </div>

      <div className="form-group">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <label className="form-label" style={{ margin: 0 }}>Клиенты конкретных услуг</label>
          {services.length > 0 && (
            <button
              type="button"
              className="btn-link"
              style={{ fontSize: 12, padding: 0 }}
              onClick={selectAllServices}
              disabled={busy}
            >
              {allSelected ? 'Снять выделение' : 'Выделить все'}
            </button>
          )}
        </div>
        <div className="service-checkbox-list">
          {services.length === 0 && (
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Услуги не настроены</span>
          )}
          {services.map((s) => (
            <label key={s.id} className="checkbox-row" style={{ padding: '6px 0' }}>
              <input
                type="checkbox"
                checked={selectedServices.includes(s.id)}
                onChange={() => toggleService(s.id)}
                disabled={busy}
              />
              <span>{s.name}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="broadcast-preview">
        {previewCount !== null && <span>👥 Получателей: <b>{previewCount}</b></span>}
        <button className="btn-link" onClick={handlePreview} disabled={previewBusy || busy}>
          {previewBusy ? 'Считаем…' : '🔍 Посчитать получателей'}
        </button>
      </div>

      <div
        style={{
          marginTop: 16,
          padding: 12,
          background: 'var(--bg)',
          borderRadius: 10,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          🕒 Когда отправить?
        </div>
        <label className="radio-row" style={{ paddingBottom: 6 }}>
          <input
            type="radio"
            name="schedule-mode"
            checked={scheduleMode === 'now'}
            onChange={() => setScheduleMode('now')}
            disabled={busy}
          />
          <div>
            <div className="radio-label">Сейчас</div>
            <div className="radio-hint">Нажать «Отправить сейчас» → отправим в течение минуты.</div>
          </div>
        </label>
        <label className="radio-row" style={{ paddingBottom: 6 }}>
          <input
            type="radio"
            name="schedule-mode"
            checked={scheduleMode === 'scheduled'}
            onChange={() => setScheduleMode('scheduled')}
            disabled={busy}
          />
          <div>
            <div className="radio-label">Запланировать</div>
            <div className="radio-hint">Выберите дату и время — рассылка уйдёт автоматически.</div>
          </div>
        </label>
        <label className="radio-row" style={{ paddingBottom: 0 }}>
          <input
            type="radio"
            name="schedule-mode"
            checked={scheduleMode === 'draft'}
            onChange={() => setScheduleMode('draft')}
            disabled={busy}
          />
          <div>
            <div className="radio-label">Сохранить как черновик</div>
            <div className="radio-hint">Можно вернуться и отредактировать позже.</div>
          </div>
        </label>

        {scheduleMode === 'scheduled' && (
          <div className="form-group" style={{ marginTop: 10, marginBottom: 0 }}>
            <label className="form-label">Дата и время запуска</label>
            <input
              className="form-input"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              disabled={busy}
            />
          </div>
        )}
      </div>

      {error && <div className="form-error" style={{ marginTop: 12 }}>{error}</div>}

      <div className="actions" style={{ marginTop: 16, flexWrap: 'wrap' }}>
        <button
          className="btn-action reject"
          onClick={handleSaveDraft}
          disabled={busy || !text.trim() || uploading}
          style={{ flex: 1, minWidth: 120 }}
        >
          💾 Черновик
        </button>
        {scheduleMode === 'scheduled' ? (
          <button
            className="btn-action confirm"
            onClick={handleSchedule}
            disabled={busy || !text.trim() || uploading || !scheduledAt}
            style={{ flex: 1, minWidth: 120 }}
          >
            🕒 Запланировать
          </button>
        ) : (
          <button
            className="btn-action confirm"
            onClick={handleSendNow}
            disabled={busy || !text.trim() || uploading}
            style={{ flex: 1, minWidth: 120 }}
          >
            🚀 Отправить сейчас
          </button>
        )}
        <button
          className="btn-action reject"
          onClick={onCancel}
          disabled={busy}
          style={{ flex: '0 0 80px' }}
        >
          Отмена
        </button>
      </div>
    </div>
  );
}

function ManualBroadcastDetailsModal({ orgId, bid, onClose }) {
  const [data, setData] = useState(null);
  const [sends, setSends] = useState([]);
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      adminApi.getBroadcastDetails(orgId, bid),
      adminApi.getBroadcastSends(orgId, bid),
    ]).then(([d, s]) => {
      setData(d.broadcast);
      setSends(s.sends || []);
      setStep('ready');
    }).catch((e) => {
      setError(e.message);
      setStep('error');
    });
  }, [orgId, bid]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 500 }}>
        <h2 className="card-title">Рассылка #{bid}</h2>
        {step === 'loading' && <div className="loading">Загрузка…</div>}
        {step === 'error' && <div className="error-box">{error}</div>}
        {step === 'ready' && data && (
          <>
            {data.preview_url && (
              <div className="broadcast-image-preview" style={{ marginBottom: 8 }}>
                <img src={data.preview_url} alt="preview" />
              </div>
            )}
            <div className="row"><span>Текст:</span> {data.text}</div>
            <div className="row"><span>Статус:</span> {STATUS_LABELS[data.status] || data.status}</div>
            {data.scheduled_at && (
              <div className="row"><span>Запуск:</span> {formatScheduled(data.scheduled_at)}</div>
            )}
            <div className="row"><span>Всего:</span> {data.total}</div>
            <div className="row"><span>Отправлено:</span> {data.sent}</div>
            {data.failed > 0 && <div className="row"><span>Ошибок:</span> {data.failed}</div>}
            <div className="row"><span>Создана:</span> {data.created_at?.slice(0, 16).replace('T', ' ')}</div>
            {data.finished_at && (
              <div className="row"><span>Завершена:</span> {data.finished_at.slice(0, 16).replace('T', ' ')}</div>
            )}
            <h3 style={{ marginTop: 16, fontSize: 14 }}>Получатели ({sends.length})</h3>
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {!sends.length && <p style={{ color: 'var(--text-muted)' }}>Список пуст.</p>}
              {sends.map((s) => (
                <div key={s.user_id} className="row" style={{ fontSize: 13 }}>
                  <span style={{ minWidth: 130 }}>{s.user_id}:</span>
                  {s.status === 'sent' ? '✅ доставлено'
                    : s.status === 'failed' ? `❌ ${s.error || 'ошибка'}`
                    : s.status === 'skipped' ? `➖ пропущен (${s.error || 'нет канала'})`
                    : '⏳ ожидает'}
                </div>
              ))}
            </div>
          </>
        )}
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}

// ==================== АВТОМАТИЧЕСКИЕ ====================

function AutoBroadcasts({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [togglingId, setTogglingId] = useState(null);
  const formAnchorRef = useRef(null);

  useEffect(() => {
    if (editing && formAnchorRef.current) {
      formAnchorRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [editing]);

  async function load() {
    try {
      const data = await adminApi.getAutoBroadcasts(orgId);
      setItems(data.auto_broadcasts || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleToggle(id) {
    if (togglingId) return;
    setTogglingId(id);
    try {
      await adminApi.toggleAutoBroadcast(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить сценарий?')) return;
    try {
      await adminApi.deleteAutoBroadcast(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handleSave(form) {
    try {
      if (form.id) {
        await adminApi.updateAutoBroadcast(orgId, form.id, {
          text: form.text,
          delay_value: form.delay_value,
          image_id: form.image_id,
          active: form.active ? 1 : 0,
        });
      } else {
        await adminApi.createAutoBroadcast(orgId, {
          type: form.type,
          text: form.text,
          delay_value: form.delay_value,
          image_id: form.image_id,
        });
      }
      setEditing(null);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  if (step === 'loading') return <div className="loading">Загрузка…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  return (
    <div>
      {!editing && (
        <button
          className="btn-generate"
          style={{ marginBottom: 12 }}
          onClick={() => setEditing({
            isNew: true, type: 'birthday', text: '', delay_value: 3,
            image_id: null, preview_url: null, active: true,
          })}
        >
          ➕ Добавить сценарий
        </button>
      )}

      {editing && (
        <div ref={formAnchorRef}>
          <AutoBroadcastForm
            orgId={orgId}
            initial={editing}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
          />
        </div>
      )}

      <h2 className="card-title" style={{ marginTop: 16 }}>Активные сценарии</h2>

      {!items.length && <p style={{ color: 'var(--text-muted)' }}>Сценариев пока нет.</p>}

      {items.map((item) => (
        <div key={item.id} className="broadcast-item" style={{ opacity: item.active ? 1 : 0.6 }}>
          <div className="broadcast-head">
            <div style={{ flex: 1 }}>
              <div className="broadcast-text">
                <b>{AUTO_TYPES[item.type]}</b>
                {item.has_image && <span style={{ marginLeft: 6 }}>🖼</span>}
              </div>
              <div className="broadcast-meta">
                {item.type === 'birthday' ? `За ${item.delay_value} дн. до ДР`
                  : item.type === 'inactive' ? `Через ${item.delay_value} дн. неактивности`
                  : `Через ${item.delay_value} ч. после визита`}
                {' · '}{item.text.slice(0, 40)}...
              </div>
            </div>
            <button
              type="button"
              className={`status status-${item.active ? 'confirmed' : 'cancelled'} status-clickable`}
              onClick={() => handleToggle(item.id)}
              disabled={togglingId === item.id}
              title={item.active ? 'Нажмите, чтобы отключить' : 'Нажмите, чтобы включить'}
            >
              {togglingId === item.id ? '…' : (item.active ? 'Вкл' : 'Выкл')}
            </button>
          </div>

          <div className="actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
            <button
              className="btn-action"
              onClick={async () => {
                try {
                  await adminApi.testAutoBroadcast(orgId, item.id);
                  alert('Тест отправлен в ваш чат MAX');
                } catch (e) {
                  alert('Ошибка: ' + e.message);
                }
              }}
            >
              🧪 Тест
            </button>
            <button className="btn-action confirm" onClick={() => setEditing(item)}>
              ✏️ Редактировать
            </button>
            <button className="btn-action reject" onClick={() => handleDelete(item.id)}>
              🗑 Удалить
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function AutoBroadcastForm({ orgId, initial, onSave, onCancel }) {
  const [text, setText] = useState(initial.text || '');
  const [type, setType] = useState(initial.type || 'birthday');
  const [delayValue, setDelayValue] = useState(initial.delay_value || 3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [imageId, setImageId] = useState(initial.image_id || null);
  const [previewUrl, setPreviewUrl] = useState(initial.preview_url || null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);

  async function handleFileChange(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('Файл больше 10 МБ');
      return;
    }
    setUploadError('');
    setUploading(true);
    try {
      const r = await adminApi.uploadImage(orgId, file);
      setImageId(r.upload_id);
      setPreviewUrl(r.preview_url);
    } catch (err) {
      setUploadError('Не удалось загрузить: ' + err.message);
      setImageId(null);
      setPreviewUrl(null);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function insertVariable(varname) {
    const ta = textareaRef.current;
    if (!ta) {
      setText((t) => (t || "") + varname);
      return;
    }
    const start = ta.selectionStart ?? (text || "").length;
    const end = ta.selectionEnd ?? (text || "").length;
    const before = (text || "").slice(0, start);
    const after = (text || "").slice(end);
    const next = before + varname + after;
    setText(next);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + varname.length;
      try { ta.setSelectionRange(pos, pos); } catch {}
    });
  }

  function handleRemoveImage() {
    setImageId(null);
    setPreviewUrl(null);
    setUploadError('');
  }

  async function handleSubmit() {
    setError('');
    setBusy(true);
    try {
      await onSave({
        ...initial,
        text,
        type,
        delay_value: (type === 'welcome_first' || type === 'revisit_cycle') ? 0 : delayValue,
        image_id: imageId,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2 className="card-title">
        {initial.isNew ? 'Новый сценарий' : 'Редактировать сценарий'}
      </h2>

      <div className="form-group">
        <label className="form-label">Тип сценария</label>
        <select
          className="form-input"
          value={type}
          onChange={(e) => setType(e.target.value)}
          disabled={busy || !initial.isNew}
        >
          <option value="birthday">День рождения</option>
          <option value="inactive">Спящие клиенты</option>
          <option value="after_visit">После визита</option>
          <option value="welcome_first">Приветствие нового (первая запись)</option>
          <option value="revisit_cycle">Повторный визит по циклу</option>
        </select>
        {type === 'welcome_first' && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Отправляется сразу после первой записи клиента в клинику.
            Задержка не используется — поле ниже скрыто.
          </div>
        )}
        {type === 'revisit_cycle' && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Отправляется через N дней после визита, где N — поле
            «Напомнить о повторе» в карточке услуги (Справочники → Услуги).
            Задержка здесь не используется — поле ниже скрыто.
          </div>
        )}
      </div>

      {type !== 'welcome_first' && type !== 'revisit_cycle' && (
        <div className="form-group">
          <label className="form-label">
            {type === 'birthday' ? 'За сколько дней до ДР отправлять?'
              : type === 'inactive' ? 'Через сколько дней неактивности отправлять?'
              : 'Через сколько часов после визита отправлять?'}
          </label>
          <input
            className="form-input"
            type="number"
            min="1"
            value={delayValue}
            onChange={(e) => setDelayValue(parseInt(e.target.value, 10) || 1)}
            disabled={busy}
          />
        </div>
      )}

      <div className="form-group">
        <label className="form-label">Текст (поддерживает markdown)</label>
        <textarea
          ref={textareaRef}
          className="form-input"
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
        />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Вставить:</span>
          {(type === 'welcome_first' || type === 'after_visit'
            ? [
                { code: '{name}', label: 'Имя' },
                { code: '{service}', label: 'Услуга' },
                { code: '{scheduled_at}', label: 'Дата/время' },
                { code: '{address}', label: 'Адрес' },
                { code: '{prep}', label: 'Подготовка' },
              ]
            : type === 'inactive'
              ? [
                  { code: '{name}', label: 'Имя' },
                  { code: '{last_visit}', label: 'Последний визит' },
                  { code: '{days_inactive}', label: 'Дней без визита' },
                  { code: '{service}', label: 'Последняя услуга' },
                ]
            : type === 'revisit_cycle'
              ? [
                  { code: '{name}', label: 'Имя' },
                  { code: '{service}', label: 'Услуга' },
                  { code: '{last_visit}', label: 'Последний визит' },
                  { code: '{days_since_visit}', label: 'Дней с визита' },
                  { code: '{prep}', label: 'Подготовка' },
                ]
              : [{ code: '{name}', label: 'Имя' }]
          ).map((v) => (
            <button
              key={v.code}
              type="button"
              className="filter-btn"
              onClick={() => insertVariable(v.code)}
              disabled={busy}
              style={{ padding: '3px 10px', fontSize: 12 }}
              title={v.code}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
          Нажмите на переменную — код вставится в позицию курсора.
          {type === 'birthday' && <> Для «Дня рождения» доступно только имя клиента.</>}
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">
          Картинка {imageId ? '(прикреплена)' : '(опционально)'}
        </label>
        {previewUrl && (
          <div className="broadcast-image-preview" style={{ marginBottom: 8 }}>
            <img src={previewUrl} alt="preview" />
            <button
              type="button"
              className="dir-btn danger"
              onClick={handleRemoveImage}
              disabled={busy}
            >✕</button>
          </div>
        )}
        {uploading && <div className="loading" style={{ padding: 16 }}>Загрузка…</div>}
        {!uploading && (
          <button
            className="btn-generate"
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
          >
            {imageId ? '🖼 Заменить картинку' : '📎 Прикрепить картинку'}
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        {uploadError && <div className="form-error">{uploadError}</div>}
      </div>

      {error && <div className="form-error">{error}</div>}

      <div className="actions" style={{ marginTop: 16, flexWrap: 'wrap' }}>
        <button
          className="btn-action confirm"
          onClick={handleSubmit}
          disabled={busy || !text.trim() || uploading}
          style={{ flex: 1, minWidth: 120 }}
        >
          {busy ? 'Сохранение…' : '💾 Сохранить'}
        </button>
        <button
          className="btn-action reject"
          onClick={onCancel}
          disabled={busy}
          style={{ flex: '0 0 80px' }}
        >
          Отмена
        </button>
      </div>
    </div>
  );
}