import { useEffect, useState } from 'react';
import { api } from './api.js';
import ServiceList from './components/ServiceList.jsx';
import CalendarGrid from './components/CalendarGrid.jsx';
import TimeGrid from './components/TimeGrid.jsx';
import PhoneForm from './components/PhoneForm.jsx';
import Success from './components/Success.jsx';
import WaitlistForm from './components/WaitlistForm.jsx';
import DoctorPicker from './components/DoctorPicker.jsx';

export default function ClientApp({
  repeatRequestId = null,
  preselectedSlotId = null,
}) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [services, setServices] = useState([]);
  const [dates, setDates] = useState([]);
  const [slots, setSlots] = useState([]);

  const [service, setService] = useState(null);
  const [date, setDate] = useState(null);
  const [slot, setSlot] = useState(null);
  const [result, setResult] = useState(null);

  const [favoriteDoctorId, setFavoriteDoctorId] = useState(null);

  const [waitlistForm, setWaitlistForm] = useState(null);

  useEffect(() => {
    if (preselectedSlotId) {
      loadPreselectedSlot();
      return;
    }
    Promise.all([
      api.getServices(),
      api.getMe().catch(() => null),
    ])
      .then(([servicesData, me]) => {
        setServices(servicesData.services || []);
        if (me && me.favorite_doctor_id) setFavoriteDoctorId(me.favorite_doctor_id);
        if (repeatRequestId) {
          handleRepeat(servicesData.services || []);
        } else {
          setStep('service');
        }
      })
      .catch((e) => {
        setError(e.message);
        setStep('error');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadPreselectedSlot() {
    setStep('loading');
    try {
      const data = await api.getSlot(preselectedSlotId);
      setService(data.service);
      setDate(data.slot.date);
      setSlot(data.slot);
      setSlots([data.slot]);
      setStep('phone');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  async function handleRepeat(servicesList) {
    try {
      const rep = await api.getRepeat(repeatRequestId);
      const svc = (servicesList || []).find((s) => s.id === rep.service_id);
      if (!svc) {
        setStep('service');
        return;
      }
      setService(svc);
      setStep('loading');
      const datesData = await api.getDates(svc.id);
      setDates(datesData.dates || []);
      setStep('date');
    } catch (e) {
      setStep('service');
    }
  }

  async function pickService(svc) {
    setService(svc);
    setError('');
    setStep('loading');
    try {
      const data = await api.getDates(svc.id);
      setDates(data.dates || []);
      setStep('date');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  async function pickDate(d) {
    setDate(d);
    setError('');
    setStep('loading');
    try {
      const data = await api.getSlots(service.id, d);
      setSlots(data.slots || []);
      setStep('time');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  function pickSlot(s) {
    setSlot(s);
    setStep('phone');
  }

  async function toggleFavorite(doctorId) {
    if (!doctorId) return;
    const isSame = favoriteDoctorId === doctorId;
    try {
      const r = await api.setFavoriteDoctor(isSame ? null : doctorId);
      setFavoriteDoctorId(r.favorite_doctor_id || null);
    } catch (e) {
      // тихо — не блокируем запись из-за звёздочки
    }
  }

  async function submitBooking(payload) {
    setStep('loading');
    try {
      const data = await api.book({
        service_id: service.id,
        ...payload,
      });
      setResult(data);
      setStep('success');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  function reset() {
    setService(null);
    setDate(null);
    setSlot(null);
    setResult(null);
    setError('');
    setWaitlistForm(null);
    setStep('service');
  }

  function openWaitlistForm() {
    if (!service) return;
    setWaitlistForm({ service, doctor: null, date });
  }

  function openDoctorPicker() {
    setStep('doctor-picker');
  }

  function closeWaitlistForm() {
    setWaitlistForm(null);
  }

  return (
    <div className="app">
      <div className="header">
        <h1>Запись на приём</h1>
        <p>Онлайн, без звонков</p>
      </div>

      {error && step === 'error' && (
        <div className="error-box">
          {error}
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-primary" onClick={reset}>
              Начать заново
            </button>
          </div>
        </div>
      )}

      {step === 'loading' && <div className="loading">Загрузка…</div>}

      {step === 'service' && (
        <>
          <ServiceList services={services} onPick={pickService} />
          <div className="card" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
              Не нашли подходящую услугу?
            </div>
            <button
              className="btn-link"
              onClick={openDoctorPicker}
              style={{ fontSize: 14 }}
            >
              👤 Записаться к специалисту без услуги
            </button>
          </div>
        </>
      )}

      {step === 'doctor-picker' && (
        <DoctorPicker
          onPick={(doc) => {
            setWaitlistForm({ service: null, doctor: doc, date: null });
            setStep('service');
          }}
          onBack={() => setStep('service')}
        />
      )}

      {step === 'date' && (
        <CalendarGrid dates={dates} onPick={pickDate} onBack={reset} />
      )}

      {step === 'time' && (
        <TimeGrid
          slots={slots}
          date={date}
          onPick={pickSlot}
          onBack={() => setStep('date')}
          favoriteDoctorId={favoriteDoctorId}
          onToggleFavorite={toggleFavorite}
          onJoinWaitlist={openWaitlistForm}
        />
      )}

      {step === 'phone' && (
        <PhoneForm
          service={service}
          date={date}
          slot={slot}
          slots={slots}
          favoriteDoctorId={favoriteDoctorId}
          onSubmit={submitBooking}
          onBack={preselectedSlotId ? reset : () => setStep('time')}
          api={api}
        />
      )}

      {step === 'success' && <Success result={result} onReset={reset} />}

      {waitlistForm && (
        <WaitlistForm
          service={waitlistForm.service}
          doctor={waitlistForm.doctor}
          date={waitlistForm.date}
          api={api}
          onClose={closeWaitlistForm}
          onCreated={() => {
            closeWaitlistForm();
            setStep('success-waitlist');
          }}
        />
      )}

      {step === 'success-waitlist' && (
        <div className="card">
          <div className="success">
            <div className="success-icon waitlist-icon">🔔</div>
            <h2>Заявка в лист ожидания</h2>
            <p>
              Мы сообщим вам, если освободится подходящее время.
            </p>
            <div style={{ marginTop: 24 }}>
              <button className="btn btn-link" onClick={reset}>
                Вернуться на главную
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}