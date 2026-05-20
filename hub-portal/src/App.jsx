import React, { useEffect, useState } from 'react';
import { AdminShell } from './pages/AdminShell.jsx';
import { Login } from './pages/Login.jsx';
import api from './api.ts';

export function App() {
  // 'landing' = login screen, 'app' = authenticated shell.
  const [view, setView] = useState('landing');
  const [bootDone, setBootDone] = useState(false);

  // On mount, probe /api/auth/me so a returning user with a valid Odoo
  // session cookie skips the login form.
  useEffect(() => {
    let cancelled = false;
    api.auth
      .me()
      .then((u) => {
        if (!cancelled && u && u.uid) setView('app');
      })
      .catch(() => {
        /* 401 -> stay on landing */
      })
      .finally(() => {
        if (!cancelled) setBootDone(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      /* ignore */
    }
    setView('landing');
  };

  if (!bootDone) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: '#0b1220', color: '#e6edf7',
        fontFamily: 'Inter, sans-serif', fontSize: 13,
      }}>
        Loading...
      </div>
    );
  }

  if (view === 'app') {
    return <AdminShell onLogout={handleLogout} />;
  }
  return <Login onLogin={() => setView('app')} />;
}
