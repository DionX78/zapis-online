import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const ACTION_LABELS = {
  booking_created: '🆕 Создана запись',
  request_confirmed: '✅ Заявка подтверждена',
  request_rejected: '❌ Заявка отклонена',
  request_cancelled_by_admin: '❌ Запись отменена',
  status_changed_to_done: '✅ Пришёл',
  status_changed_to_no_show: '🚫 Не пришёл',
  status_changed_to_cancelled: '❌ Отменена',
  status_changed_to_confirmed: '✅ Подтверждена',
  payment_updated: '💰 Оплата изменена',
  settings_updated: '⚙️ Настройки обновлены',
  slot_created: '📅 Слот создан',
  slot_deleted: '🗑 Слот удалён',
  slots_generated: '⚡ Слоты сгенерированы',
  branch_created: '🏢 Филиал создан',
  branch_updated: '🏢 Филиал изменён',
  branch_deleted: '🗑 Филиал удалён',
  doctor_created: '👤 Специалист создан',
  doctor_updated: '👤 Специалист изменён',
  doctor_deleted: '🗑 Специалист удалён',
  service_created: '💼 Услуга создана',
  service_updated: '💼 Услуга изменена',
  service_deleted: '🗑 Услуга удалена',
  broadcast_created: '📣 Рассылка создана',
  broadcast_started: '🚀 Рассылка запущена',
  broadcast_cancelled: '⏸ Рассылка отменена',
  broadcast_deleted: '🗑 Рассылка удалена',
  auto_broadcast_created: '📣 Автосценарий создан',
  auto_broadcast_updated: '📣 Автосценарий изменён',
  auto_broadcast_deleted: '🗑 Автосценарий удалён',
  auto_broadcast_toggled: '📣 Автосценарий переключён',
  image_uploaded: '🖼 Картинка загружена',
};

function actionLabel(action) {
  return ACTION_LABELS[action] || action;
}

function humanTs(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

function tryJson(str) {
  if (!str) return null;
  try { return JSON.parse(str); } catch { return str; }
}

export default function AuditLogPage({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [entries, setEntries] = useState([]);
  const [filter, setFilter] = useState('all');
  const [offset, setOffset] = useState(0);
  const PER_PAGE = 100;

  const FILTERS = [
    { id: 'all', label: 'Все' },
    { id: 'requests', label: '📋 Заявки', actions: [
      'booking_created','request_confirmed','request_rejected','request_cancelled_by_admin',
      'status_changed_to_done','status_changed_to_no_show','status_changed_to_cancelled',
      'status_changed_to_confirmed','payment_updated',
    ]},
    { id: 'slots', label: '📅 Слоты', actions: [
      'slot_created','slot_deleted','slots_generated',
    ]},
    { id: 'directories', label: '🏢 Справочники', actions: [
      'branch_created','branch_updated','branch_deleted',
      'doctor_created','doctor_updated','doctor_deleted',
      'service_created','service_updated','service_deleted',
    ]},
    { id: 'broadcasts', label: '📣 Рассылки', actions: [
      'broadcast_created','broadcast_started','broadcast_cancelled','broadcast_deleted',
      'auto_broadcast_created','auto_broadcast_updated','auto_broadcast_deleted',
      'auto_broadcast_toggled','image_uploaded',
    ]},
    { id: 'settings', label: '⚙️ Настройки', actions: ['settings_updated'] },
  ];

  async function load(showSpinner = true) {
    if (showSpinner) setStep('loading');
    setError('');
    try {
      const r = await adminApi.getAuditLog(orgId, { limit: PER_PAGE, offset });
      setEntries(r.entries || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, offset]);

  function changeFilter(id) {
    setFilter(id);
    setOffset(0);
  }

  if (step === 'loading') return <div className="loading">Загрузка журнала…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  const activeFilter = FILTERS.find((f) => f.id === filter) || FILTERS[0];
  const filtered = filter === 'all'
    ? entries
    : entries.filter((e) => (activeFilter.actions || []).includes(e.action));

  return (
    <div>
      <div className="filters-scroll">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            className={'filter-btn' + (filter === f.id ? ' active' : '')}
            onClick={() => changeFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!filtered.length && (
        <div className="dash-empty">
          Пока нет записей в журнале.
          <div style={{ fontSize: 13, marginTop: 6 }}>
            Здесь будут появляться все действия администраторов: подтверждения,
            отмены, изменения настроек, создание слотов и рассылок.
          </div>
        </div>
      )}

      {filtered.map((e) => {
        const payload = tryJson(e.payload);
        return (
          <div key={e.id} className="audit-item">
            <div className="audit-head">
              <div style={{ flex: 1 }}>
                <div className="audit-action">{actionLabel(e.action)}</div>
                <div className="audit-meta">
                  {e.entity_type && `${e.entity_type}`}
                  {e.entity_id && ` #${e.entity_id}`}
                  {e.user_id && ` · админ: ${e.user_id}`}
                </div>
              </div>
              <div className="audit-ts">{humanTs(e.created_at)}</div>
            </div>
            {payload && typeof payload === 'object' && Object.keys(payload).length > 0 && (
              <div className="audit-payload">
                {Object.entries(payload).map(([k, v]) => (
                  <span key={k} className="audit-payload-item">
                    <b>{k}:</b> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <div className="pagination" style={{ marginTop: 12 }}>
        <button
          className="page-btn"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PER_PAGE))}
        >
          ←
        </button>
        <span className="page-info">
          {offset + 1}–{offset + entries.length}
        </span>
        <button
          className="page-btn"
          disabled={entries.length < PER_PAGE}
          onClick={() => setOffset(offset + PER_PAGE)}
        >
          →
        </button>
      </div>
    </div>
  );
}