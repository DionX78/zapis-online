import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const FILTERS = [
  { id: '', label: 'Все' },
  { id: 'positive', label: '⭐ 4-5' },
  { id: 'negative', label: '⚠️ 1-3' },
];

const RATING_FILTERS = [
  { id: '', label: 'Любая' },
  { id: '5', label: '5 ⭐' },
  { id: '4', label: '4 ⭐' },
  { id: '3', label: '3 ⭐' },
  { id: '2', label: '2 ⭐' },
  { id: '1', label: '1 ⭐' },
];

function humanTs(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso.replace(' ', 'T'));
    const p = (n) => (n < 10 ? '0' + n : n);
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch { return iso; }
}

function stars(rating) {
  return '⭐'.repeat(rating) + '☆'.repeat(5 - rating);
}

export default function ReviewsPage({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [doctorId, setDoctorId] = useState('');
  const [rating, setRating] = useState('');
  const [reviews, setReviews] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [total, setTotal] = useState(0);

  async function load() {
    setStep('loading');
    setError('');
    try {
      const data = await adminApi.getReviews(orgId, {
        filter: filter || undefined,
        doctor_id: doctorId || undefined,
        rating: rating || undefined,
        limit: 200,
      });
      setReviews(data.reviews || []);
      setDoctors(data.doctors || []);
      setTotal(data.total || 0);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId, filter, doctorId, rating]);

  if (step === 'loading') return <div className="loading">Загрузка…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;

  return (
    <div>
      <div style={{
        fontSize: 13, color: 'var(--text-muted)', marginBottom: 12,
        padding: '8px 12px', background: 'var(--primary-soft)', borderRadius: 8,
      }}>
        Отзывы, которые клиенты оставили после визита (1–5 звёзд).
        Положительные (4–5) видны клиенту как повод оставить отзыв на
        Яндекс.Картах/2ГИС. Отрицательные (1–3) — только вам, для разбора ситуации.
      </div>

      {doctors.length > 0 && (
        <div className="form-group" style={{ marginBottom: 8 }}>
          <select
            className="form-input"
            value={doctorId}
            onChange={(e) => setDoctorId(e.target.value)}
          >
            <option value="">Все специалисты</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>
      )}

      <div className="filters-scroll">
        {FILTERS.map((f) => (
          <button
            key={f.id || 'all'}
            className={'filter-btn' + (filter === f.id ? ' active' : '')}
            onClick={() => { setFilter(f.id); if (f.id !== '') setRating(''); }}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="filters-scroll" style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center', marginRight: 4 }}>
          Оценка:
        </span>
        {RATING_FILTERS.map((f) => (
          <button
            key={f.id || 'any'}
            className={'filter-btn' + (rating === f.id ? ' active' : '')}
            onClick={() => { setRating(f.id); if (f.id !== '') setFilter(''); }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!reviews.length && (
        <div className="dash-empty">
          Пока нет отзывов. Включите запрос отзывов в «⚙️ Настройки → ⭐ Отзывы».
        </div>
      )}

      {reviews.map((r) => {
        const fio = [r.client_last_name, r.client_first_name, r.client_middle_name]
          .filter(Boolean).join(' ') || '—';
        const isNegative = r.rating <= 3;
        return (
          <div key={r.id} className="dir-item" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div className="dir-main">
                <div className="dir-title">
                  {stars(r.rating)}
                  {isNegative && (
                    <span className="tag" style={{ marginLeft: 8, background: '#fdecec', color: '#a83c3c' }}>
                      ⚠️ негатив
                    </span>
                  )}
                </div>
                <div className="dir-meta">
                  <b>{fio}</b>
                  {r.client_phone && ` · ${r.client_phone}`}
                </div>
                {r.service_name && (
                  <div className="dir-meta">
                    {r.service_name}
                    {r.scheduled_at && ` · ${r.scheduled_at}`}
                  </div>
                )}
                {r.doctor && <div className="dir-meta">👤 {r.doctor}</div>}
                {r.comment && (
                  <div className="dir-meta" style={{ marginTop: 4, fontStyle: 'italic' }}>
                    «{r.comment}»
                  </div>
                )}
              </div>
              <div className="audit-ts">{humanTs(r.created_at)}</div>
            </div>
          </div>
        );
      })}

      {reviews.length > 0 && (
        <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, marginTop: 12 }}>
          Показано {reviews.length} из {total}
          {(doctorId || rating || filter) && ' · отфильтровано'}
        </p>
      )}
    </div>
  );
}