const MONTHS_SHORT = [
  'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

function humanDate(iso) {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

const BRANCH_COLORS = [
  { bg: '#e3f0fb', border: '#3a8dde', text: '#2e5f8a' },
  { bg: '#e3f5e9', border: '#2d7a4b', text: '#1f5f36' },
  { bg: '#fff4d9', border: '#b8851a', text: '#8b5a00' },
  { bg: '#f3e8fa', border: '#8b5cf6', text: '#5b3d8a' },
  { bg: '#fde7ee', border: '#d9467a', text: '#8a2c4e' },
  { bg: '#e8f3f4', border: '#1f8b9c', text: '#145f6a' },
];

function colorForBranch(branchId) {
  if (!branchId) return null;
  const n = typeof branchId === 'number' ? branchId : String(branchId).charCodeAt(0);
  return BRANCH_COLORS[n % BRANCH_COLORS.length];
}

export default function TimeGrid({
  slots, date, onPick, onBack,
  favoriteDoctorId = null,
  onToggleFavorite = null,
  onJoinWaitlist = null,
}) {
  const byBranch = new Map();
  for (const s of slots) {
    const key = s.branch_id ?? '__none__';
    if (!byBranch.has(key)) {
      byBranch.set(key, {
        branch_id: s.branch_id,
        branch_name: s.branch_name || 'Без филиала',
        branch_address: s.branch_address || null,
        slots: [],
      });
    }
    byBranch.get(key).slots.push(s);
  }

  const branches = Array.from(byBranch.values());
  const showBranchSections = branches.length > 1;

  function groupByTime(list) {
    const g = {};
    for (const s of list) {
      if (!g[s.time]) g[s.time] = [];
      g[s.time].push(s);
    }
    return Object.keys(g).sort().map((time) => ({ time, slots: g[time] }));
  }

  function sortedSlotsForFav(list) {
    return [...list].sort((a, b) => {
      const aFav = a.doctor_id && a.doctor_id === favoriteDoctorId ? 0 : 1;
      const bFav = b.doctor_id && b.doctor_id === favoriteDoctorId ? 0 : 1;
      return aFav - bFav;
    });
  }

  function renderDoctorChip(s) {
    const isFav = s.doctor_id && s.doctor_id === favoriteDoctorId;
    return (
      <button
        key={s.id}
        className={'doctor-chip' + (isFav ? ' doctor-chip-favorite' : '')}
        onClick={() => onPick(s)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="doctor-chip-name">
            {s.doctor_name || 'Без специалиста'}
            {onToggleFavorite && s.doctor_id && (
              <span
                className={'fav-star' + (isFav ? ' fav-star-active' : '')}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleFavorite(s.doctor_id);
                }}
                title={isFav ? 'Убрать из любимых' : 'Сделать любимым специалистом'}
              >
                {isFav ? '★' : '☆'}
              </span>
            )}
          </div>
          {!showBranchSections && s.branch_address && (
            <div className="doctor-chip-address">📍 {s.branch_address}</div>
          )}
        </div>
      </button>
    );
  }

  function renderTimeGroups(list) {
    const groups = groupByTime(list);
    return (
      <div className="time-grid-grouped">
        {groups.map(({ time, slots: timeSlots }) => {
          const sorted = sortedSlotsForFav(timeSlots);
          return (
            <div key={time} className="time-group">
              <div className="time-group-header">
                <div className="time-slot-time">{time}</div>
                {sorted.length > 1 && (
                  <div className="time-group-badge">{sorted.length} специалиста</div>
                )}
              </div>
              <div className="time-group-doctors">
                {sorted.map(renderDoctorChip)}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (!slots.length) {
    return (
      <div className="card">
        <div className="step-nav">
          <button onClick={onBack}>← Назад</button>
        </div>
        <h2 className="card-title">Свободное время на {humanDate(date)}</h2>
        <div>Свободных слотов нет.</div>
        {onJoinWaitlist && (
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-primary" onClick={onJoinWaitlist}>
              🔔 Сообщите, если освободится
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <div className="step-nav">
        <button onClick={onBack}>← Назад</button>
      </div>
      <h2 className="card-title">Свободное время на {humanDate(date)}</h2>

      {showBranchSections && (
        <div className="branch-sections-note">
          В этот день приём ведётся в разных филиалах — проверяйте адрес при выборе времени.
        </div>
      )}

      {!showBranchSections && renderTimeGroups(slots)}

      {showBranchSections && branches.map((b) => {
        const c = colorForBranch(b.branch_id) || {
          bg: 'var(--bg)', border: 'var(--border)', text: 'var(--text-muted)',
        };
        return (
          <div
            key={b.branch_id ?? '__none__'}
            className="branch-section"
            style={{ borderLeftColor: c.border }}
          >
            <div
              className="branch-section-header"
              style={{ background: c.bg, color: c.text }}
            >
              <div className="branch-section-name">🏢 {b.branch_name}</div>
              {b.branch_address && (
                <div className="branch-section-address">📍 {b.branch_address}</div>
              )}
            </div>
            {renderTimeGroups(b.slots)}
          </div>
        );
      })}

      {onJoinWaitlist && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button className="btn-link" onClick={onJoinWaitlist}>
            🔔 Не нашли удобное время? Оставьте заявку
          </button>
        </div>
      )}
    </div>
  );
}