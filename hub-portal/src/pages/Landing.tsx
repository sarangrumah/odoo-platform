import { LogIn, Sparkles, ShieldCheck, GitBranch, Server } from 'lucide-react';
import { colors, radii, spacing } from '../tokens';
import { Button, Card } from '../components/ui';

interface Props {
  onLogin: () => void;
}

const FEATURES = [
  { icon: Server, title: 'Multi-tenant orchestrator', desc: 'Tenant-per-DB, automated provisioning + backups.' },
  { icon: GitBranch, title: 'EE-gap fulfillment', desc: 'Custom modules close every CE→EE delta we need.' },
  { icon: ShieldCheck, title: 'Compliance first', desc: 'PDP, Coretax, Bupot Unifikasi, audit trail.' },
  { icon: Sparkles, title: 'AI assist', desc: 'BRD analyzer, recommendation engine, cross-vertical insight.' },
];

export default function Landing({ onLogin }: Props) {
  return (
    <div style={{ minHeight: '100vh', background: colors.bg, color: colors.text }}>
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '20px 48px',
          borderBottom: `1px solid ${colors.border}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontWeight: 700 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: radii.md,
              background: `linear-gradient(135deg, ${colors.brand}, ${colors.accent})`,
            }}
          />
          Odoo Hub Platform
        </div>
        <Button variant="secondary" onClick={onLogin}>
          <LogIn size={14} /> Sign in
        </Button>
      </header>

      <section style={{ padding: '96px 48px', maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ fontSize: 14, color: colors.accent, fontWeight: 600, letterSpacing: 1.5, textTransform: 'uppercase' }}>
          Erajaya Group · Internal Control Plane
        </div>
        <h1 style={{ fontSize: 56, lineHeight: 1.05, margin: '16px 0 24px', maxWidth: 820 }}>
          One hub for every tenant, every vertical, every release.
        </h1>
        <p style={{ fontSize: 18, color: colors.textMuted, maxWidth: 720, marginBottom: 32 }}>
          Onboard new properties in days, not months. The hub-portal coordinates intake, BRD analysis,
          VPS provisioning, module deployment, and post go-live ops in one workspace.
        </p>
        <Button size="lg" onClick={onLogin}>
          Open dashboard
        </Button>
      </section>

      <section
        style={{
          padding: '48px 48px 96px',
          maxWidth: 1100,
          margin: '0 auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: spacing.lg,
        }}
      >
        {FEATURES.map((f) => (
          <Card key={f.title}>
            <f.icon size={22} color={colors.accent} />
            <h3 style={{ margin: '12px 0 6px', fontSize: 16 }}>{f.title}</h3>
            <p style={{ margin: 0, color: colors.textMuted, fontSize: 13 }}>{f.desc}</p>
          </Card>
        ))}
      </section>

      <footer
        style={{
          padding: '24px 48px',
          borderTop: `1px solid ${colors.border}`,
          color: colors.textDim,
          fontSize: 12,
        }}
      >
        Internal use only. Multi-tenant production scope: DB-per-tenant, Pajakku ASPP, 99.5% SLA.
      </footer>
    </div>
  );
}
