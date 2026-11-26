import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

function todayHuman() {
  const d = new Date();
  const months = ['января','февраля','марта','апреля','мая','июня',
    'июля','августа','сентября','октября','ноября','декабря'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

export default function DashboardPage({ orgId, onOpenRequests }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load(showSpinner = true) {
    if (showSpinner) setStep('loading');
    else setRefreshing(true);
    setError('');
    try {
      const d = await adminApi.getDashboardToday(orgId);
      setData(d);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(() => load(false), 60 * 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  function open(status, datePreset = 'today') {
    if (onOpenRequests) onOpenRequests(status, datePreset);
  }

  if (step === 'loading') return <div className="loading">Загрузка дашборда…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;
  if (!data) return null;

  return (
    <div>
      <div className="dash-header">
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Сегодня</h2>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            {todayHuman()}
          </div>
        </div>
        <button
          className="btn-link"
          style={{ fontSize: 13, padding: 4 }}
          onClick={() => load(false)}
          disabled={refreshing}
        >
          {refreshing ? '…' : '↻ Обновить'}
        </button>
      </div>

      {/* Широкая карточка «Всего» */}
      <button
        type="button"
        className="dash-card dash-card-total dash-card-clickable"
        onClick={() => open('all', 'today')}
      >
        <div className="dash-card-label">Всего записей</div>
        <div className="dash-card-value">{data.total}</div>
      </button>

      {/* Сетка 3×2 по статусам + выручка */}
      <div className="dash-cards">
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-done"
          onClick={() => open('done', 'today')}
        >
          <div className="dash-card-label">✅ Пришли</div>
          <div className="dash-card-value">{data.done}</div>
          {data.auto_done_count > 0 && (
            <div
              style={{
                fontSize: 11,
                color: '#8b5a00',
                marginTop: 2,
                fontWeight: 500,
              }}
              onClick={(e) => {
                e.stopPropagation();
                open('auto_done', 'today');
              }}
              title="Автоматически отмечены как пришедшие. Клик — перепроверить."
            >
              ⚠️ {data.auto_done_count} авто
            </div>
          )}
        </button>
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-pending"
          onClick={() => open('pending', 'today')}
        >
          <div className="dash-card-label">🟡 Ожидают</div>
          <div className="dash-card-value">{data.pending}</div>
        </button>
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-confirmed"
          onClick={() => open('confirmed', 'today')}
        >
          <div className="dash-card-label">🔵 Подтверждены</div>
          <div className="dash-card-value">{data.confirmed}</div>
        </button>
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-noshow"
          onClick={() => open('no_show', 'today')}
        >
          <div className="dash-card-label">🚫 Не пришли</div>
          <div className="dash-card-value">{data.no_show}</div>
        </button>
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-cancelled"
          onClick={() => open('cancelled', 'today')}
        >
          <div className="dash-card-label">❌ Отменены</div>
          <div className="dash-card-value">{data.cancelled}</div>
        </button>
        <button
          type="button"
          className="dash-card dash-card-clickable dash-card-revenue"
          onClick={() => open('done', 'today')}
          title="Показать записи, по которым есть оплата"
        >
          <div className="dash-card-label">💰 Выручка</div>
          <div className="dash-card-value">{data.revenue} ₽</div>
        </button>
      </div>

      {data.pending > 0 && (
        <div className="dash-section">
          <div className="dash-section-head">
            <h3 style={{ margin: 0, fontSize: 15 }}>⚠️ Требуют подтверждения</h3>
            <button
              className="btn-link"
              style={{ fontSize: 13, padding: 4 }}
              onClick={() => open('pending', 'today')}
            >
              Перейти →
            </button>
          </div>
          <div className="dash-pending-list">
            {data.pending_list.map((r) => (
              <button
                key={r.id}
                type="button"
                className="dash-pending-item dash-pending-clickable"
                onClick={() => open('pending', 'today')}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>
                    #{r.id} · {r.service_name}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                    {r.scheduled_at}
                    {r.doctor ? ` · ${r.doctor}` : ''}
                  </div>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                  {r.phone}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {data.pending === 0 && data.total > 0 && (
        <div className="dash-all-good">
          ✅ Все записи на сегодня подтверждены. Можно выдохнуть.
        </div>
      )}

      {data.total === 0 && (
        <div className="dash-empty">
          На сегодня записей нет.
          <div style={{ fontSize: 13, marginTop: 6 }}>
            Откройте «Расписание», чтобы создать слоты, или подождите новых заявок.
          </div>
        </div>
      )}

      <div className="dash-section">
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>📅 Завтра</h3>
        <button
          type="button"
          className="dash-tomorrow dash-tomorrow-clickable"
          onClick={() => open('all', 'tomorrow')}
        >
          Записано: <b>{data.tomorrow_count}</b> · показать →
        </button>
      </div>
    </div>
  );
}