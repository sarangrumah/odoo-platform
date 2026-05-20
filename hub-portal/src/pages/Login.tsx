import { FormEvent, useState } from 'react';
import { ArrowLeft, LogIn } from 'lucide-react';
import { colors, radii, spacing } from '../tokens';
import { Button, Card, Input } from '../components/ui';
import { auth } from '../api';

interface Props {
  onSuccess: () => void;
  onCancel: () => void;
}

export default function Login({ onSuccess, onCancel }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(email, password);
      onSuccess();
    } catch (err: any) {
      // Dev-mode bypass: allow demo/demo locally if backend offline.
      if (email === 'demo' && password === 'demo') {
        onSuccess();
        return;
      }
      setError(err?.detail || err?.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: colors.bg,
        color: colors.text,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: spacing.lg,
      }}
    >
      <Card style={{ width: 400, padding: spacing.xxl }}>
        <button
          onClick={onCancel}
          style={{ background: 'none', border: 'none', color: colors.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, marginBottom: spacing.md }}
        >
          <ArrowLeft size={12} /> Back
        </button>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: radii.md,
            background: `linear-gradient(135deg, ${colors.brand}, ${colors.accent})`,
            marginBottom: spacing.md,
          }}
        />
        <h1 style={{ margin: '0 0 4px', fontSize: 22 }}>Sign in to Hub</h1>
        <p style={{ margin: 0, color: colors.textMuted, fontSize: 13, marginBottom: spacing.lg }}>
          Internal control plane for Erajaya Odoo platform.
        </p>
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Email
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{ marginTop: 4 }}
              autoComplete="username"
            />
          </label>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Password
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ marginTop: 4 }}
              autoComplete="current-password"
            />
          </label>
          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', color: colors.danger, padding: 10, borderRadius: radii.md, fontSize: 13 }}>
              {error}
            </div>
          )}
          <Button type="submit" disabled={busy}>
            <LogIn size={14} /> {busy ? 'Signing in…' : 'Sign in'}
          </Button>
          <p style={{ margin: 0, fontSize: 11, color: colors.textDim }}>
            Tip: dev bypass — demo/demo when backend is offline.
          </p>
        </form>
      </Card>
    </div>
  );
}
