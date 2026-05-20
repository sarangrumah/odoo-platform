import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LandingPage } from './pages/Landing.jsx';
import { Login } from './pages/Login.jsx';
import { AdminShell } from './pages/AdminShell.jsx';
import api from './api.ts';

export function App() {
  // 'landing' (public) -> 'login' -> 'app' (authenticated)
  const [view, setView] = useState('landing');
  const [bootDone, setBootDone] = useState(false);

  // On mount: probe /api/auth/me. A returning user with a valid Odoo
  // session cookie can jump straight to the app. Anonymous visitors stay
  // on the public landing page.
  useEffect(() => {
    let cancelled = false;
    api.auth
      .me()
      .then((u) => {
        if (!cancelled && u && u.uid) setView('app');
      })
      .catch(() => {
        /* 401 -> stay on landing (public) */
      })
      .finally(() => {
        if (!cancelled) setBootDone(true);
      });
    return () => { cancelled = true; };
  }, []);

  const handleLogout = async () => {
    try { await api.auth.logout(); } catch { /* ignore */ }
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

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={view}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      >
        {view === 'landing' && <LandingPage onEnterApp={() => setView('login')} />}
        {view === 'login'   && <Login onLogin={() => setView('app')} onBack={() => setView('landing')} />}
        {view === 'app'     && <AdminShell onLogout={handleLogout} />}
      </motion.div>
    </AnimatePresence>
  );
}
