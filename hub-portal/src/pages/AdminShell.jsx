import React, { useEffect, useState } from 'react';
import api from '../api.ts';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, Layers, FileText, Users, DollarSign, History, BarChart3,
  Search, Bell, LogOut, ChevronRight,
  Workflow, Server, Package, GitBranch, Plus,
} from 'lucide-react';
import { tokens } from '../tokens.js';
import { ErajayaMark } from '../components/ui.jsx';
import { DashboardPage } from './admin/DashboardPage.jsx';
import { TenantsPage } from './admin/TenantsPage.jsx';
import { MonitoringPage } from './admin/MonitoringPage.jsx';
import { AuditPage } from './admin/AuditPage.jsx';
import { DocumentsPage } from './admin/DocumentsPage.jsx';
import { UsersPage } from './admin/UsersPage.jsx';
import { CostsPage } from './admin/CostsPage.jsx';
import OnboardingPipelinePage from './admin/OnboardingPipelinePage.tsx';
import JourneyWorkspacePage from './admin/JourneyWorkspacePage.tsx';
import VpsConsolePage from './admin/VpsConsolePage.tsx';
import ModuleDeployPage from './admin/ModuleDeployPage.tsx';
import DevCyclePage from './admin/DevCyclePage.tsx';
import IntakeWizard from '../components/IntakeWizard.tsx';

const adminNav = [
  { id: 'dashboard',  label: 'Dashboard',          icon: BarChart3 },
  { id: 'onboarding', label: 'Onboarding Pipeline', icon: Workflow },
  { id: 'tenants',    label: 'Tenants & Verticals', icon: Layers },
  { id: 'vps',        label: 'VPS Console',        icon: Server },
  { id: 'modules',    label: 'Module Deployments', icon: Package },
  { id: 'devcycle',   label: 'Dev Cycles',         icon: GitBranch },
  { id: 'monitoring', label: 'Services Monitoring', icon: Activity },
  { id: 'audit',      label: 'Audit Trail',        icon: History },
  { id: 'documents',  label: 'Documents',          icon: FileText },
  { id: 'users',      label: 'Users & RBAC',       icon: Users },
  { id: 'costs',      label: 'Cost & Licenses',    icon: DollarSign },
];

export function AdminShell({ onLogout }) {
  const [active, setActive] = useState('dashboard');
  const [activeJourneyId, setActiveJourneyId] = useState(null);
  const [showIntake, setShowIntake] = useState(false);
  const [me, setMe] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.auth
      .me()
      .then((u) => { if (!cancelled) setMe(u); })
      .catch(() => { /* not logged in; parent handles redirect */ });
    return () => { cancelled = true; };
  }, []);

  const handleLogout = async () => {
    try { await api.auth.logout(); } catch { /* ignore */ }
    if (typeof onLogout === 'function') onLogout();
  };

  const displayName = me?.name || 'Loading...';
  const initials = (me?.name || '?')
    .split(' ')
    .map((n) => n[0])
    .filter(Boolean)
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const openJourney = (id) => {
    setActiveJourneyId(id);
    setActive('journey');
  };

  return (
    <div style={{
      minHeight: '100vh', background: tokens.surfaceAlt,
      fontFamily: "'Inter', sans-serif", color: tokens.ink,
      display: 'flex',
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-thumb { background: ${tokens.border}; border-radius: 4px; }
      `}</style>

      <aside style={{
        width: 240, background: tokens.ink, color: '#fff',
        display: 'flex', flexDirection: 'column',
        position: 'sticky', top: 0, height: '100vh',
      }}>
        <div style={{ padding: '24px 20px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: `1px solid ${tokens.borderDark}` }}>
          <ErajayaMark size={32} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>Erajaya</div>
            <div style={{ fontSize: 10, color: tokens.muted, letterSpacing: 1, textTransform: 'uppercase' }}>Odoo Hub</div>
          </div>
        </div>

        <nav style={{ flex: 1, padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {adminNav.map(item => {
            const Icon = item.icon;
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActive(item.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 12px', borderRadius: 7,
                  background: isActive ? tokens.brand : 'transparent',
                  color: isActive ? '#fff' : '#d4d4d8',
                  border: 'none', cursor: 'pointer',
                  fontSize: 13, fontWeight: isActive ? 600 : 500,
                  fontFamily: 'inherit', textAlign: 'left',
                  transition: 'all 0.15s',
                }}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div style={{ padding: 16, borderTop: `1px solid ${tokens.borderDark}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: `linear-gradient(135deg, ${tokens.brand}, ${tokens.accent})`,
              color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700,
            }}>{initials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayName}</div>
              <div style={{ fontSize: 10, color: tokens.muted }}>{me?.login || 'Platform Admin'}</div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              width: '100%', background: 'transparent',
              color: tokens.muted, border: `1px solid ${tokens.borderDark}`,
              padding: '8px', borderRadius: 6, cursor: 'pointer',
              fontSize: 11, fontWeight: 500, fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            <LogOut size={12} /> Sign out
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, overflow: 'auto' }}>
        <header style={{
          background: '#fff', borderBottom: `1px solid ${tokens.border}`,
          padding: '14px 32px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'sticky', top: 0, zIndex: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: tokens.muted }}>
            <span>Console</span>
            <ChevronRight size={12} />
            <span style={{ color: tokens.ink, fontWeight: 600 }}>
              {adminNav.find(n => n.id === active)?.label}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              onClick={() => setShowIntake(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: tokens.brand, color: '#fff',
                border: 'none', padding: '8px 14px', borderRadius: 8,
                fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              <Plus size={14} /> New Intake
            </button>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: tokens.surfaceAlt, padding: '8px 12px',
              borderRadius: 8, width: 280,
            }}>
              <Search size={14} color={tokens.muted} />
              <input
                placeholder="Search tenants, users, documents..."
                style={{
                  background: 'transparent', border: 'none', outline: 'none',
                  fontSize: 13, width: '100%', fontFamily: 'inherit',
                }}
              />
              <kbd style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                background: '#fff', border: `1px solid ${tokens.border}`,
                color: tokens.muted, fontFamily: 'JetBrains Mono, monospace',
              }}>⌘K</kbd>
            </div>
            <button style={{
              width: 36, height: 36, borderRadius: 8,
              background: tokens.surfaceAlt, border: 'none',
              cursor: 'pointer', position: 'relative',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Bell size={16} color={tokens.ink} />
              <span style={{
                position: 'absolute', top: 6, right: 6,
                width: 8, height: 8, borderRadius: '50%',
                background: tokens.brand, border: '2px solid #fff',
              }} />
            </button>
          </div>
        </header>

        <div style={{ padding: 32 }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {active === 'dashboard'  && <DashboardPage />}
              {active === 'onboarding' && <OnboardingPipelinePage onOpenJourney={openJourney} onNewIntake={() => setShowIntake(true)} />}
              {active === 'journey'    && <JourneyWorkspacePage journeyId={activeJourneyId} onBack={() => setActive('onboarding')} />}
              {active === 'tenants'    && <TenantsPage />}
              {active === 'vps'        && <VpsConsolePage />}
              {active === 'modules'    && <ModuleDeployPage />}
              {active === 'devcycle'   && <DevCyclePage />}
              {active === 'monitoring' && <MonitoringPage />}
              {active === 'audit'      && <AuditPage />}
              {active === 'documents'  && <DocumentsPage />}
              {active === 'users'      && <UsersPage />}
              {active === 'costs'      && <CostsPage />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      <IntakeWizard open={showIntake} onClose={() => setShowIntake(false)} />

    </div>
  );
}
