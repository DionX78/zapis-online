import { useState, useMemo } from 'react';

export default function ServiceList({ services, onPick }) {
  const [collapsed, setCollapsed] = useState(() => new Set());

  const grouped = useMemo(() => {
    if (!services.length) return [];
    const groups = new Map();
    for (const s of services) {
      const key = s.category_id ?? '__none__';
      if (!groups.has(key)) {
        groups.set(key, {
          id: s.category_id,
          name: s.category_name || 'Прочие услуги',
          sort_order: s.category_sort_order ?? 999999,
          services: [],
        });
      }
      groups.get(key).services.push(s);
    }
    return Array.from(groups.values()).sort((a, b) => {
      if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
      return a.name.localeCompare(b.name, 'ru');
    });
  }, [services]);

  const hasCategories = services.some((s) => s.category_id);

  function toggleCollapse(groupKey) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  }

  if (!services.length) {
    return <div className="card">Услуги пока не настроены.</div>;
  }

  if (!hasCategories) {
    return (
      <div className="card">
        <h2 className="card-title">Выберите услугу</h2>
        {services.map((s) => (
          <div key={s.id} className="service-item" onClick={() => onPick(s)}>
            <div>
              <div className="service-name">{s.name}</div>
              {s.prep && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  {s.prep}
                </div>
              )}
            </div>
            <div className="service-price">{s.price} ₽</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="card-title">Выберите услугу</h2>
      {grouped.map((g) => {
        const groupKey = g.id ?? '__none__';
        const isCollapsed = collapsed.has(groupKey);
        return (
          <div key={groupKey} className="service-group">
            <button
              type="button"
              className="service-group-header"
              onClick={() => toggleCollapse(groupKey)}
              style={{
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                width: '100%',
                fontFamily: 'inherit',
                textAlign: 'left',
              }}
            >
              <span className="service-group-chevron">
                {isCollapsed ? '▶' : '▼'}
              </span>
              <span className="service-group-icon">📂</span>
              <span className="service-group-name">{g.name}</span>
              <span className="service-group-count">
                {g.services.length}
              </span>
            </button>
            {!isCollapsed && (
              <div>
                {g.services.map((s) => (
                  <div key={s.id} className="service-item" onClick={() => onPick(s)}>
                    <div>
                      <div className="service-name">{s.name}</div>
                      {s.prep && (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                          {s.prep}
                        </div>
                      )}
                    </div>
                    <div className="service-price">{s.price} ₽</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}