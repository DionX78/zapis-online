import { useState, useEffect } from 'react';

const MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

function humanDate(iso) {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

function normalizePhone(text) {
  const digits = text.replace(/\D/g, '');
  if (digits.length === 10) return '+7' + digits;
  if (digits.length === 11 && (digits[0] === '7' || digits[0] === '8')) {
    return '+7' + digits.slice(1);
  }
  return null;
}

export default function PhoneForm({
  service, date, slot, slots = [],
  favoriteDoctorId = null,
  onSubmit, onBack, api,
}) {
  const [selectedSlot, setSelectedSlot] = useState(slot);
  const [phone, setPhone] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [gender, setGender] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [consent, setConsent] = useState(false);
  const [needsConsent, setNeedsConsent] = useState(true);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const originalTime = slot.time;
  const alternatives = (slots || []).filter(
    (s) => s.time === originalTime && s.id !== selectedSlot.id
  );
  const sortedAlternatives = [...alternatives].sort((a, b) => {
    const aFav = a.doctor_id && a.doctor_id === favoriteDoctorId ? 0 : 1;
    const bFav = b.doctor_id && b.doctor_id === favoriteDoctorId ? 0 : 1;
    return aFav - bFav;
  });

  useEffect(() => {
    if (!api) {
      setLoaded(true);
      return;
    }
    api
      .getMe()
      .then((data) => {
        if (data.first_name) setFirstName(data.first_name);
        if (data.last_name) setLastName(data.last_name);
        if (data.middle_name) setMiddleName(data.middle_name);
        if (data.phone) setPhone(data.phone);
        if (data.gender) setGender(data.gender);
        if (data.birth_date) setBirthDate(data.birth_date);
        if (data.consent_152fz) {
          setNeedsConsent(false);
          setConsent(true);
        }
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [api]);

  function submit() {
    const norm = normalizePhone(phone);
    if (!norm) {
      setError('Введите корректный номер телефона');
      return;
    }
    if (!lastName.trim() || !firstName.trim()) {
      setError('Заполните фамилию и имя');
      return;
    }
    if (needsConsent && !consent) {
      setError('Необходимо согласие на обработку персональных данных');
      return;
    }
    setError('');
    onSubmit({
      slot_id: selectedSlot.id,
      phone: norm,
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      middle_name: middleName.trim(),
      gender: gender || null,
      birth_date: birthDate || null,
      consent_152fz: consent || !needsConsent,
    });
  }

  return (
    <div className="card">
      <div className="step-nav">
        <button onClick={onBack}>← Назад</button>
      </div>
      <h2 className="card-title">Подтверждение записи</h2>

      <div className="summary">
        <div><strong>Услуга:</strong> {service.name}</div>
        <div><strong>Дата:</strong> {humanDate(date)}</div>
        <div><strong>Время:</strong> {selectedSlot.time}</div>
        {service.duration_min && (
          <div><strong>Длительность:</strong> {service.duration_min} мин</div>
        )}
        <div><strong>Специалист:</strong> {selectedSlot.doctor_name || 'Любой'}</div>
        {selectedSlot.branch_address && (
          <div><strong>Адрес:</strong> {selectedSlot.branch_address}</div>
        )}
      </div>

      {sortedAlternatives.length > 0 && (
        <div className="form-group">
          <label className="form-label">Сменить специалиста на это время</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sortedAlternatives.map((alt) => {
              const isFav = alt.doctor_id && alt.doctor_id === favoriteDoctorId;
              return (
                <button
                  key={alt.id}
                  type="button"
                  className={'doctor-chip' + (isFav ? ' doctor-chip-favorite' : '')}
                  onClick={() => setSelectedSlot(alt)}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="doctor-chip-name">
                      {alt.doctor_name || 'Без специалиста'}
                      {isFav && <span style={{ color: '#f0b429', marginLeft: 6 }}>★</span>}
                    </div>
                    {alt.branch_address && (
                      <div className="doctor-chip-address">📍 {alt.branch_address}</div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="form-group">
        <label className="form-label">Фамилия</label>
        <input
          className="form-input" type="text"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
          placeholder={loaded ? 'Иванов' : 'Загрузка…'}
        />
      </div>

      <div className="form-group">
        <label className="form-label">Имя</label>
        <input
          className="form-input" type="text"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          placeholder="Иван"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Отчество (если есть)</label>
        <input
          className="form-input" type="text"
          value={middleName}
          onChange={(e) => setMiddleName(e.target.value)}
          placeholder="Иванович"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Телефон для связи</label>
        <input
          className="form-input" type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+7 999 123-45-67"
        />
        {error && <div className="form-error">{error}</div>}
      </div>

      <div className="form-group">
        <label className="form-label">Пол (необязательно)</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={'filter-btn' + (gender === 'male' ? ' active' : '')}
            onClick={() => setGender(gender === 'male' ? '' : 'male')}
            type="button"
          >
            Мужской
          </button>
          <button
            className={'filter-btn' + (gender === 'female' ? ' active' : '')}
            onClick={() => setGender(gender === 'female' ? '' : 'female')}
            type="button"
          >
            Женский
          </button>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Дата рождения (необязательно)</label>
        <input
          className="form-input" type="date"
          value={birthDate}
          onChange={(e) => setBirthDate(e.target.value)}
        />
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
          Мы поздравим вас с днём рождения и подарим скидку 🎉
        </div>
      </div>

      {needsConsent && (
        <label className="checkbox-row" style={{ alignItems: 'flex-start', marginBottom: 14 }}>
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => { setConsent(e.target.checked); setError(''); }}
            style={{ marginTop: 3 }}
          />
          <span style={{ fontSize: 13, lineHeight: 1.4 }}>
            Согласен на обработку персональных данных в соответствии с
            152-ФЗ. Данные используются для записи на приём и напоминаний.
          </span>
        </label>
      )}

      <button className="btn btn-primary" onClick={submit}>
        Записаться
      </button>
    </div>
  );
}