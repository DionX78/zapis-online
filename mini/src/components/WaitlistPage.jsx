import { useEffect, useState } from 'react';
import { api } from '../api.js';
import ServiceList from './ServiceList.jsx';
import DoctorPicker from './DoctorPicker.jsx';
import WaitlistForm from './WaitlistForm.jsx';

const MONTHS_SHORT = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];

function humanDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]}`;
}

const PREFERRED_LABELS = {
  morning: 'утро',
  afternoon: 'день',
  evening: 'вечер',
  any: 'любое',
};

export default function WaitlistPage() {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [entries, setEntries] = useState([]);
  const [services, setServices] = useState([]);

  const [selectedService, setSelectedService] = useState(null);
  const [selectedDoctor, setSelectedDoctor] = useState(null);

  const [busyId, setBusyId] = useState(null);

  async function load() {
    setStep('loading');
    setError('');
    try {
      const data = await api.getWaitlist();
      setEntries(data.entries || []);
      setStep('list');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function startCreateByService() {
    setStep('loading');
    try {
      const data = await api.getServices();
      setServices(data.services || []);
      setStep('service');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  function startCreateByDoctor() {
    setStep('doctor');
  }

  function pickService(svc) {
    setSelectedService(svc);
    setSelectedDoctor(null);
    setStep('form');
  }

  function pickDoctor(doc) {
    setSelectedService(null);
    setSelectedDoctor(doc);
    setStep('form');
  }

  async function cancelEntry(wid) {
    if (!window.confirm('Удалить заявку?')) return;
    setBusyId(wid);
    try {
      await api.cancelWaitlist(wid);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setBusyId(null);
    }
  }

  function closeApp() {
    if (window.WebApp && typeof window.WebApp.close === 'function') {
      window.WebApp.close();
    }
  }

  return (
    <div className="app">
      <div className="header">
        <h1>Лист ожидания</h1>
        <p>Сообщим, если освободится время</p>
      </div>

      {step === 'loading' && <div className="loading">Загрузка…</div>}

      {step === 'error' && (
        <div className="error-box">
          {error}
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-primary" onClick={load}>Повторить</button>
          </div>
        </div>
      )}

      {step === 'list' && (
        <>
          <div className="card">
            <h2 className="card-title">Активные заявки</h2>
            {!entries.length && (
              <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
                У вас нет активных заявок в листе ожидания.
              </div>
            )}
            {entries.map((e) => (
              <div key={e.id} className="dir-item" style={{ alignItems: 'center' }}>
                <div className="dir-main">
                  <div className="dir-title">
                    {e.service_name ? e.service_name : (e.doctor_name ? `👤 ${e.doctor_name}` : '—')}
                  </div>
                  <div className="dir-meta">
                    📅 {humanDate(e.date_from)} — {humanDate(e.date_to)}
                    {e.preferred_time && ` · ${PREFERRED_LABELS[e.preferred_time] || e.preferred_time}`}
                  </div>
                  {e.doctor_name && e.service_name && (
                    <div className="dir-meta">👤 {e.doctor_name}</div>
                  )}
                </div>
                <div className="dir-actions">
                  <button
                    className="dir-btn danger"
                    onClick={() => cancelEntry(e.id)}
                    disabled={busyId === e.id}
                    title="Удалить заявку"
                  >
                    {busyId === e.id ? '…' : '🗑'}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="card">
            <h2 className="card-title">Добавить заявку</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button className="btn btn-primary" onClick={startCreateByService}>
                💼 По услуге
              </button>
              <button className="btn btn-primary" onClick={startCreateByDoctor}>
                👤 К специалисту (без услуги)
              </button>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <button className="btn-link" onClick={closeApp}>Закрыть</button>
          </div>
        </>
      )}

      {step === 'service' && (
        <ServiceList services={services} onPick={pickService} />
      )}

      {step === 'doctor' && (
        <DoctorPicker
          onPick={pickDoctor}
          onBack={() => setStep('list')}
        />
      )}

      {step === 'form' && (selectedService || selectedDoctor) && (
        <WaitlistForm
          service={selectedService}
          doctor={selectedDoctor}
          date={null}
          api={api}
          onClose={() => {
            setSelectedService(null);
            setSelectedDoctor(null);
            setStep('list');
          }}
          onCreated={async () => {
            setSelectedService(null);
            setSelectedDoctor(null);
            await load();
          }}
        />
      )}
    </div>
  );
}