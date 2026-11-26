import { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function DoctorPicker({ onPick, onBack }) {
  const [doctors, setDoctors] = useState([]);
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    api.getDoctors()
      .then((d) => { setDoctors(d.doctors || []); setStep('ready'); })
      .catch((e) => { setError(e.message); setStep('error'); });
  }, []);

  if (step === 'loading') return <div className="loading">Загрузка…</div>;
  if (step === 'error') return (
    <div className="error-box">
      Ошибка: {error}
      <div style={{ marginTop: 12 }}>
        <button className="btn btn-primary" onClick={onBack}>Назад</button>
      </div>
    </div>
  );
  if (!doctors.length) {
    return (
      <div className="card">
        <div className="step-nav">
          <button onClick={onBack}>← Назад</button>
        </div>
        <div>Специалистов пока нет.</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="step-nav">
        <button onClick={onBack}>← Назад</button>
      </div>
      <h2 className="card-title">Выберите специалиста</h2>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
        Мы сообщим, если у выбранного специалиста освободится время.
      </div>
      {doctors.map((d) => (
        <div key={d.id} className="service-item" onClick={() => onPick(d)}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flex: 1, minWidth: 0 }}>
            {d.photo_url ? (
              <img
                src={d.photo_url}
                alt={d.name}
                style={{
                  width: 40, height: 40, borderRadius: '50%',
                  objectFit: 'cover', flexShrink: 0,
                }}
              />
            ) : (
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                background: 'var(--primary-soft)', color: 'var(--primary)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 16, fontWeight: 600, flexShrink: 0,
              }}>
                {(d.name || '').split(/\s+/).map((x) => x[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '👤'}
              </div>
            )}
            <div style={{ minWidth: 0 }}>
              <div className="service-name">{d.name}</div>
              {d.specialty && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {d.specialty}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}