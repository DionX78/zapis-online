import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';
import SettingsPage from './SettingsPage.jsx';
import SchedulePage from './SchedulePage.jsx';
import DirectoriesPage from './DirectoriesPage.jsx';
import RequestsPage from './RequestsPage.jsx';
import BroadcastsPage from './BroadcastsPage.jsx';
import DashboardPage from './DashboardPage.jsx';
import AuditLogPage from './AuditLogPage.jsx';
import BlockedUsersPage from './BlockedUsersPage.jsx';
import ClientsPage from './ClientsPage.jsx';
import WaitlistPage from './WaitlistPage.jsx';
import AnalyticsPage from './AnalyticsPage.jsx';
import ReviewsPage from './ReviewsPage.jsx';
import ChannelsPage from './ChannelsPage.jsx';

const LS_ORG_KEY = 'max_booking_admin_org_id';

const MENU_ITEMS = [
  { id: 'analytics',   label: '📊 Аналитика' },
  { id: 'reviews',     label: '⭐ Отзывы' },
  { id: 'clients',     label: '👥 Клиенты' },
  { id: 'waitlist',    label: '⏳ Лист ожидания' },
  { id: 'audit',       label: '📜 Журнал' },
  { id: 'blocked',     label: '🚫 Заблокированные' },
  { id: 'broadcasts',  label: '📣 Рассылки' },
  { id: 'directories', label: '🏢 Справочники' },
  { id: 'channels',    label: '🤖 Каналы' },
  { id: 'settings',    label: '⚙️ Настройки' },
];

export default function AdminApp({ orgId }) {
  const [tab, setTab] = useState('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [me, setMe] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [currentOrgId, setCurrentOrgId] = useState(orgId || null);
  const [requestsPreset, setRequestsPreset] = useState(null);

  async function loadMe(currentOrg) {
    try {
      const meData = await adminApi.getMe(currentOrg);
      setMe(meData);

      if (meData.role === 'superadmin') {
        const orgsData = await adminApi.getOrgs();
        setOrgs(orgsData.orgs || []);
        if (!currentOrg && orgsData.orgs && orgsData.orgs.length) {
          const saved = localStorage.getItem(LS_ORG_KEY);
          const fromSaved = saved && orgsData.orgs.find((o) => String(o.id) === saved);
          const pick = fromSaved ? fromSaved.id : orgsData.orgs[0].id;
          setCurrentOrgId(pick);
          localStorage.setItem(LS_ORG_KEY, String(pick));
          return;
        }
      }
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  useEffect(() => {
    loadMe(currentOrgId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentOrgId]);

  function handleOrgChange(e) {
    const id = parseInt(e.target.value, 10);
    setCurrentOrgId(id);
    localStorage.setItem(LS_ORG_KEY, String(id));
  }

  function openTab(id) {
    if (id === 'requests') setRequestsPreset(null);
    setTab(id);
    setMenuOpen(false);
  }

  function handleDashboardOpen(status, datePreset) {
    setRequestsPreset({ status, datePreset });
    setTab('requests');
    setMenuOpen(false);
  }

  if (step === 'loading') {
    return (
      <div className="app">
        <div className="loading">Загрузка админки…</div>
      </div>
    );
  }

  if (step === 'error') {
    return (
      <div className="app">
        <div className="error-box">
          <strong>Ошибка доступа:</strong> {error}
          <p style={{ marginTop: 8, fontSize: 14 }}>
            Откройте админку через бота (кнопка «⚙️ Админ»).
          </p>
        </div>
      </div>
    );
  }

  const isSuper = me.role === 'superadmin';
  const roleLabel = isSuper ? 'Суперадмин' : 'Админ';
  const isExtraTab = MENU_ITEMS.some((m) => m.id === tab);

  const requestsKey = requestsPreset
    ? `requests-${requestsPreset.status}-${requestsPreset.datePreset}`
    : 'requests-default';

  return (
    <div className="app">
      <div className="header">
        <h1>Админка</h1>
        {isSuper && orgs.length > 0 ? (
          <select
            className="org-select"
            value={currentOrgId || ''}
            onChange={handleOrgChange}
          >
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
        ) : (
          <p>{me.org_name || '—'}</p>
        )}
        <p className="role-line">{roleLabel}</p>
      </div>

      <div className="main-tabs">
        <button
          className={'main-tab' + (tab === 'dashboard' ? ' active' : '')}
          onClick={() => openTab('dashboard')}
        >
          🏠 Сегодня
        </button>
        <button
          className={'main-tab' + (tab === 'requests' ? ' active' : '')}
          onClick={() => openTab('requests')}
        >
          📋 Заявки
        </button>
        <button
          className={'main-tab' + (tab === 'schedule' ? ' active' : '')}
          onClick={() => openTab('schedule')}
        >
          📅 Расписание
        </button>
        <button
          className={'main-tab hamburger' + (isExtraTab ? ' active' : '')}
          onClick={() => setMenuOpen(true)}
        >
          ☰
        </button>
      </div>

      {menuOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setMenuOpen(false)} />
          <div className="drawer">
            <div className="drawer-header">
              <span>Меню</span>
              <button className="drawer-close" onClick={() => setMenuOpen(false)}>✕</button>
            </div>
            {MENU_ITEMS.map((item) => (
              <button
                key={item.id}
                className={'drawer-item' + (tab === item.id ? ' active' : '')}
                onClick={() => openTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}

      {tab === 'dashboard' && (
        <div className="card">
          <DashboardPage
            orgId={currentOrgId}
            onOpenRequests={handleDashboardOpen}
          />
        </div>
      )}

      {tab === 'requests' && (
        <div className="card">
          <RequestsPage
            key={requestsKey}
            orgId={currentOrgId}
            initialStatus={requestsPreset?.status || 'all'}
            initialDatePreset={requestsPreset?.datePreset || '7'}
          />
        </div>
      )}

      {tab === 'schedule' && (
        <div className="card">
          <SchedulePage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'broadcasts' && (
        <div className="card">
          <BroadcastsPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'directories' && (
        <div className="card">
          <DirectoriesPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'audit' && (
        <div className="card">
          <AuditLogPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'analytics' && (
        <div className="card">
          <AnalyticsPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'reviews' && (
        <div className="card">
          <ReviewsPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'clients' && (
        <div className="card">
          <ClientsPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'waitlist' && (
        <div className="card">
          <WaitlistPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'blocked' && (
        <div className="card">
          <BlockedUsersPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'channels' && (
        <div className="card">
          <ChannelsPage orgId={currentOrgId} />
        </div>
      )}

      {tab === 'settings' && (
        <SettingsPage
          orgId={currentOrgId}
          onOrgRenamed={() => loadMe(currentOrgId)}
        />
      )}
    </div>
  );
}