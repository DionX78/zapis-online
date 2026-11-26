import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';
import ClientCardModal from './ClientCardModal.jsx';

function humanTs(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.replace(' ', 'T'));
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
  } catch { return iso; }
}

export default function ClientsPage({ orgId }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [openedUserId, setOpenedUserId] = useState(null);

  async function load(q) {
    setBusy(true);
    setError('');
    try {
      const data = await adminApi.searchClients(orgId, q || '');
      setResults(data.clients || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { load(''); /* eslint-disable-next-line */ }, [orgId]);

  function handleSearch(e) {
    e.preventDefault();
    load(query);
  }

  return (
    <div>
      <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          className="form-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ФИО или телефон"
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-action confirm" style={{ flex: '0 0 auto', padding: '10px 16px' }} disabled={busy}>
          {busy ? '…' : '🔍 Найти'}
        </button>
      </form>

      <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 12, padding: '8px 12px', background: 'var(--primary-soft)', borderRadius: 8 }}>
        Введите ФИО или телефон. Пустой запрос — показать последних обновлённых клиентов.
      </div>

      {error && <div className="error-box" style={{ marginBottom: 12 }}>{error}</div>}

      {busy && <div className="loading">Поиск…</div>}

      {!busy && !results.length && (
        <div className="create-req-empty">Ничего не найдено.</div>
      )}

      {results.map((c) => {
        const fio = [c.last_name, c.first_name, c.middle_name].filter(Boolean).join(' ') || '—';
        return (
          <div
            key={c.user_id}
            className="dir-item visit-clickable"
            onClick={() => setOpenedUserId(c.user_id)}
          >
            <div className="dir-main">
              <div className="dir-title">
                {fio}
                {(c.channels || []).length > 0 && (
                  <span className="tag tag-muted" style={{ marginLeft: 8 }}>
                    {(c.channels || []).map((p) => p.toUpperCase()).join('+')}
                  </span>
                )}
                {(c.channels || []).length === 0 && !c.has_max && (
                  <span className="tag tag-muted" style={{ marginLeft: 8 }}>нет MAX</span>
                )}
              </div>
              <div className="dir-meta">
                {c.phone || '—'}
                {c.last_visit_at && ` · последний визит ${humanTs(c.last_visit_at)}`}
              </div>
            </div>
          </div>
        );
      })}

      {openedUserId && (
        <ClientCardModal
          orgId={orgId}
          userId={openedUserId}
          onClose={() => setOpenedUserId(null)}
          onChanged={() => load(query)}
        />
      )}
    </div>
  );
}