import { useState } from 'react';
import Landing from './pages/Landing';
import Login from './pages/Login';
import AdminShell from './pages/AdminShell';

type View = 'landing' | 'login' | 'app';

export default function App() {
  const [view, setView] = useState<View>('landing');
  if (view === 'landing') return <Landing onLogin={() => setView('login')} />;
  if (view === 'login') return <Login onSuccess={() => setView('app')} onCancel={() => setView('landing')} />;
  return <AdminShell onLogout={() => setView('landing')} />;
}
