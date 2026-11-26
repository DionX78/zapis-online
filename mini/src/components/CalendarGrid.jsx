import { useState, useMemo } from 'react';

const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function pad(n) {
  return n < 10 ? '0' + n : '' + n;
}

export default function CalendarGrid({ dates, onPick, onBack }) {
  const availableSet = useMemo(() => new Set(dates), [dates]);

  const [view, setView] = useState(() => {
    if (dates.length) {
      const d = new Date(dates[0]);
      return { year: d.getFullYear(), month: d.getMonth() };
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  const firstDay = new Date(view.year, view.month, 1);
  const lastDay = new Date(view.year, view.month + 1, 0);
  const startWeekday = (firstDay.getDay() + 6) % 7; // пн=0
  const daysInMonth = lastDay.getDate();

  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  function isoFor(day) {
    return `${view.year}-${pad(view.month + 1)}-${pad(day)}`;
  }

  function prevMonth() {
    setView((v) => {
      const m = v.month - 1;
      return m < 0 ? { year: v.year - 1, month: 11 } : { year: v.year, month: m };
    });
  }
  function nextMonth() {
    setView((v) => {
      const m = v.month + 1;
      return m > 11 ? { year: v.year + 1, month: 0 } : { year: v.year, month: m };
    });
  }

  return (
    <div className="card">
      <div className="step-nav">
        <button onClick={onBack}>← Назад</button>
      </div>
      <h2 className="card-title">Выберите дату</h2>
      <div className="calendar-header">
        <button className="calendar-nav" onClick={prevMonth}>‹</button>
        <div className="calendar-month">
          {MONTHS[view.month]} {view.year}
        </div>
        <button className="calendar-nav" onClick={nextMonth}>›</button>
      </div>
      <div className="calendar-grid">
        {WEEKDAYS.map((w) => (
          <div key={w} className="calendar-weekday">{w}</div>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <div key={i} className="calendar-day empty" />;
          const iso = isoFor(day);
          const isAvailable = availableSet.has(iso);
          return (
            <button
              key={i}
              className={`calendar-day ${isAvailable ? 'available' : 'disabled'}`}
              disabled={!isAvailable}
              onClick={() => isAvailable && onPick(iso)}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}