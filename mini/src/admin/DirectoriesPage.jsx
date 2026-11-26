import { useEffect, useRef, useState } from 'react';
import { adminApi } from './adminApi.js';
import DoctorScheduleModal from './DoctorScheduleModal.jsx';
import DoctorServicesModal from './DoctorServicesModal.jsx';

const TABS = [
  { id: 'branches',   label: '🏢 Филиалы' },
  { id: 'doctors',    label: '👨‍⚕️ Специалисты' },
  { id: 'services',   label: '💼 Услуги' },
  { id: 'categories', label: '📂 Категории' },
];

function todayIso() {
  const d = new Date();
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function formatStopBadge(stopDate) {
  if (!stopDate) return null;
  const today = todayIso();
  const [y, m, d] = stopDate.split('-');
  const human = `${d}.${m}.${y}`;
  if (stopDate <= today) {
    return { text: '⏸ генерация остановлена', style: { background: '#fdecec', color: '#a83c3c' } };
  }
  return { text: `⏸ генерируется до ${human}`, style: { background: '#fff4d9', color: '#8b5a00' } };
}

function servicesBadge(servicesCount) {
  if (servicesCount === 0) {
    return { text: '💼 все услуги', style: { background: '#e3f0fb', color: '#2e5f8a' } };
  }
  const word = servicesCount === 1 ? 'услуга' : servicesCount < 5 ? 'услуги' : 'услуг';
  return {
    text: `💼 ${servicesCount} ${word}`,
    style: { background: '#e8f3f4', color: '#145f6a' },
  };
}

export default function DirectoriesPage({ orgId }) {
  const [tab, setTab] = useState('branches');

  return (
    <div>
      <div className="filters" style={{ marginBottom: 12 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={'filter-btn' + (tab === t.id ? ' active' : '')}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'branches'   && <BranchesSection orgId={orgId} />}
      {tab === 'doctors'    && <DoctorsSection orgId={orgId} />}
      {tab === 'services'   && <ServicesSection orgId={orgId} />}
      {tab === 'categories' && <CategoriesSection orgId={orgId} />}
    </div>
  );
}


// ---------- Филиалы ----------

function BranchesSection({ orgId }) {
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [settingPrimaryId, setSettingPrimaryId] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const data = await adminApi.getBranches(orgId);
      setBranches(data.branches || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleSave(form) {
    const isNew = !form.id;
    const wasPrimary = !isNew && !!form._wasPrimary;
    const wantPrimary = !!form._setPrimary;
    const payload = { name: form.name, address: form.address, phone: form.phone };

    let branchesFromResponse = null;

    if (isNew) {
      await adminApi.createBranch(orgId, payload);
    } else {
      await adminApi.updateBranch(orgId, form.id, payload);
      if (wantPrimary && !wasPrimary) {
        const r = await adminApi.setPrimaryBranch(orgId, form.id);
        if (r && Array.isArray(r.branches)) {
          branchesFromResponse = r.branches;
        }
      }
    }
    setEditing(null);
    if (branchesFromResponse) {
      setBranches(branchesFromResponse);
    } else {
      await load();
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить филиал? Специалисты этого филиала тоже могут пострадать.')) return;
    try {
      await adminApi.deleteBranch(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handleSetPrimary(id) {
    setSettingPrimaryId(id);
    try {
      const r = await adminApi.setPrimaryBranch(orgId, id);
      if (r && Array.isArray(r.branches)) {
        setBranches(r.branches);
      } else {
        await load();
      }
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setSettingPrimaryId(null);
    }
  }

  if (loading) return <div className="loading">Загрузка…</div>;

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setEditing({
          name: '', address: '', phone: '',
          _setPrimary: branches.length === 0,
        })}
      >
        ➕ Добавить филиал
      </button>

      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 13,
          marginBottom: 12,
          padding: '8px 12px',
          background: 'var(--primary-soft)',
          borderRadius: 8,
        }}
      >
        Основной филиал — используется по умолчанию при создании записей,
        специалистов и слотов. Всегда ровно один.
      </div>

      {!branches.length && <p style={{ color: 'var(--text-muted)' }}>Филиалов пока нет.</p>}

      {branches.map((b) => (
        <div key={b.id} className="dir-item">
          <div className="dir-main">
            <div className="dir-title">
              {b.name}
              {b.is_primary && (
                <span
                  className="tag"
                  style={{
                    marginLeft: 8,
                    background: 'var(--primary-soft)',
                    color: 'var(--primary)',
                  }}
                >
                  🏠 основной
                </span>
              )}
            </div>
            <div className="dir-meta">{b.address || '—'}</div>
            <div className="dir-meta">{b.phone || '—'}</div>
          </div>
          <div className="dir-actions">
            {!b.is_primary && (
              <button
                className="dir-btn"
                onClick={() => handleSetPrimary(b.id)}
                disabled={settingPrimaryId === b.id}
                title="Сделать основным"
              >
                {settingPrimaryId === b.id ? '…' : '🏠'}
              </button>
            )}
            <button
              className="dir-btn"
              onClick={() => setEditing({
                ...b,
                _wasPrimary: !!b.is_primary,
                _setPrimary: !!b.is_primary,
              })}
            >✏️</button>
            <button className="dir-btn danger" onClick={() => handleDelete(b.id)}>🗑</button>
          </div>
        </div>
      ))}

      {editing && (
        <ModalForm
          title={editing.id ? 'Редактировать филиал' : 'Новый филиал'}
          onClose={() => setEditing(null)}
          onSave={handleSave}
          fields={[
            { key: 'name',    label: 'Название', required: true },
            { key: 'address', label: 'Адрес' },
            { key: 'phone',   label: 'Телефон' },
            {
              key: '_setPrimary',
              label: 'Основной филиал (🏠)',
              type: 'checkbox',
              hint: 'Используется по умолчанию при создании записей, специалистов и слотов.',
            },
          ]}
          initial={editing}
        />
      )}
    </div>
  );
}


// ---------- Специалисты ----------

function DoctorsSection({ orgId }) {
  const [doctors, setDoctors] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [scheduleFor, setScheduleFor] = useState(null);
  const [servicesFor, setServicesFor] = useState(null);
  const [photoUploadingId, setPhotoUploadingId] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [docsData, brData] = await Promise.all([
        adminApi.getDoctorsByOrg(orgId),
        adminApi.getBranches(orgId),
      ]);
      setDoctors(docsData.doctors || []);
      setBranches(brData.branches || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleSave(form) {
    const isNew = !form.id;
    const payload = {
      name: form.name,
      specialty: form.specialty,
      branch_id: form.branch_id,
      education: form.education || '',
      courses: form.courses || '',
      about: form.about || '',
    };
    if (isNew) {
      await adminApi.createDoctor(orgId, payload);
    } else {
      await adminApi.updateDoctor(orgId, form.id, payload);
    }
    setEditing(null);
    await load();
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить специалиста?')) return;
    try {
      await adminApi.deleteDoctor(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  async function handlePhotoUpload(doctorId, file) {
    if (!file) return;
    if (!['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
      alert('Только JPEG/PNG/WebP/GIF');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('Файл больше 10 МБ');
      return;
    }
    setPhotoUploadingId(doctorId);
    try {
      const r = await adminApi.uploadDoctorPhoto(orgId, doctorId, file);
      setDoctors((arr) => arr.map((d) => d.id === doctorId ? { ...d, photo_url: r.photo_url } : d));
    } catch (e) {
      alert('Ошибка загрузки: ' + e.message);
    } finally {
      setPhotoUploadingId(null);
    }
  }

  async function handlePhotoDelete(doctorId) {
    if (!window.confirm('Удалить фото специалиста?')) return;
    setPhotoUploadingId(doctorId);
    try {
      await adminApi.deleteDoctorPhoto(orgId, doctorId);
      setDoctors((arr) => arr.map((d) => d.id === doctorId ? { ...d, photo_url: null } : d));
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setPhotoUploadingId(null);
    }
  }

  if (loading) return <div className="loading">Загрузка…</div>;

  if (!branches.length) {
    return (
      <div className="error-box">
        Сначала создайте хотя бы один филиал в разделе «🏢 Филиалы».
      </div>
    );
  }

  const branchNameById = {};
  for (const b of branches) branchNameById[b.id] = b.name;

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setEditing({ name: '', specialty: '', branch_id: branches[0].id, education: '', courses: '', about: '' })}
      >
        ➕ Добавить специалиста
      </button>

      {!doctors.length && <p style={{ color: 'var(--text-muted)' }}>Специалистов пока нет.</p>}

      {doctors.map((d) => {
        const stopBadge = formatStopBadge(d.schedule_stop_date);
        const svcBadge = servicesBadge(d.services_count || 0);
        const primaryName = d.branch_name || branchNameById[d.branch_id] || '—';
        const otherBranchesCount = (d.branch_ids || []).filter((bid) => bid !== d.branch_id).length;
        const isUploading = photoUploadingId === d.id;
        const initials = (d.name || '').split(/\s+/).map((x) => x[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '👤';
        return (
          <div key={d.id} className="doctor-card">
            {/* Строка 1: аватар слева + ФИО на всю оставшуюся ширину */}
            <div className="doctor-card-top">
              <DoctorAvatarInline
                doctor={d}
                initials={initials}
                uploading={isUploading}
                onUpload={(file) => handlePhotoUpload(d.id, file)}
                onDelete={() => handlePhotoDelete(d.id)}
              />
              <button
                type="button"
                className="doctor-card-name"
                onClick={() => setEditing(d)}
                title="Нажмите, чтобы отредактировать"
              >
                {d.name}
              </button>
            </div>

            {/* Строка 2: «генерируется до …» (если задано) */}
            {stopBadge && (
              <div className="doctor-card-row doctor-card-stop">
                <span className="tag" style={stopBadge.style}>{stopBadge.text}</span>
              </div>
            )}

            {/* Строка 3: кнопки-иконки */}
            <div className="doctor-card-row doctor-card-actions">
              <button className="dir-btn" onClick={() => setServicesFor(d)} title="Услуги специалиста">💼</button>
              <button className="dir-btn" onClick={() => setScheduleFor(d)} title="График и смены">📅</button>
              <button className="dir-btn" onClick={() => setEditing(d)} title="Редактировать">✏️</button>
              <button className="dir-btn danger" onClick={() => handleDelete(d.id)} title="Удалить">🗑</button>
            </div>

            {/* Строка 4: специальность, филиал, услуги */}
            <div className="doctor-card-row doctor-card-meta">
              {d.specialty && (
                <div className="doctor-card-specialty">{d.specialty}</div>
              )}
              <div className="doctor-card-tags">
                <span className="tag" style={{ background: 'var(--bg)', color: 'var(--text-muted)' }}>
                  🏢 {primaryName}
                </span>
                {otherBranchesCount > 0 && (
                  <span
                    className="tag"
                    style={{ background: 'var(--primary-soft)', color: 'var(--primary)' }}
                    title="Также ведёт приём в других филиалах — см. «📅 График»"
                  >
                    +{otherBranchesCount} филиал{otherBranchesCount === 1 ? '' : otherBranchesCount < 5 ? 'а' : 'ов'}
                  </span>
                )}
                <span className="tag" style={svcBadge.style}>{svcBadge.text}</span>
                {d.reviews_count > 0 && (
                  <span
                    className="tag"
                    style={{ background: '#fff4d9', color: '#8b5a00' }}
                    title={`${d.reviews_count} отзыв(ов)`}
                  >
                    ⭐ {d.avg_rating.toFixed(1)} ({d.reviews_count})
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {editing && (
        <DoctorForm
          title={editing.id ? 'Редактировать специалиста' : 'Новый специалист'}
          onClose={() => setEditing(null)}
          onSave={handleSave}
          branches={branches}
          initial={editing}
        />
      )}

      {scheduleFor && (
        <DoctorScheduleModal
          orgId={orgId}
          doctor={scheduleFor}
          onClose={() => { setScheduleFor(null); load(); }}
        />
      )}

      {servicesFor && (
        <DoctorServicesModal
          orgId={orgId}
          doctor={servicesFor}
          onClose={() => { setServicesFor(null); load(); }}
        />
      )}
    </div>
  );
}


function DoctorAvatarInline({ doctor, initials, uploading, onUpload, onDelete }) {
  const fileRef = useRef(null);
  return (
    <div style={{ position: 'relative', flexShrink: 0 }}>
      <div
        onClick={() => !uploading && fileRef.current?.click()}
        title={doctor.photo_url ? 'Заменить фото' : 'Загрузить фото'}
        style={{
          width: 60, height: 60, borderRadius: '50%',
          border: '2px solid var(--border)',
          background: doctor.photo_url ? 'var(--bg)' : 'var(--primary-soft)',
          color: 'var(--primary)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: doctor.photo_url ? 0 : 20, fontWeight: 600,
          overflow: 'hidden', cursor: uploading ? 'wait' : 'pointer',
          position: 'relative',
        }}
      >
        {doctor.photo_url ? (
          <img src={doctor.photo_url} alt={doctor.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : initials}
        {uploading && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'rgba(0,0,0,0.45)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10,
          }}>…</div>
        )}
      </div>
      {doctor.photo_url && !uploading && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Удалить фото"
          style={{
            position: 'absolute', top: -2, right: -2,
            width: 20, height: 20, borderRadius: '50%',
            background: '#fff', border: '1px solid var(--border)',
            color: 'var(--danger)', cursor: 'pointer',
            fontSize: 10, lineHeight: 1, padding: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >✕</button>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files && e.target.files[0];
          if (fileRef.current) fileRef.current.value = '';
          if (f) onUpload(f);
        }}
      />
    </div>
  );
}


function DoctorForm({ title, onClose, onSave, branches, initial }) {
  const [form, setForm] = useState({
    id: initial.id,
    name: initial.name || '',
    specialty: initial.specialty || '',
    branch_id: initial.branch_id || (branches[0] && branches[0].id),
    education: initial.education || '',
    courses: initial.courses || '',
    about: initial.about || '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit() {
    if (!form.name.trim()) { setError('ФИО обязательно'); return; }
    if (!form.branch_id) { setError('Основной филиал обязателен'); return; }
    setError('');
    setBusy(true);
    try {
      await onSave(form);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 620 }}>
        <h2 className="card-title">{title}</h2>

        <div className="form-group">
          <label className="form-label">ФИО</label>
          <input
            className="form-input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            disabled={busy}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Специальность</label>
          <input
            className="form-input"
            value={form.specialty}
            onChange={(e) => setForm({ ...form, specialty: e.target.value })}
            placeholder="УЗИ-диагност, косметолог, парикмахер-стилист…"
            disabled={busy}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Основной филиал</label>
          <select
            className="form-input"
            value={form.branch_id}
            onChange={(e) => setForm({ ...form, branch_id: parseInt(e.target.value, 10) })}
            disabled={busy}
          >
            {branches.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Филиал по умолчанию. Специалист может работать и в других филиалах — задаётся в «📅 График».
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Образование</label>
          <textarea
            className="form-input"
            rows={3}
            value={form.education}
            onChange={(e) => setForm({ ...form, education: e.target.value })}
            placeholder="МГМСУ им. Евдокимова, 2015, лечебное дело"
            disabled={busy}
            maxLength={2000}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Курсы и повышение квалификации</label>
          <textarea
            className="form-input"
            rows={3}
            value={form.courses}
            onChange={(e) => setForm({ ...form, courses: e.target.value })}
            placeholder="УЗИ-диагностика, 2019; ЭХО-КГ, 2021"
            disabled={busy}
            maxLength={2000}
          />
        </div>

        <div className="form-group">
          <label className="form-label">О специалисте</label>
          <textarea
            className="form-input"
            rows={4}
            value={form.about}
            onChange={(e) => setForm({ ...form, about: e.target.value })}
            placeholder="Стаж 10 лет, специализация на УЗИ-диагностике..."
            disabled={busy}
            maxLength={5000}
          />
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Используется в карточке специалиста в клиентских приложениях (в будущем — ИИ-ассистентом).
          </div>
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={handleSubmit} disabled={busy}>
            {busy ? 'Сохранение…' : '✅ Сохранить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>Отмена</button>
        </div>
      </div>
    </div>
  );
}


// ---------- Категории ----------

function CategoriesSection({ orgId }) {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const data = await adminApi.getServiceCategories(orgId);
      setCategories(data.categories || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleSave(form) {
    const isNew = !form.id;
    const payload = {
      name: (form.name || '').trim(),
      sort_order: parseInt(form.sort_order || 100, 10),
    };
    if (isNew) {
      await adminApi.createServiceCategory(orgId, payload);
    } else {
      await adminApi.updateServiceCategory(orgId, form.id, payload);
    }
    setEditing(null);
    await load();
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить категорию? Это возможно только если в ней нет услуг.')) return;
    try {
      await adminApi.deleteServiceCategory(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  if (loading) return <div className="loading">Загрузка…</div>;

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setEditing({ name: '', sort_order: 100 })}
      >
        ➕ Добавить категорию
      </button>

      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 13,
          marginBottom: 12,
          padding: '8px 12px',
          background: 'var(--primary-soft)',
          borderRadius: 8,
        }}
      >
        Категории помогают клиенту быстрее найти нужную услугу в Mini App.
        Порядок отображения — по «Порядку» (меньше — выше).
      </div>

      {!categories.length && <p style={{ color: 'var(--text-muted)' }}>Категорий пока нет.</p>}

      {categories.map((c) => (
        <div key={c.id} className="dir-item">
          <div className="dir-main">
            <div className="dir-title">{c.name}</div>
            <div className="dir-meta">Порядок: {c.sort_order} · Услуг: {c.services_count}</div>
          </div>
          <div className="dir-actions">
            <button className="dir-btn" onClick={() => setEditing(c)}>✏️</button>
            <button
              className="dir-btn danger"
              onClick={() => handleDelete(c.id)}
              title={c.services_count > 0 ? 'Сначала переназначьте услуги' : 'Удалить'}
            >
              🗑
            </button>
          </div>
        </div>
      ))}

      {editing && (
        <ModalForm
          title={editing.id ? 'Редактировать категорию' : 'Новая категория'}
          onClose={() => setEditing(null)}
          onSave={handleSave}
          fields={[
            { key: 'name',       label: 'Название', required: true },
            { key: 'sort_order', label: 'Порядок (меньше — выше)', type: 'number' },
          ]}
          initial={editing}
        />
      )}
    </div>
  );
}


// ---------- Услуги ----------

function ServicesSection({ orgId }) {
  const [services, setServices] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [svcData, catData] = await Promise.all([
        adminApi.getServices(orgId),
        adminApi.getServiceCategories(orgId).catch(() => ({ categories: [] })),
      ]);
      setServices(svcData.services || []);
      setCategories(catData.categories || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [orgId]);

  async function handleSave(form) {
    const isNew = !!form._isNew;
    const payload = {
      name: (form.name || '').trim(),
      category_id: form.category_id || null,
      price: parseInt(form.price || 0, 10),
      duration_min: parseInt(form.duration_min || 30, 10),
      buffer_min: parseInt(form.buffer_min || 0, 10),
      revisit_interval_days: parseInt(form.revisit_interval_days || 0, 10),
      prep: form.prep || '',
      active: form.active ? 1 : 0,
    };
    if (isNew) {
      await adminApi.createService(orgId, payload);
    } else {
      await adminApi.updateService(orgId, form.id, payload);
    }
    setEditing(null);
    await load();
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить услугу?')) return;
    try {
      await adminApi.deleteService(orgId, id);
      await load();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  }

  if (loading) return <div className="loading">Загрузка…</div>;

  const categoryOptions = [
    { value: '', label: '— Без категории —' },
    ...categories.map((c) => ({ value: c.id, label: c.name })),
  ];

  return (
    <div>
      <button
        className="btn-generate"
        style={{ marginBottom: 12 }}
        onClick={() => setEditing({
          _isNew: true, id: '', name: '', price: 0, prep: '',
          duration_min: 30, buffer_min: 0, revisit_interval_days: 0,
          category_id: null, active: true,
        })}
      >
        ➕ Добавить услугу
      </button>

      {!services.length && <p style={{ color: 'var(--text-muted)' }}>Услуг пока нет.</p>}

      {services.map((s) => (
        <div key={s.id} className="dir-item">
          <div className="dir-main">
            <div className="dir-title">
              {s.name} {!s.active && <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>(скрыта)</span>}
            </div>
            <div className="dir-meta">
              {s.price} ₽ · {s.duration_min} мин
              {s.buffer_min > 0 && <span style={{ color: 'var(--text-muted)' }}> · буфер {s.buffer_min} мин</span>}
              {s.revisit_interval_days > 0 && (
                <span style={{ color: 'var(--primary)' }}> · 🔔 повтор через {s.revisit_interval_days} дн.</span>
              )}
              {s.category_name && (
                <span className="service-cat-badge" style={{ marginLeft: 8 }}>
                  {s.category_name}
                </span>
              )}
            </div>
            {s.prep && <div className="dir-meta" style={{ fontSize: 12 }}>{s.prep}</div>}
          </div>
          <div className="dir-actions">
            <button
              className="dir-btn"
              onClick={() => setEditing({ ...s, category_id: s.category_id || null })}
            >
              ✏️
            </button>
            <button className="dir-btn danger" onClick={() => handleDelete(s.id)}>🗑</button>
          </div>
        </div>
      ))}

      {editing && (
        <ModalForm
          title={editing._isNew ? 'Новая услуга' : 'Редактировать услугу'}
          onClose={() => setEditing(null)}
          onSave={handleSave}
          fields={[
            { key: 'name',         label: 'Название', required: true },
            {
              key: 'category_id',
              label: 'Категория',
              type: 'select',
              options: categoryOptions,
              nullable: true,
            },
            { key: 'price',        label: 'Цена, ₽', type: 'number' },
            { key: 'duration_min', label: 'Длительность, мин', type: 'number' },
            { key: 'buffer_min',   label: 'Буфер после приёма, мин', type: 'number',
              hint: 'Время на уборку/подготовку после процедуры.' },
            { key: 'revisit_interval_days', label: 'Напомнить о повторе через, дней',
              type: 'number',
              hint: '0 — не напоминать. Например, 30 для стрижки, 21 для маникюра. Работает, если в «📣 Рассылки → Автоматические» создан сценарий «Повторный визит по циклу».' },
            { key: 'prep',         label: 'Подготовка (что взять, как готовиться)' },
            { key: 'active',       label: 'Показывать в Mini App', type: 'checkbox' },
          ]}
          initial={editing}
        />
      )}
    </div>
  );
}


// ---------- Универсальная модалка ----------

function ModalForm({ title, onClose, onSave, fields, initial }) {
  const [form, setForm] = useState(() => {
    const f = { ...initial };
    for (const fld of fields) {
      if (f[fld.key] === undefined) {
        if (fld.type === 'checkbox') f[fld.key] = true;
        else if (fld.type === 'number') f[fld.key] = 0;
        else f[fld.key] = '';
      }
    }
    return f;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function setSelectField(key, rawValue, nullable) {
    if (nullable && rawValue === '') {
      setField(key, null);
      return;
    }
    setField(key, parseInt(rawValue, 10));
  }

  async function handleSubmit() {
    for (const fld of fields) {
      if (fld.required && !form[fld.key] && form[fld.key] !== 0) {
        setError(`Заполните: ${fld.label}`);
        return;
      }
    }
    setError('');
    setBusy(true);
    try {
      await onSave(form);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="card-title">{title}</h2>

        {fields.map((fld) => (
          <div key={fld.key} className="form-group">
            <label className="form-label">{fld.label}</label>
            {fld.type === 'select' ? (
              <select
                className="form-input"
                value={form[fld.key] ?? ''}
                onChange={(e) => setSelectField(fld.key, e.target.value, fld.nullable)}
                disabled={busy}
              >
                {fld.options.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : fld.type === 'checkbox' ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={!!form[fld.key]}
                  onChange={(e) => setField(fld.key, e.target.checked)}
                  disabled={busy}
                />
                <span>{form[fld.key] ? 'Да' : 'Нет'}</span>
              </label>
            ) : (
              <input
                className="form-input"
                type={fld.type || 'text'}
                value={form[fld.key] ?? ''}
                onChange={(e) => setField(
                  fld.key,
                  fld.type === 'number' ? parseInt(e.target.value || '0', 10) : e.target.value
                )}
                placeholder={fld.placeholder || ''}
                disabled={busy || fld.disabled}
              />
            )}
            {fld.hint && (
              <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
                {fld.hint}
              </div>
            )}
          </div>
        ))}

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={handleSubmit} disabled={busy}>
            {busy ? 'Сохранение…' : '✅ Сохранить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}