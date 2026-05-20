import { useState, ComponentType } from 'react';
import {
  LayoutDashboard,
  Building2,
  Users,
  Activity,
  DollarSign,
  ShieldAlert,
  FileText,
  Workflow,
  FolderKanban,
  Server,
  Package,
  Code2,
  LogOut,
  Plus,
} from 'lucide-react';

import { colors, radii, spacing } from '../tokens';
import { Button } from '../components/ui';

import DashboardPage from './admin/DashboardPage';
import TenantsPage from './admin/TenantsPage';
import UsersPage from './admin/UsersPage';
import MonitoringPage from './admin/MonitoringPage';
import CostsPage from './admin/CostsPage';
import AuditPage from './admin/AuditPage';
import DocumentsPage from './admin/DocumentsPage';
import OnboardingPipelinePage from './admin/OnboardingPipelinePage';
import JourneyWorkspacePage from './admin/JourneyWorkspacePage';
import VpsConsolePage from './admin/VpsConsolePage';
import ModuleDeployPage from './admin/ModuleDeployPage';
import DevCyclePage from './admin/DevCyclePage';
import IntakeWizard from '../components/IntakeWizard';

type NavKey =
  | 'dashboard'
  | 'pipeline'
  | 'tenants'
  | 'vps'
  | 'modules'
  | 'devcycles'
  | 'users'
  | 'monitoring'
  | 'costs'
  | 'audit'
  | 'documents';

interface NavItem {
  key: NavKey;
  label: string;
  icon: ComponentType<{ size?: number }>;
  group: 'ops' | 'plat' | 'admin';
}

const NAV: NavItem[] = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, group: 'ops' },
  { key: 'pipeline', label: 'Onboarding Pipeline', icon: Workflow, group: 'ops' },
  { key: 'tenants', label: 'Tenants', icon: Building2, group: 'ops' },
  { key: 'vps', label: 'VPS Console', icon: Server, group: 'plat' },
  { key: 'modules', label: 'Module Deploy', icon: Package, group: 'plat' },
  { key: 'devcycles', label: 'Dev Cycles', icon: Code2, group: 'plat' },
  { key: 'users', label: 'Users', icon: Users, group: 'admin' },
  { key: 'monitoring', label: 'Monitoring', icon: Activity, group: 'admin' },
  { key: 'costs', label: 'Costs', icon: DollarSign, group: 'admin' },
  { key: 'audit', label: 'Audit', icon: ShieldAlert, group: 'admin' },
  { key: 'documents', label: 'Documents', icon: FileText, group: 'admin' },
];

const GROUP_LABEL: Record<NavItem['group'], string> = {
  ops: 'Operations',
  plat: 'Platform',
  admin: 'Administration',
};

interface Props {
  onLogout: () => void;
}

export default function AdminShell({ onLogout }: Props) {
  const [active, setActive] = useState<NavKey>('dashboard');
  const [journeyId, setJourneyId] = useState<number | null>(null);
  const [intakeOpen, setIntakeOpen] = useState(false);

  function openJourney(id: number) {
    setJourneyId(id);
  }

  function backToPipeline() {
    setJourneyId(null);
  }

  function renderActive() {
    if (active === 'pipeline' && journeyId)
      return <JourneyWorkspacePage journeyId={journeyId} onBack={backToPipeline} />;
    switch (active) {
      case 'dashboard':
        return <DashboardPage />;
      case 'pipeline':
        return (
          <OnboardingPipelinePage
            onOpenJourney={openJourney}
            onNewIntake={() => setIntakeOpen(true)}
          />
        );
      case 'tenants':
        return <TenantsPage />;
      case 'vps':
        return <VpsConsolePage />;
      case 'modules':
        return <ModuleDeployPage />;
      case 'devcycles':
        return <DevCyclePage />;
      case 'users':
        return <UsersPage />;
      case 'monitoring':
        return <MonitoringPage />;
      case 'costs':
        return <CostsPage />;
      case 'audit':
        return <AuditPage />;
      case 'documents':
        return <DocumentsPage />;
      default:
        return null;
    }
  }

  const groups: NavItem['group'][] = ['ops', 'plat', 'admin'];

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: colors.bg, color: colors.text }}>
      <aside
        style={{
          width: 240,
          background: colors.surface,
          borderRight: `1px solid ${colors.border}`,
          padding: spacing.lg,
          display: 'flex',
          flexDirection: 'column',
          gap: spacing.md,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700, fontSize: 15 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: radii.md,
              background: `linear-gradient(135deg, ${colors.brand}, ${colors.accent})`,
            }}
          />
          Hub Portal
        </div>

        {groups.map((g) => (
          <div key={g} style={{ marginTop: spacing.md }}>
            <div
              style={{
                fontSize: 10,
                color: colors.textDim,
                textTransform: 'uppercase',
                letterSpacing: 1,
                marginBottom: 6,
                paddingLeft: 4,
              }}
            >
              {GROUP_LABEL[g]}
            </div>
            {NAV.filter((n) => n.group === g).map((item) => {
              const Icon = item.icon;
              const isActive = active === item.key;
              return (
                <button
                  key={item.key}
                  onClick={() => {
                    setActive(item.key);
                    setJourneyId(null);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    width: '100%',
                    background: isActive ? colors.surfaceMuted : 'transparent',
                    color: isActive ? colors.text : colors.textMuted,
                    border: 'none',
                    padding: '8px 10px',
                    borderRadius: radii.md,
                    cursor: 'pointer',
                    fontSize: 13,
                    textAlign: 'left',
                    fontWeight: 500,
                    marginBottom: 2,
                  }}
                >
                  <Icon size={15} />
                  {item.label}
                </button>
              );
            })}
          </div>
        ))}

        <div style={{ marginTop: 'auto' }}>
          <Button variant="ghost" onClick={onLogout} style={{ width: '100%', justifyContent: 'center' }}>
            <LogOut size={14} /> Sign out
          </Button>
        </div>
      </aside>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: `${spacing.md}px ${spacing.xl}px`,
            borderBottom: `1px solid ${colors.border}`,
            background: colors.surface,
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 14, color: colors.textMuted }}>
            {NAV.find((n) => n.key === active)?.label}
            {active === 'pipeline' && journeyId && ` › Journey #${journeyId}`}
          </div>
          <div style={{ display: 'flex', gap: spacing.sm }}>
            <Button onClick={() => setIntakeOpen(true)}>
              <Plus size={14} /> New Onboarding Intake
            </Button>
          </div>
        </header>

        <div style={{ flex: 1, overflow: 'auto', padding: spacing.xl }}>{renderActive()}</div>
      </main>

      <IntakeWizard
        open={intakeOpen}
        onClose={() => setIntakeOpen(false)}
        onSuccess={(token) => {
          // Optional: jump straight to pipeline after success.
          setActive('pipeline');
          setIntakeOpen(false);
          // eslint-disable-next-line no-console
          console.info('Intake submitted, token:', token);
        }}
      />
    </div>
  );
}
