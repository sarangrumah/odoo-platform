import React, { useState } from 'react';
import api from '../api.ts';

export function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Email and password required');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await api.auth.login(email, password);
      if (res && res.ok) {
        onLogin && onLogin();
      } else {
        setError('Unexpected response from auth gateway');
      }
    } catch (err) {
      if (err && err.status === 401) {
        setError('Invalid credentials');
      } else {
        setError(err?.detail || err?.message || 'Login failed');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: '#0b1220', color: '#e6edf7',
      fontFamily: 'Inter, sans-serif',
    }}>
      <form
        onSubmit={handleSubmit}
        style={{
          width: 360, padding: 32, borderRadius: 12,
          background: '#111a2e', border: '1px solid #1f2a44',
          display: 'flex', flexDirection: 'column', gap: 16,
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Odoo Hub Portal</div>
          <div style={{ fontSize: 12, color: '#8b96b0' }}>Sign in with your Odoo account</div>
        </div>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
          <span style={{ color: '#a7b1c8' }}>Email</span>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            style={{
              padding: '10px 12px', borderRadius: 6,
              border: '1px solid #1f2a44', background: '#0b1220',
              color: '#e6edf7', fontSize: 13, fontFamily: 'inherit', outline: 'none',
            }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
          <span style={{ color: '#a7b1c8' }}>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            style={{
              padding: '10px 12px', borderRadius: 6,
              border: '1px solid #1f2a44', background: '#0b1220',
              color: '#e6edf7', fontSize: 13, fontFamily: 'inherit', outline: 'none',
            }}
          />
        </label>

        {error && (
          <div style={{
            fontSize: 12, color: '#ff6b6b',
            background: 'rgba(255,107,107,0.08)',
            border: '1px solid rgba(255,107,107,0.3)',
            padding: '8px 10px', borderRadius: 6,
          }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '10px 14px', borderRadius: 6,
            background: loading ? '#374a73' : '#3b6ef5',
            color: '#fff', border: 'none', cursor: loading ? 'wait' : 'pointer',
            fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
          }}
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>

        <div style={{ fontSize: 11, color: '#6b7794', textAlign: 'center' }}>
          Default dev: admin / admin
        </div>
      </form>
    </div>
  );
}

export default Login;
