import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

function humanTs(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

export default function BlockedUsersPage({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [users, setUsers] = useState([]);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    setStep('loading');
    setError('');
    try {
      const data = await adminApi.getBlockedUsers(orgId);
      setUsers(data.users || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleUnblock(userId) {
    if (!window.confirm('Разблокировать клиента? Он снова сможет записываться.')) return;
    setBusyId(userId);
    try {
      await adminApi.unblockClient(orgId, userId);
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
      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 13,
          marginBottom: 12,
          padding: '8px 12px',
          background: 'var(--primary-soft)',
          borderRadius: 8,
        }}
      >
        Заблокированные клиенты не могут создавать новые записи. Существующие
        активные записи остаются в силе — их можно отменить отдельно в разделе «Заявки».
        Разблокировка возвращает доступ.
      </div>

      {!users.length && (
        <div className="dash-empty">
          Заблокированных клиентов нет.
        </div>
      )}

      {users.map((u) => (
        <div key={u.user_id} className="dir-item">
          <div className="dir-main">
            <div className="dir-title">
              🚫 MAX ID: {u.user_id}
            </div>
            <div className="dir-meta">📞 {u.phone || '—'}</div>
            {u.reason && <div className="dir-meta">Причина: {u.reason}</div>}
            <div className="dir-meta" style={{ fontSize: 12 }}>
              Заблокирован: {humanTs(u.blocked_at)}
              {u.blocked_by && ` · кем: ${u.blocked_by}`}
            </div>
          </div>
          <div className="dir-actions">
            <button
              className="dir-btn"
              onClick={() => handleUnblock(u.user_id)}
              disabled={busyId === u.user_id}
              title="Разблокировать"
            >
              ↩
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}