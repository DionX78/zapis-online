import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';
import CreateRequestModal from './CreateRequestModal.jsx';
import MarkVisitModal, { PAYMENT_LABELS } from './MarkVisitModal.jsx';
import ClientCardModal from './ClientCardModal.jsx';
import MoveRequestModal from './MoveRequestModal.jsx';
import EditRequestModal from './EditRequestModal.jsx';

const STATUS_LABELS = {
  pending: 'ожидает',
  confirmed: 'подтверждена',
  cancelled: 'отменена',
  done: 'пришёл',
  no_show: 'не пришёл',
  new: 'новая',
};

const STATUS_FILTERS = [
  { id: 'all', label: 'Все' },
  { id: 'pending', label: 'Ожидают' },
  { id: 'confirmed', label: 'Подтверждены' },
  { id: 'cancelled', label: 'Отменены' },
  { id: 'done', label: '✅ Пришли' },
  { id: 'no_show', label: '🚫 Не пришли' },
  { id: 'auto_done', label: '⚠️ Авто-пришли' },
];

const PER_PAGE = 20;

function isoDate(d) {
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function todayIso() { return isoDate(new Date()); }
function plusDaysIso(n) { return isoDate(addDays(new Date(), n)); }

const DATE_PRESETS = [
  { id: 'today', label: 'Сегодня', from: () => todayIso(), to: () => todayIso() },
  { id: 'yesterday', label: 'Вчера', from: () => plusDaysIso(-1), to: () => plusDaysIso(-1) },
  { id: 'tomorrow', label: 'Завтра', from: () => plusDaysIso(1), to: () => plusDaysIso(1) },
  { id: '7_back', label: 'Сегодня −7', from: () => plusDaysIso(-7), to: () => plusDaysIso(-1) },
  { id: '7', label: 'Сегодня +7', from: () => todayIso(), to: () => plusDaysIso(7) },
  { id: '30', label: 'Сегодня +30', from: () => todayIso(), to: () => plusDaysIso(30) },
  { id: 'all', label: 'Вся история', from: () => null, to: () => null },
];

export default function RequestsPage({
  orgId,
  initialStatus = 'all',
  initialDatePreset = '7',
}) {
  const [status, setStatus] = useState(initialStatus);
  const [datePreset, setDatePreset] = useState(initialDatePreset);
  const [page, setPage] = useState(1);

  const [requests, setRequests] = useState([]);
  const [services, setServices] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [markingRequest, setMarkingRequest] = useState(null);
  const [clientCardUserId, setClientCardUserId] = useState(null);
  const [movingRequest, setMovingRequest] = useState(null);
  const [editingRequest, setEditingRequest] = useState(null);

  async function load() {
    setStep('loading');
    setError('');
    try {
      const preset = DATE_PRESETS.find((p) => p.id === datePreset);
      const from = preset ? preset.from() : null;
      const to = preset ? preset.to() : null;

      // Спецфильтр «Авто-пришли»: status=done + auto_done=1.
      const isAutoDone = status === 'auto_done';
      const realStatus = isAutoDone ? 'done' : status;

      const data = await adminApi.getRequests(orgId, {
        status: realStatus,
        auto_done: isAutoDone ? '1' : undefined,
        date_from: from,
        date_to: to,
        page,
        per_page: PER_PAGE,
      });
      setRequests(data.requests || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, status, datePreset, page]);

  useEffect(() => {
    adminApi.getServices(orgId).then((d) => setServices(d.services || [])).catch(() => {});
  }, [orgId]);

  function priceByServiceId(serviceId) {
    const svc = services.find((s) => s.id === serviceId);
    return svc ? svc.price : null;
  }

  function changeStatus(newStatus) {
    setStatus(newStatus);
    setPage(1);
  }

  function changeDatePreset(id) {
    setDatePreset(id);
    setPage(1);
  }

  async function handleConfirm(id) {
    setBusyId(id);
    try {
      await adminApi.confirmRequest(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(id, wasConfirmed) {
    const msg = wasConfirmed
      ? 'Отменить подтверждённую запись? Слот будет освобождён, клиент получит уведомление.'
      : 'Отклонить заявку? Слот будет освобождён.';
    if (!window.confirm(msg)) return;
    setBusyId(id);
    try {
      await adminApi.rejectRequest(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleMarkNoShow(id) {
    if (!window.confirm('Отметить, что клиент не пришёл? Клиент не получит «Спасибо за визит», а дата визита пересчитается.')) return;
    setBusyId(id);
    try {
      await adminApi.markNoShow(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleMarkDone(payload) {
    if (!markingRequest) return;
    const id = markingRequest.id;
    await adminApi.markDone(orgId, id, payload);
    setMarkingRequest(null);
    await load();
  }

  if (step === 'loading') return <div className="loading">Загрузка заявок…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  const activeDateLabel = (DATE_PRESETS.find((p) => p.id === datePreset) || {}).label || '—';

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setCreateOpen(true)}
      >
        ➕ Создать запись
      </button>

      <div className="filters-scroll">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            className={'filter-btn' + (status === f.id ? ' active' : '')}
            onClick={() => changeStatus(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="filters-period-row">
        <span className="filters-period-label">📅 Период</span>
        <select
          className="filters-period-select"
          value={datePreset}
          onChange={(e) => changeDatePreset(e.target.value)}
          title="Период"
        >
          {DATE_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      </div>

      {!requests.length && (
        <p style={{ color: 'var(--text-muted)', margin: '12px 0' }}>
          Заявок в этой категории нет.
        </p>
      )}

      {requests.map((r) => {
        const expanded = expandedId === r.id;
        const hasAmount = r.actual_amount != null;
        const optedOut = !!r.marketing_opt_out;
        const isBlocked = !!r.blocked;
        const isPhoneOnly = String(r.user_id || '').startsWith('phone:');
        return (
          <div key={r.id} className="request-item">
            <div
              className="request-head"
              onClick={() => setExpandedId(expanded ? null : r.id)}
            >
              <div>
                <div className="request-title">#{r.id} {r.service_name}</div>
                <div className="request-meta">
                  {r.scheduled_at} · {r.phone}
                  {hasAmount && ` · 💰 ${r.actual_amount} ₽${r.payment_method ? ` (${PAYMENT_LABELS[r.payment_method] || r.payment_method})` : ''}`}
                </div>
              </div>
              <div className="request-head-right">
                {isBlocked && (
                  <span className="tag" style={{ background: '#fdecec', color: '#a83c3c' }}>
                    🚫 заблокирован
                  </span>
                )}
                {r.done_auto && (
                  <span
                    className="tag"
                    style={{ background: '#fff4d9', color: '#8b5a00' }}
                    title="Статус «пришёл» проставлен автоматически. Проверьте сумму."
                  >
                    ⚠️ авто
                  </span>
                )}
                <div className={`status status-${r.status}`}>
                  {STATUS_LABELS[r.status] || r.status}
                </div>
              </div>
            </div>

            {expanded && (
              <div className="request-body">
                <div className="row"><span>Услуга:</span> {r.service_name}</div>
                <div className="row">
                  <span>Дата:</span> {r.scheduled_at}
                  {r.slots_count > 1 && (
                    <span style={{ color: 'var(--text-muted)', marginLeft: 6, fontSize: 12 }}>
                      (занимает {r.slots_count} слота)
                    </span>
                  )}
                </div>
                <div className="row"><span>Телефон:</span> {r.phone}</div>
                {r.address && <div className="row"><span>Адрес:</span> {r.address}</div>}
                {r.doctor && <div className="row"><span>Специалист:</span> {r.doctor}</div>}
                <div className="row"><span>Создана:</span> {r.created_at}</div>
                {hasAmount && (
                  <div className="row">
                    <span>Оплата:</span>
                    {' '}{r.actual_amount} ₽
                    {r.payment_method ? ` · ${PAYMENT_LABELS[r.payment_method] || r.payment_method}` : ''}
                    {r.done_auto && (
                      <span style={{ color: '#8b5a00', marginLeft: 6, fontSize: 12 }}>
                        (авто, проверьте)
                      </span>
                    )}
                  </div>
                )}
                <div className="row" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
                  {!isPhoneOnly && (
                    <button
                      type="button"
                      className="btn-link"
                      style={{ fontSize: 12, padding: 0 }}
                      onClick={() => setClientCardUserId(r.user_id)}
                    >
                      👤 Карточка клиента
                    </button>
                  )}
                  {(r.status === 'pending' || r.status === 'confirmed') && (
                    <>
                      <button
                        type="button"
                        className="btn-link"
                        style={{ fontSize: 12, padding: 0 }}
                        onClick={() => setMovingRequest(r)}
                      >
                        🔄 Перенести запись
                      </button>
                      <button
                        type="button"
                        className="btn-link"
                        style={{ fontSize: 12, padding: 0 }}
                        onClick={() => setEditingRequest(r)}
                      >
                        ✏️ Редактировать услугу / слоты
                      </button>
                    </>
                  )}
                </div>

                {r.status === 'pending' && (
                  <div className="actions">
                    <button
                      className="btn-action confirm"
                      disabled={busyId === r.id}
                      onClick={() => handleConfirm(r.id)}
                    >
                      ✅ Подтвердить
                    </button>
                    <button
                      className="btn-action reject"
                      disabled={busyId === r.id}
                      onClick={() => handleReject(r.id, false)}
                    >
                      ❌ Отклонить
                    </button>
                  </div>
                )}

                {r.status === 'confirmed' && (
                  <div className="actions">
                    <button
                      className="btn-action confirm"
                      disabled={busyId === r.id}
                      onClick={() => setMarkingRequest(r)}
                    >
                      ✅ Пришёл
                    </button>
                    <button
                      className="btn-action"
                      disabled={busyId === r.id}
                      onClick={() => handleMarkNoShow(r.id)}
                    >
                      🚫 Не пришёл
                    </button>
                    <button
                      className="btn-action reject"
                      disabled={busyId === r.id}
                      onClick={() => handleReject(r.id, true)}
                    >
                      ❌ Отменить запись
                    </button>
                  </div>
                )}

                {r.status === 'done' && (
                  <div className="actions">
                    <button
                      className="btn-action"
                      disabled={busyId === r.id}
                      onClick={() => setMarkingRequest(r)}
                      title="Изменить сумму или способ оплаты"
                    >
                      ✏️ Изменить сумму
                    </button>
                    <button
                      className="btn-action"
                      disabled={busyId === r.id}
                      onClick={() => handleMarkNoShow(r.id)}
                    >
                      🚫 Клиент не пришёл
                    </button>
                  </div>
                )}

                {r.status === 'no_show' && (
                  <div className="actions">
                    <button
                      className="btn-action confirm"
                      disabled={busyId === r.id}
                      onClick={() => setMarkingRequest(r)}
                    >
                      ✅ Клиент пришёл
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            ←
          </button>
          <span className="page-info">{page} из {totalPages}</span>
          <button
            className="page-btn"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            →
          </button>
        </div>
      )}

      <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, marginTop: 12 }}>
        Всего заявок: {total} · {activeDateLabel}
      </p>

      {createOpen && (
        <CreateRequestModal
          orgId={orgId}
          onClose={() => setCreateOpen(false)}
          onCreated={async () => { await load(); }}
        />
      )}

      {markingRequest && (
        <MarkVisitModal
          request={markingRequest}
          defaultPrice={priceByServiceId(markingRequest.service_id)}
          onCancel={() => setMarkingRequest(null)}
          onConfirm={handleMarkDone}
        />
      )}

      {clientCardUserId && (
        <ClientCardModal
          orgId={orgId}
          userId={clientCardUserId}
          onClose={() => setClientCardUserId(null)}
          onChanged={async () => { await load(); }}
        />
      )}

      {movingRequest && (
        <MoveRequestModal
          orgId={orgId}
          request={movingRequest}
          onClose={() => setMovingRequest(null)}
          onMoved={async () => { await load(); }}
        />
      )}

      {editingRequest && (
        <EditRequestModal
          orgId={orgId}
          request={editingRequest}
          onClose={() => setEditingRequest(null)}
          onSaved={async () => { await load(); }}
        />
      )}
    </div>
  );
}