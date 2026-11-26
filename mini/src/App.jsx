import { useEffect, useState } from 'react';
import ClientApp from './ClientApp.jsx';
import AdminApp from './admin/AdminApp.jsx';
import WaitlistPage from './components/WaitlistPage.jsx';

function getStartParam() {
  if (window.WebApp && window.WebApp.initDataUnsafe && window.WebApp.initDataUnsafe.start_param) {
    return window.WebApp.initDataUnsafe.start_param;
  }
  const params = new URLSearchParams(window.location.search);
  return params.get('startapp') || '';
}

export default function App() {
  const [mode, setMode] = useState(null);
  const [orgId, setOrgId] = useState(null);
  const [repeatRequestId, setRepeatRequestId] = useState(null);
  const [preselectedSlotId, setPreselectedSlotId] = useState(null);

  useEffect(() => {
    const sp = getStartParam();
    if (sp.startsWith('admin_')) {
      const id = sp.replace('admin_', '');
      setOrgId(id);
      setMode('admin');
    } else if (sp.startsWith('repeat_')) {
      const rid = parseInt(sp.replace('repeat_', ''), 10);
      if (Number.isFinite(rid)) setRepeatRequestId(rid);
      setMode('client');
    } else if (sp.startsWith('slot_')) {
      const sid = parseInt(sp.replace('slot_', ''), 10);
      if (Number.isFinite(sid)) setPreselectedSlotId(sid);
      setMode('client');
    } else if (sp === 'waitlist') {
      setMode('waitlist');
    } else {
      setMode('client');
    }
  }, []);

  if (mode === null) {
    return (
      <div className="app">
        <div className="loading">Загрузка…</div>
      </div>
    );
  }

  if (mode === 'admin') {
    return <AdminApp orgId={orgId} />;
  }

  if (mode === 'waitlist') {
    return <WaitlistPage />;
  }

  return (
    <ClientApp
      repeatRequestId={repeatRequestId}
      preselectedSlotId={preselectedSlotId}
    />
  );
}