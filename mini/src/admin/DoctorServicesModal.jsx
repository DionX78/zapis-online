import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

export default function DoctorServicesModal({ orgId, doctor, onClose }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [services, setServices] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [allServicesMode, setAllServicesMode] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  async function load() {
    setStep('loading');
    try {
      const [svcData, docData] = await Promise.all([
        adminApi.getServices(orgId),
        adminApi.getDoctorServices(orgId, doctor.id),
      ]);
      const svcList = (svcData.services || []).filter((s) => s.active);
      setServices(svcList);
      const assigned = new Set(docData.service_ids || []);
      setSelected(assigned);
      setAllServicesMode(assigned.size === 0);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId, doctor.id]);

  function toggleService(sid) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });
    setSaveMsg('');
  }

  function toggleAll(sidList) {
    if (selected.size === sidList.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(sidList));
    }
    setSaveMsg('');
  }

  function selectAll() {
    setAllServicesMode(true);
    setSelected(new Set());
    setSaveMsg('');
  }

  function selectSpecific() {
    setAllServicesMode(false);
    setSaveMsg('');
  }

  async function handleSave() {
    setSaving(true);
    setSaveMsg('');
    setError('');
    try {
      const ids = allServicesMode ? [] : Array.from(selected);
      await adminApi.setDoctorServices(orgId, doctor.id, ids);
      setSaveMsg('✅ Сохранено');
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (step === 'loading') return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="loading">Загрузка…</div>
      </div>
    </div>
  );

  if (step === 'error') return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="error-box">Ошибка: {error}</div>
        <div className="actions" style={{ marginTop: 12 }}>
          <button className="btn-action reject" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );

  // Группировка услуг по категориям для удобства
  const byCategory = new Map();
  for (const s of services) {
    const key = s.category_id ?? '__none__';
    if (!byCategory.has(key)) {
      byCategory.set(key, {
        id: s.category_id,
        name: s.category_name || 'Прочие услуги',
        sort_order: s.category_sort_order ?? 999999,
        items: [],
      });
    }
    byCategory.get(key).items.push(s);
  }
  const categories = Array.from(byCategory.values()).sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.name.localeCompare(b.name, 'ru');
  });

  const allSelected = !allServicesMode
    && services.length > 0
    && selected.size === services.length;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
        <h2 className="card-title">💼 Услуги специалиста: {doctor.name}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0, marginBottom: 16 }}>
          Клиент увидит специалиста только для отмеченных услуг. Если не отметить
          ни одной — специалист показывается для всех услуг (по умолчанию).
        </p>

        <div
          style={{
            padding: 12,
            background: 'var(--bg)',
            borderRadius: 10,
            marginBottom: 16,
          }}
        >
          <label className="radio-row" style={{ paddingBottom: 8 }}>
            <input
              type="radio"
              name="services-mode"
              checked={allServicesMode}
              onChange={selectAll}
              disabled={saving}
            />
            <div>
              <div className="radio-label">Делает все услуги</div>
              <div className="radio-hint">
                Специалист показывается для любой услуги. Удобно для новых —
                потом можно сузить список.
              </div>
            </div>
          </label>
          <label className="radio-row" style={{ paddingBottom: 0 }}>
            <input
              type="radio"
              name="services-mode"
              checked={!allServicesMode}
              onChange={selectSpecific}
              disabled={saving}
            />
            <div>
              <div className="radio-label">Только выбранные услуги</div>
              <div className="radio-hint">
                Отметьте ниже, какие услуги делает специалист. Клиент увидит его
                только там.
              </div>
            </div>
          </label>
        </div>

        {!allServicesMode && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                Отмечено {selected.size} из {services.length}
              </span>
              {services.length > 0 && (
                <button
                  type="button"
                  className="btn-link"
                  style={{ fontSize: 12, padding: 0 }}
                  onClick={() => toggleAll(services.map((s) => s.id))}
                  disabled={saving}
                >
                  {allSelected ? 'Снять выделение' : 'Выделить все'}
                </button>
              )}
            </div>

            <div
              className="service-checkbox-list"
              style={{ maxHeight: '50vh', marginBottom: 16 }}
            >
              {services.length === 0 && (
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                  Услуг пока нет
                </span>
              )}
              {categories.map((cat) => (
                <div key={cat.id ?? '__none__'}>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: 'var(--primary)',
                      padding: '6px 4px 2px',
                      borderBottom: '1px solid var(--border)',
                      marginBottom: 2,
                    }}
                  >
                    📂 {cat.name}
                  </div>
                  {cat.items.map((s) => (
                    <label key={s.id} className="checkbox-row" style={{ padding: '4px 0 4px 8px' }}>
                      <input
                        type="checkbox"
                        checked={selected.has(s.id)}
                        onChange={() => toggleService(s.id)}
                        disabled={saving}
                      />
                      <span>{s.name}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </>
        )}

        {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}

        <div className="actions">
          <button
            className="btn-action confirm"
            onClick={handleSave}
            disabled={saving || (!allServicesMode && selected.size === 0 && services.length > 0)}
            title={!allServicesMode && selected.size === 0 && services.length > 0
              ? 'Выберите хотя бы одну услугу или переключитесь на «Делает все услуги»'
              : undefined}
          >
            {saving ? 'Сохранение…' : '💾 Сохранить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={saving}>
            Закрыть
          </button>
        </div>
        {saveMsg && (
          <div style={{ color: 'var(--accent)', fontSize: 13, marginTop: 12, textAlign: 'center' }}>
            {saveMsg}
          </div>
        )}
      </div>
    </div>
  );
}