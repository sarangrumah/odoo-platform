import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, Shield, Database, Layers, FileText, Users, DollarSign, BarChart3,
  Search, Bell, Settings, LogOut, ChevronRight, CheckCircle2, AlertCircle,
  Clock, TrendingUp, Server, Lock, Eye, ArrowUpRight, Menu, X, Globe,
  Sparkles, Zap, GitBranch, ShieldCheck, KeyRound, History, FileSearch,
  Building2, ArrowRight, Plus, Filter, Download, MoreVertical, Check
} from 'lucide-react';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';

// ============================================================================
// DESIGN TOKENS — Erajaya brand palette
// ============================================================================
const tokens = {
  // Brand
  brand: '#E30613',           // Erajaya red
  brandDeep: '#B8050F',
  brandSoft: '#FEE2E4',
  // Neutrals — warm dark slate
  ink: '#0A0A0B',
  inkSoft: '#18181B',
  surface: '#FAFAF9',
  surfaceAlt: '#F4F4F2',
  border: '#E7E5E2',
  borderDark: '#27272A',
  muted: '#71717A',
  // Semantic
  ok: '#10B981',
  warn: '#F59E0B',
  err: '#EF4444',
  info: '#3B82F6',
};

// ============================================================================
// MOCK DATA
// ============================================================================
const verticals = [
  { id: 'fnb', name: 'F&B Erajaya', tagline: 'Restaurant & café operations', tenants: 12, icon: '🍽️', color: '#E30613' },
  { id: 'active', name: 'Active Lifestyle', tagline: 'Sports & fitness retail', tenants: 8, icon: '🏃', color: '#F59E0B' },
  { id: 'retail', name: 'Erajaya Retail', tagline: 'Eraspace & device retail', tenants: 24, icon: '📱', color: '#3B82F6' },
  { id: 'distrib', name: 'Distribution', tagline: 'Wholesale & logistics', tenants: 6, icon: '🚚', color: '#10B981' },
  { id: 'service', name: 'Service Center', tagline: 'After-sales & repair', tenants: 9, icon: '🔧', color: '#8B5CF6' },
  { id: 'corp', name: 'Corporate Services', tagline: 'Shared services & VAS', tenants: 4, icon: '🏢', color: '#EC4899' },
];

const services = [
  { name: 'odoo-fnb-prod', vertical: 'F&B', status: 'healthy', uptime: 99.98, latency: 142, version: '18.0' },
  { name: 'odoo-active-prod', vertical: 'Active Lifestyle', status: 'healthy', uptime: 99.95, latency: 168, version: '18.0' },
  { name: 'odoo-eraspace-prod', vertical: 'Retail', status: 'degraded', uptime: 99.42, latency: 412, version: '17.0' },
  { name: 'odoo-distrib-prod', vertical: 'Distribution', status: 'healthy', uptime: 99.99, latency: 98, version: '18.0' },
  { name: 'odoo-service-prod', vertical: 'Service', status: 'healthy', uptime: 99.91, latency: 187, version: '18.0' },
  { name: 'odoo-corp-prod', vertical: 'Corporate', status: 'maintenance', uptime: 98.20, latency: 0, version: '18.0' },
];

const uptimeData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  uptime: 98 + Math.random() * 2,
  latency: 100 + Math.random() * 180,
}));

const costData = [
  { vertical: 'F&B', cost: 142, licenses: 84 },
  { vertical: 'Active', cost: 98, licenses: 56 },
  { vertical: 'Retail', cost: 312, licenses: 198 },
  { vertical: 'Distrib', cost: 76, licenses: 42 },
  { vertical: 'Service', cost: 88, licenses: 51 },
  { vertical: 'Corp', cost: 54, licenses: 28 },
];

const auditLogs = [
  { id: 1, actor: 'ade.maryadi@erajaya.co.id', action: 'tenant.create', target: 'odoo-fnb-jakarta-02', status: 'success', ts: '2 min ago', ip: '10.20.4.18' },
  { id: 2, actor: 'system.scheduler', action: 'backup.complete', target: 'odoo-eraspace-prod', status: 'success', ts: '12 min ago', ip: 'internal' },
  { id: 3, actor: 'b.santoso@erajaya.co.id', action: 'rbac.grant', target: 'role: tenant_admin', status: 'success', ts: '34 min ago', ip: '10.20.4.42' },
  { id: 4, actor: 'd.pratama@erajaya.co.id', action: 'document.download', target: 'SOW-AIM-2026.pdf', status: 'success', ts: '1 hr ago', ip: '10.20.5.11' },
  { id: 5, actor: 'unknown', action: 'auth.login', target: 'portal.gateway', status: 'failed', ts: '1 hr ago', ip: '203.142.x.x' },
  { id: 6, actor: 'r.wijaya@erajaya.co.id', action: 'config.update', target: 'odoo-active-prod / mail.smtp', status: 'success', ts: '2 hr ago', ip: '10.20.4.91' },
  { id: 7, actor: 'system.backup', action: 'snapshot.create', target: 'all production tenants', status: 'success', ts: '3 hr ago', ip: 'internal' },
];

const documents = [
  { name: 'MSA-Erajaya-Odoo-Master.pdf', kind: 'Master Agreement', vertical: 'All', size: '2.4 MB', updated: 'Mar 12, 2026', owner: 'Legal' },
  { name: 'SOW-FNB-Phase-2.docx', kind: 'Statement of Work', vertical: 'F&B', size: '892 KB', updated: 'Apr 02, 2026', owner: 'VAS' },
  { name: 'Runbook-Eraspace-POS.md', kind: 'Runbook', vertical: 'Retail', size: '124 KB', updated: 'Apr 18, 2026', owner: 'Ops' },
  { name: 'Deliverable-AIM-Drone-Modules.zip', kind: 'Deliverable', vertical: 'Distribution', size: '18.2 MB', updated: 'May 04, 2026', owner: 'VAS' },
  { name: 'License-Inventory-2026Q2.xlsx', kind: 'License', vertical: 'All', size: '412 KB', updated: 'May 10, 2026', owner: 'Finance' },
];

const users = [
  { name: 'Ade Maryadi', email: 'ade.maryadi@erajaya.co.id', role: 'Platform Admin', verticals: 'All', mfa: true, last: 'now' },
  { name: 'Budi Santoso', email: 'b.santoso@erajaya.co.id', role: 'Tenant Admin', verticals: 'F&B, Active', mfa: true, last: '14 min ago' },
  { name: 'Dewi Pratama', email: 'd.pratama@erajaya.co.id', role: 'Auditor (Read)', verticals: 'All', mfa: true, last: '2 hr ago' },
  { name: 'Rangga Wijaya', email: 'r.wijaya@erajaya.co.id', role: 'Ops Engineer', verticals: 'Retail, Distrib', mfa: true, last: '4 hr ago' },
  { name: 'Sinta Kurnia', email: 's.kurnia@erajaya.co.id', role: 'Finance Viewer', verticals: 'All', mfa: false, last: '1 day ago' },
];

// ============================================================================
// SHARED UI PRIMITIVES
// ============================================================================
const StatusDot = ({ status }) => {
  const map = {
    healthy: tokens.ok,
    degraded: tokens.warn,
    down: tokens.err,
    maintenance: tokens.info,
    success: tokens.ok,
    failed: tokens.err,
  };
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8, height: 8, borderRadius: '50%',
        background: map[status] || tokens.muted,
        boxShadow: `0 0 0 3px ${map[status]}20`,
      }}
    />
  );
};

const Pill = ({ children, tone = 'neutral' }) => {
  const toneMap = {
    neutral: { bg: '#F4F4F2', fg: '#52525B', bd: '#E7E5E2' },
    brand:   { bg: tokens.brandSoft, fg: tokens.brandDeep, bd: '#FACFD3' },
    ok:      { bg: '#D1FAE5', fg: '#065F46', bd: '#A7F3D0' },
    warn:    { bg: '#FEF3C7', fg: '#92400E', bd: '#FDE68A' },
    err:     { bg: '#FEE2E2', fg: '#991B1B', bd: '#FECACA' },
    info:    { bg: '#DBEAFE', fg: '#1E40AF', bd: '#BFDBFE' },
  };
  const t = toneMap[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 999,
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`,
      fontSize: 11, fontWeight: 600, letterSpacing: 0.2, fontFamily: 'inherit',
      textTransform: 'uppercase',
    }}>{children}</span>
  );
};

// ============================================================================
// LANDING PAGE
// ============================================================================
function LandingPage({ onEnterApp }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div style={{
      minHeight: '100vh',
      background: tokens.surface,
      color: tokens.ink,
      fontFamily: "'Inter', -apple-system, system-ui, sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700;9..144,800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }
        .grain { position: relative; }
        .grain::before {
          content: ''; position: absolute; inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.4'/%3E%3C/svg%3E");
          opacity: 0.06; pointer-events: none; mix-blend-mode: multiply;
        }
      `}</style>

      {/* NAV */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
          padding: scrolled ? '12px 0' : '20px 0',
          background: scrolled ? 'rgba(250,250,249,0.85)' : 'transparent',
          backdropFilter: scrolled ? 'blur(20px)' : 'none',
          borderBottom: scrolled ? `1px solid ${tokens.border}` : '1px solid transparent',
          transition: 'all 0.3s ease',
        }}
      >
        <div style={{
          maxWidth: 1280, margin: '0 auto', padding: '0 32px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: tokens.brand,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'Fraunces, serif', fontWeight: 800, color: '#fff', fontSize: 20,
              letterSpacing: -1,
            }}>E</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: -0.3 }}>Erajaya</div>
              <div style={{ fontSize: 10, color: tokens.muted, letterSpacing: 1, textTransform: 'uppercase' }}>Odoo Hub</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 32, fontSize: 14, fontWeight: 500 }}>
            <a href="#capabilities" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Capabilities</a>
            <a href="#verticals" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Verticals</a>
            <a href="#security" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Security</a>
            <a href="#contact" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Contact</a>
          </div>
          <button
            onClick={onEnterApp}
            style={{
              background: tokens.ink, color: '#fff', border: 'none',
              padding: '10px 18px', borderRadius: 8,
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
              fontFamily: 'inherit',
            }}
          >
            <Lock size={14} /> Sign in
          </button>
        </div>
      </motion.nav>

      {/* HERO */}
      <section style={{ paddingTop: 160, paddingBottom: 120, position: 'relative', overflow: 'hidden' }}>
        {/* decorative red bar */}
        <div style={{
          position: 'absolute', top: 0, right: -100, width: 600, height: 600,
          background: `radial-gradient(circle, ${tokens.brand}15 0%, transparent 60%)`,
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', top: 120, left: 0, width: 4, height: 200,
          background: tokens.brand,
        }} />

        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px', position: 'relative' }}>
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <Pill tone="brand">
              <Sparkles size={11} /> Internal Platform · Erajaya Group
            </Pill>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            style={{
              fontFamily: 'Fraunces, serif',
              fontSize: 'clamp(48px, 7vw, 88px)',
              fontWeight: 600,
              letterSpacing: -2.5,
              lineHeight: 0.98,
              margin: '28px 0 24px',
              maxWidth: 980,
            }}
          >
            One platform to govern{' '}
            <span style={{
              fontStyle: 'italic', fontWeight: 500,
              color: tokens.brand,
              position: 'relative',
            }}>every Odoo instance</span>{' '}
            across Erajaya verticals.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25 }}
            style={{
              fontSize: 20, lineHeight: 1.5, color: tokens.muted,
              maxWidth: 680, marginBottom: 40, fontWeight: 400,
            }}
          >
            Centralized tenant provisioning, real-time health monitoring, immutable
            audit trail, and document governance — purpose-built for the Value
            Added Services team.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            style={{ display: 'flex', gap: 12, alignItems: 'center' }}
          >
            <button
              onClick={onEnterApp}
              style={{
                background: tokens.brand, color: '#fff', border: 'none',
                padding: '16px 28px', borderRadius: 10,
                fontSize: 15, fontWeight: 600, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 10,
                boxShadow: `0 10px 30px -8px ${tokens.brand}60`,
                fontFamily: 'inherit',
              }}
            >
              Enter Admin Console <ArrowRight size={16} />
            </button>
            <button style={{
              background: 'transparent', color: tokens.ink, border: `1px solid ${tokens.border}`,
              padding: '16px 24px', borderRadius: 10,
              fontSize: 15, fontWeight: 600, cursor: 'pointer',
              fontFamily: 'inherit',
            }}>
              View Platform Brief
            </button>
          </motion.div>

          {/* trust strip */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            style={{
              marginTop: 80, paddingTop: 32, borderTop: `1px solid ${tokens.border}`,
              display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 32,
            }}
          >
            {[
              { k: '63', l: 'Active tenants', s: 'across 6 verticals' },
              { k: '99.94%', l: 'Aggregate uptime', s: 'rolling 30 days' },
              { k: '4.2M', l: 'Audit events', s: 'last quarter' },
              { k: 'UU PDP', l: 'Compliant', s: 'No. 27/2022 ready' },
            ].map((s, i) => (
              <div key={i}>
                <div style={{
                  fontFamily: 'Fraunces, serif', fontSize: 40, fontWeight: 600,
                  letterSpacing: -1.5, lineHeight: 1,
                }}>{s.k}</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 8 }}>{s.l}</div>
                <div style={{ fontSize: 12, color: tokens.muted, marginTop: 2 }}>{s.s}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* CAPABILITIES */}
      <section id="capabilities" style={{
        padding: '120px 0', background: tokens.ink, color: '#fff', position: 'relative',
      }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 72 }}>
            <div>
              <div style={{
                fontSize: 11, letterSpacing: 3, textTransform: 'uppercase',
                color: tokens.brand, fontWeight: 600, marginBottom: 16,
              }}>— Platform capabilities</div>
              <h2 style={{
                fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500,
                letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 720,
              }}>
                What the platform <em style={{ color: tokens.brand, fontWeight: 600 }}>governs.</em>
              </h2>
            </div>
            <div style={{ maxWidth: 320, color: '#a1a1aa', fontSize: 14, lineHeight: 1.6 }}>
              High-level information for stakeholders. Operational controls live
              inside the admin console.
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: tokens.borderDark }}>
            {[
              { icon: Layers, t: 'Multi-Tenant Management', d: 'Provision, suspend, and configure Odoo instances across F&B, Retail, Active Lifestyle, Distribution, Service, and Corporate verticals from a single pane.' },
              { icon: Activity, t: 'Services Monitoring', d: 'Real-time uptime, latency, and resource telemetry per tenant. Synthetic checks, alerting routes, and SLA tracking against 99.9% target.' },
              { icon: History, t: 'Audit Trail', d: 'Immutable, append-only log of every administrative action, login event, and configuration change. Searchable by actor, target, time window.' },
              { icon: FileText, t: 'Document Management', d: 'Versioned repository for MSAs, SOWs, runbooks, deliverables, and license inventories — scoped per vertical with access controls.' },
              { icon: Users, t: 'User & RBAC', d: 'Role-based access across all verticals with least-privilege defaults. MFA enforcement, session policies, and break-glass procedures.' },
              { icon: DollarSign, t: 'Cost & License Tracking', d: 'Per-vertical subscription, infrastructure, and Odoo license costs. Monthly chargeback reports and consumption forecasting.' },
            ].map((c, i) => {
              const Icon = c.icon;
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-80px' }}
                  transition={{ duration: 0.5, delay: (i % 3) * 0.1 }}
                  style={{
                    background: tokens.ink, padding: '40px 32px',
                    transition: 'background 0.3s',
                    cursor: 'default',
                  }}
                  whileHover={{ background: tokens.inkSoft }}
                >
                  <div style={{
                    width: 44, height: 44, borderRadius: 10,
                    background: `${tokens.brand}20`, border: `1px solid ${tokens.brand}40`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: 24,
                  }}>
                    <Icon size={20} color={tokens.brand} />
                  </div>
                  <h3 style={{
                    fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500,
                    margin: '0 0 12px', letterSpacing: -0.5,
                  }}>{c.t}</h3>
                  <p style={{ color: '#a1a1aa', fontSize: 14, lineHeight: 1.6, margin: 0 }}>
                    {c.d}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* VERTICALS SHOWCASE */}
      <section id="verticals" style={{ padding: '120px 0', background: tokens.surfaceAlt }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ marginBottom: 64 }}>
            <div style={{
              fontSize: 11, letterSpacing: 3, textTransform: 'uppercase',
              color: tokens.brand, fontWeight: 600, marginBottom: 16,
            }}>— Verticals under management</div>
            <h2 style={{
              fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500,
              letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 800,
            }}>
              Six business <em style={{ color: tokens.brand, fontWeight: 600 }}>verticals.</em> One operational layer.
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {verticals.map((v, i) => (
              <motion.div
                key={v.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.06 }}
                whileHover={{ y: -4 }}
                style={{
                  background: '#fff', borderRadius: 16,
                  padding: 28, border: `1px solid ${tokens.border}`,
                  transition: 'box-shadow 0.3s',
                }}
              >
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  marginBottom: 32,
                }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: 12,
                    background: `${v.color}15`, border: `1px solid ${v.color}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 24,
                  }}>{v.icon}</div>
                  <div style={{
                    fontFamily: 'Fraunces, serif', fontSize: 38, fontWeight: 600,
                    color: v.color, letterSpacing: -1, lineHeight: 1,
                  }}>{String(v.tenants).padStart(2, '0')}</div>
                </div>
                <h3 style={{
                  fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 600,
                  margin: '0 0 6px', letterSpacing: -0.5,
                }}>{v.name}</h3>
                <p style={{ fontSize: 13, color: tokens.muted, margin: '0 0 20px' }}>
                  {v.tagline}
                </p>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  paddingTop: 16, borderTop: `1px solid ${tokens.border}`,
                  fontSize: 12, color: tokens.muted,
                }}>
                  <span>Active tenants</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: tokens.ok, fontWeight: 600 }}>
                    <StatusDot status="healthy" /> Operational
                  </span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* SECURITY */}
      <section id="security" style={{ padding: '120px 0', background: tokens.surface }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 80, alignItems: 'center' }}>
            <div>
              <div style={{
                fontSize: 11, letterSpacing: 3, textTransform: 'uppercase',
                color: tokens.brand, fontWeight: 600, marginBottom: 16,
              }}>— Security posture</div>
              <h2 style={{
                fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500,
                letterSpacing: -1.5, lineHeight: 1, margin: '0 0 24px',
              }}>
                Built to the standard Erajaya <em style={{ color: tokens.brand, fontWeight: 600 }}>demands.</em>
              </h2>
              <p style={{ fontSize: 17, lineHeight: 1.6, color: tokens.muted, marginBottom: 32 }}>
                Defense-in-depth from edge to database. Every administrative
                action is authenticated, authorized, and audited — without
                exception.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {[
                  { i: ShieldCheck, t: 'UU PDP No. 27/2022', d: 'Data residency, retention, and subject rights compliant.' },
                  { i: KeyRound, t: 'SSO + MFA enforced', d: 'OIDC via Erajaya identity provider. TOTP/WebAuthn required.' },
                  { i: Lock, t: 'Encryption at rest & in transit', d: 'AES-256 storage, TLS 1.3 transport, KMS-managed keys.' },
                  { i: FileSearch, t: 'Immutable audit log', d: 'Append-only, 7-year retention, cryptographically chained.' },
                ].map((item, i) => {
                  const Icon = item.i;
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -20 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.4, delay: i * 0.08 }}
                      style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}
                    >
                      <div style={{
                        width: 36, height: 36, borderRadius: 8,
                        background: tokens.brandSoft, color: tokens.brand,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <Icon size={18} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 2 }}>{item.t}</div>
                        <div style={{ fontSize: 13, color: tokens.muted, lineHeight: 1.5 }}>{item.d}</div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {/* Decorative security visual */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              style={{
                position: 'relative', aspectRatio: '1', borderRadius: 24,
                background: tokens.ink, overflow: 'hidden',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {/* concentric circles */}
              {[1, 2, 3, 4].map(n => (
                <motion.div
                  key={n}
                  animate={{ scale: [1, 1.05, 1], opacity: [0.4, 0.7, 0.4] }}
                  transition={{ duration: 3 + n * 0.5, repeat: Infinity, delay: n * 0.3 }}
                  style={{
                    position: 'absolute',
                    width: `${n * 22}%`, height: `${n * 22}%`,
                    border: `1px solid ${tokens.brand}${(60 - n * 10).toString(16)}`,
                    borderRadius: '50%',
                  }}
                />
              ))}
              <div style={{
                width: 90, height: 90, borderRadius: '50%',
                background: tokens.brand,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 60px ${tokens.brand}`,
                zIndex: 2,
              }}>
                <ShieldCheck size={42} color="#fff" />
              </div>
              {/* corner labels */}
              <div style={{ position: 'absolute', top: 24, left: 24, color: '#a1a1aa', fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>
                01 / Edge
              </div>
              <div style={{ position: 'absolute', top: 24, right: 24, color: '#a1a1aa', fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>
                02 / Auth
              </div>
              <div style={{ position: 'absolute', bottom: 24, left: 24, color: '#a1a1aa', fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>
                03 / App
              </div>
              <div style={{ position: 'absolute', bottom: 24, right: 24, color: '#a1a1aa', fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>
                04 / Data
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="contact" style={{ padding: '100px 0', background: tokens.brand, color: '#fff' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px', textAlign: 'center' }}>
          <h2 style={{
            fontFamily: 'Fraunces, serif', fontSize: 64, fontWeight: 500,
            letterSpacing: -2, lineHeight: 1, margin: '0 0 24px',
          }}>
            Ready to take the console?
          </h2>
          <p style={{ fontSize: 18, opacity: 0.85, marginBottom: 36, maxWidth: 540, margin: '0 auto 36px' }}>
            Sign in with your Erajaya identity to access the operational layer.
          </p>
          <button
            onClick={onEnterApp}
            style={{
              background: '#fff', color: tokens.brand, border: 'none',
              padding: '18px 36px', borderRadius: 10,
              fontSize: 16, fontWeight: 700, cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 10,
              fontFamily: 'inherit',
            }}
          >
            Enter Admin Console <ArrowRight size={18} />
          </button>
        </div>
      </section>

      {/* FOOTER */}
      <footer style={{ padding: '40px 0', background: tokens.ink, color: '#71717a' }}>
        <div style={{
          maxWidth: 1280, margin: '0 auto', padding: '0 32px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          fontSize: 12,
        }}>
          <div>© 2026 PT Erajaya Swasembada Tbk · Internal use only</div>
          <div style={{ display: 'flex', gap: 24 }}>
            <span>Powered by VAS · PT Azec Indonesia Management Services</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

// ============================================================================
// LOGIN GATE
// ============================================================================
function LoginGate({ onLogin, onBack }) {
  const [step, setStep] = useState('credentials');
  const [email, setEmail] = useState('ade.maryadi@erajaya.co.id');
  const [loading, setLoading] = useState(false);

  const handleSubmit = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      if (step === 'credentials') setStep('mfa');
      else onLogin();
    }, 800);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: tokens.ink,
      color: '#fff',
      fontFamily: "'Inter', sans-serif",
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* bg grid */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `linear-gradient(${tokens.borderDark} 1px, transparent 1px), linear-gradient(90deg, ${tokens.borderDark} 1px, transparent 1px)`,
        backgroundSize: '60px 60px',
        opacity: 0.5,
        maskImage: 'radial-gradient(circle at center, black 0%, transparent 70%)',
      }} />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          background: tokens.inkSoft,
          border: `1px solid ${tokens.borderDark}`,
          borderRadius: 16,
          padding: 40,
          width: 440,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 8,
            background: tokens.brand,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'Fraunces, serif', fontWeight: 800, fontSize: 22, color: '#fff',
          }}>E</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Erajaya Odoo Hub</div>
            <div style={{ fontSize: 11, color: tokens.muted, letterSpacing: 1, textTransform: 'uppercase' }}>Admin Console</div>
          </div>
        </div>

        <AnimatePresence mode="wait">
          {step === 'credentials' ? (
            <motion.div key="cred" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}>
              <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 28, fontWeight: 500, margin: '0 0 8px', letterSpacing: -0.5 }}>
                Sign in
              </h2>
              <p style={{ fontSize: 13, color: tokens.muted, margin: '0 0 28px' }}>
                Use your Erajaya corporate identity.
              </p>

              <label style={{ fontSize: 12, fontWeight: 600, color: '#d4d4d8', display: 'block', marginBottom: 8, letterSpacing: 0.3 }}>
                EMAIL
              </label>
              <input
                value={email}
                onChange={e => setEmail(e.target.value)}
                style={{
                  width: '100%', padding: '12px 14px',
                  background: tokens.ink, color: '#fff',
                  border: `1px solid ${tokens.borderDark}`, borderRadius: 8,
                  fontSize: 14, fontFamily: 'inherit', marginBottom: 16,
                  outline: 'none',
                }}
              />
              <label style={{ fontSize: 12, fontWeight: 600, color: '#d4d4d8', display: 'block', marginBottom: 8, letterSpacing: 0.3 }}>
                PASSWORD
              </label>
              <input
                type="password"
                defaultValue="••••••••••••"
                style={{
                  width: '100%', padding: '12px 14px',
                  background: tokens.ink, color: '#fff',
                  border: `1px solid ${tokens.borderDark}`, borderRadius: 8,
                  fontSize: 14, fontFamily: 'inherit', marginBottom: 24,
                  outline: 'none',
                }}
              />
              <button
                onClick={handleSubmit}
                disabled={loading}
                style={{
                  width: '100%', background: tokens.brand, color: '#fff',
                  border: 'none', padding: '14px', borderRadius: 8,
                  fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  fontFamily: 'inherit',
                  opacity: loading ? 0.7 : 1,
                }}
              >
                {loading ? 'Verifying…' : 'Continue'}
              </button>

              <div style={{
                marginTop: 24, padding: 12,
                background: `${tokens.info}10`, border: `1px solid ${tokens.info}30`,
                borderRadius: 8, fontSize: 12, color: '#93C5FD',
                display: 'flex', gap: 10, alignItems: 'flex-start',
              }}>
                <ShieldCheck size={14} style={{ marginTop: 1, flexShrink: 0 }} />
                <span>SSO via Erajaya IdP. MFA required for all admin sessions.</span>
              </div>
            </motion.div>
          ) : (
            <motion.div key="mfa" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }}>
              <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 28, fontWeight: 500, margin: '0 0 8px', letterSpacing: -0.5 }}>
                Verify identity
              </h2>
              <p style={{ fontSize: 13, color: tokens.muted, margin: '0 0 28px' }}>
                Enter the 6-digit code from your authenticator app.
              </p>

              <div style={{ display: 'flex', gap: 8, marginBottom: 28, justifyContent: 'center' }}>
                {[1, 2, 3, 4, 5, 6].map(i => (
                  <input
                    key={i}
                    maxLength={1}
                    defaultValue={i <= 4 ? Math.floor(Math.random() * 10) : ''}
                    style={{
                      width: 48, height: 56, textAlign: 'center',
                      background: tokens.ink, color: '#fff',
                      border: `1px solid ${tokens.borderDark}`, borderRadius: 8,
                      fontSize: 22, fontWeight: 600, fontFamily: 'JetBrains Mono, monospace',
                      outline: 'none',
                    }}
                  />
                ))}
              </div>

              <button
                onClick={handleSubmit}
                disabled={loading}
                style={{
                  width: '100%', background: tokens.brand, color: '#fff',
                  border: 'none', padding: '14px', borderRadius: 8,
                  fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  fontFamily: 'inherit',
                  opacity: loading ? 0.7 : 1,
                }}
              >
                {loading ? 'Verifying…' : 'Enter Console'}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={onBack}
          style={{
            marginTop: 20, width: '100%', background: 'transparent',
            color: tokens.muted, border: 'none', fontSize: 12,
            cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          ← Back to homepage
        </button>
      </motion.div>
    </div>
  );
}

// ============================================================================
// ADMIN APP SHELL
// ============================================================================
const adminNav = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
  { id: 'tenants', label: 'Tenants & Verticals', icon: Layers },
  { id: 'monitoring', label: 'Services Monitoring', icon: Activity },
  { id: 'audit', label: 'Audit Trail', icon: History },
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'users', label: 'Users & RBAC', icon: Users },
  { id: 'costs', label: 'Cost & Licenses', icon: DollarSign },
];

function AdminShell({ onLogout }) {
  const [active, setActive] = useState('dashboard');

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

      {/* SIDEBAR */}
      <aside style={{
        width: 240, background: tokens.ink, color: '#fff',
        display: 'flex', flexDirection: 'column',
        position: 'sticky', top: 0, height: '100vh',
      }}>
        <div style={{ padding: '24px 20px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: `1px solid ${tokens.borderDark}` }}>
          <div style={{
            width: 32, height: 32, borderRadius: 7,
            background: tokens.brand,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'Fraunces, serif', fontWeight: 800, fontSize: 18, color: '#fff',
          }}>E</div>
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
              background: tokens.brand, color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700,
            }}>AM</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Ade Maryadi</div>
              <div style={{ fontSize: 10, color: tokens.muted }}>Platform Admin</div>
            </div>
          </div>
          <button
            onClick={onLogout}
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

      {/* MAIN */}
      <main style={{ flex: 1, overflow: 'auto' }}>
        {/* TOPBAR */}
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

        {/* PAGE CONTENT */}
        <div style={{ padding: 32 }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {active === 'dashboard' && <DashboardPage />}
              {active === 'tenants' && <TenantsPage />}
              {active === 'monitoring' && <MonitoringPage />}
              {active === 'audit' && <AuditPage />}
              {active === 'documents' && <DocumentsPage />}
              {active === 'users' && <UsersPage />}
              {active === 'costs' && <CostsPage />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}

// ============================================================================
// ADMIN PAGES
// ============================================================================
const Card = ({ children, style }) => (
  <div style={{
    background: '#fff', borderRadius: 12,
    border: `1px solid ${tokens.border}`,
    padding: 20, ...style,
  }}>{children}</div>
);

const PageTitle = ({ title, subtitle, action }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 24 }}>
    <div>
      <h1 style={{
        fontFamily: 'Fraunces, serif', fontSize: 32, fontWeight: 600,
        margin: 0, letterSpacing: -0.5,
      }}>{title}</h1>
      {subtitle && <p style={{ color: tokens.muted, fontSize: 14, margin: '6px 0 0' }}>{subtitle}</p>}
    </div>
    {action}
  </div>
);

function DashboardPage() {
  const stats = [
    { label: 'Active tenants', value: '63', delta: '+4', icon: Layers, tone: tokens.brand },
    { label: 'Uptime (30d)', value: '99.94%', delta: '+0.02', icon: Activity, tone: tokens.ok },
    { label: 'Open incidents', value: '2', delta: '-1', icon: AlertCircle, tone: tokens.warn },
    { label: 'Monthly spend', value: 'Rp 770M', delta: '+3.2%', icon: DollarSign, tone: tokens.info },
  ];

  return (
    <>
      <PageTitle
        title="Welcome back, Ade"
        subtitle="Operational snapshot across all Erajaya Odoo verticals — last refreshed 30s ago"
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {stats.map((s, i) => {
          const Icon = s.icon;
          return (
            <Card key={i}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: `${s.tone}15`, color: s.tone,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={16} />
                </div>
                <span style={{
                  fontSize: 11, fontWeight: 600, color: tokens.ok,
                  background: '#D1FAE5', padding: '2px 8px', borderRadius: 4,
                }}>{s.delta}</span>
              </div>
              <div style={{ fontFamily: 'Fraunces, serif', fontSize: 36, fontWeight: 600, letterSpacing: -1, lineHeight: 1 }}>
                {s.value}
              </div>
              <div style={{ fontSize: 12, color: tokens.muted, marginTop: 6 }}>{s.label}</div>
            </Card>
          );
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 24 }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Aggregate uptime (24h)</div>
              <div style={{ fontSize: 11, color: tokens.muted }}>All production tenants</div>
            </div>
            <Pill tone="ok"><Check size={10} /> Healthy</Pill>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={uptimeData}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tokens.brand} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={tokens.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} vertical={false} />
              <XAxis dataKey="hour" stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} interval={3} />
              <YAxis domain={[96, 100]} stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${tokens.border}` }} />
              <Area type="monotone" dataKey="uptime" stroke={tokens.brand} strokeWidth={2} fill="url(#g1)" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Tenants by vertical</div>
            <div style={{ fontSize: 11, color: tokens.muted }}>63 active instances</div>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={verticals} dataKey="tenants" nameKey="name" innerRadius={50} outerRadius={75} paddingAngle={2}>
                {verticals.map((v, i) => <Cell key={i} fill={v.color} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {verticals.slice(0, 4).map(v => (
              <div key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: v.color }} />
                <span style={{ flex: 1, color: tokens.muted }}>{v.name}</span>
                <span style={{ fontWeight: 600 }}>{v.tenants}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Recent activity</div>
            <div style={{ fontSize: 11, color: tokens.muted }}>Last 7 events from the audit trail</div>
          </div>
          <button style={{
            background: 'transparent', border: 'none', color: tokens.brand,
            fontSize: 12, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'inherit',
          }}>
            View all <ArrowUpRight size={12} />
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {auditLogs.slice(0, 5).map((log, i) => (
            <div key={log.id} style={{
              display: 'grid', gridTemplateColumns: '20px 1fr 1.5fr 1fr 80px',
              alignItems: 'center', gap: 12, padding: '10px 0',
              borderBottom: i < 4 ? `1px solid ${tokens.border}` : 'none',
              fontSize: 13,
            }}>
              <StatusDot status={log.status} />
              <div>
                <code style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', color: tokens.brand }}>
                  {log.action}
                </code>
              </div>
              <div style={{ color: tokens.muted, fontSize: 12 }}>{log.target}</div>
              <div style={{ fontSize: 12, color: tokens.muted }}>{log.actor}</div>
              <div style={{ fontSize: 11, color: tokens.muted, textAlign: 'right' }}>{log.ts}</div>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

function TenantsPage() {
  return (
    <>
      <PageTitle
        title="Tenants & Verticals"
        subtitle="Provision and manage Odoo instances across all Erajaya verticals"
        action={
          <button style={{
            background: tokens.brand, color: '#fff', border: 'none',
            padding: '10px 16px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
          }}>
            <Plus size={14} /> Provision tenant
          </button>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {verticals.map(v => (
          <Card key={v.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div style={{
                width: 44, height: 44, borderRadius: 10,
                background: `${v.color}15`, fontSize: 22,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>{v.icon}</div>
              <button style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: tokens.muted }}>
                <MoreVertical size={16} />
              </button>
            </div>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{v.name}</div>
            <div style={{ fontSize: 12, color: tokens.muted, marginBottom: 16 }}>{v.tagline}</div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              paddingTop: 16, borderTop: `1px solid ${tokens.border}`,
            }}>
              <div>
                <div style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 600, lineHeight: 1 }}>
                  {v.tenants}
                </div>
                <div style={{ fontSize: 10, color: tokens.muted, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  tenants
                </div>
              </div>
              <Pill tone="ok"><StatusDot status="healthy" /> Active</Pill>
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>All tenant instances</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{
              background: tokens.surfaceAlt, border: 'none',
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
              fontFamily: 'inherit',
            }}>
              <Filter size={12} /> Filter
            </button>
          </div>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: tokens.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Instance</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Vertical</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Version</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Status</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Uptime</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}></th>
            </tr>
          </thead>
          <tbody>
            {services.map((s, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${tokens.border}` }}>
                <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{s.name}</td>
                <td style={{ padding: '12px 0', color: tokens.muted }}>{s.vertical}</td>
                <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>v{s.version}</td>
                <td style={{ padding: '12px 0' }}>
                  <Pill tone={s.status === 'healthy' ? 'ok' : s.status === 'degraded' ? 'warn' : 'info'}>
                    <StatusDot status={s.status} /> {s.status}
                  </Pill>
                </td>
                <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{s.uptime}%</td>
                <td style={{ padding: '12px 0', textAlign: 'right' }}>
                  <button style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: tokens.muted }}>
                    <ChevronRight size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function MonitoringPage() {
  return (
    <>
      <PageTitle
        title="Services Monitoring"
        subtitle="Real-time health, latency, and SLA tracking across Odoo tenants"
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { l: 'Healthy', v: '4', tone: 'ok' },
          { l: 'Degraded', v: '1', tone: 'warn' },
          { l: 'Maintenance', v: '1', tone: 'info' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <StatusDot status={s.tone === 'ok' ? 'healthy' : s.tone === 'warn' ? 'degraded' : 'maintenance'} />
              <div style={{ fontSize: 13, color: tokens.muted }}>{s.l}</div>
              <div style={{ flex: 1, textAlign: 'right', fontFamily: 'Fraunces, serif', fontSize: 28, fontWeight: 600 }}>
                {s.v}
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Latency over time (24h, ms)</div>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={uptimeData}>
            <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} vertical={false} />
            <XAxis dataKey="hour" stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} interval={2} />
            <YAxis stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${tokens.border}` }} />
            <Line type="monotone" dataKey="latency" stroke={tokens.brand} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card>
        <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Instance health detail</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: tokens.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Instance</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Status</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Uptime</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Latency p95</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Last check</th>
            </tr>
          </thead>
          <tbody>
            {services.map((s, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${tokens.border}` }}>
                <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{s.name}</td>
                <td style={{ padding: '12px 0' }}>
                  <Pill tone={s.status === 'healthy' ? 'ok' : s.status === 'degraded' ? 'warn' : 'info'}>
                    <StatusDot status={s.status} /> {s.status}
                  </Pill>
                </td>
                <td style={{ padding: '12px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 60, height: 6, background: tokens.border, borderRadius: 3, overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${s.uptime}%`, height: '100%',
                        background: s.uptime > 99.9 ? tokens.ok : s.uptime > 99 ? tokens.warn : tokens.err,
                      }} />
                    </div>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{s.uptime}%</span>
                  </div>
                </td>
                <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
                  {s.latency > 0 ? `${s.latency}ms` : '—'}
                </td>
                <td style={{ padding: '12px 0', color: tokens.muted, fontSize: 12 }}>just now</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function AuditPage() {
  return (
    <>
      <PageTitle
        title="Audit Trail"
        subtitle="Immutable record of every administrative action, login, and configuration change"
        action={
          <button style={{
            background: tokens.surfaceAlt, border: `1px solid ${tokens.border}`,
            padding: '10px 16px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
          }}>
            <Download size={14} /> Export
          </button>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Events (24h)', v: '14,832' },
          { l: 'Unique actors', v: '47' },
          { l: 'Failed attempts', v: '3', tone: 'err' },
          { l: 'Retention', v: '7 yrs' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>
              {s.l}
            </div>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 30, fontWeight: 600,
              letterSpacing: -0.5, marginTop: 6,
              color: s.tone === 'err' ? tokens.err : tokens.ink,
            }}>{s.v}</div>
          </Card>
        ))}
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Recent events</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: tokens.surfaceAlt, padding: '6px 10px', borderRadius: 6,
              fontSize: 12, color: tokens.muted,
            }}>
              <Filter size={12} /> All actions
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {auditLogs.map((log, i) => (
            <div key={log.id} style={{
              display: 'grid',
              gridTemplateColumns: '24px 200px 1fr 200px 120px 80px',
              alignItems: 'center', gap: 16, padding: '14px 0',
              borderBottom: i < auditLogs.length - 1 ? `1px solid ${tokens.border}` : 'none',
              fontSize: 13,
            }}>
              <StatusDot status={log.status} />
              <code style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', color: tokens.brand, fontWeight: 500 }}>
                {log.action}
              </code>
              <div style={{ color: tokens.ink, fontSize: 13 }}>{log.target}</div>
              <div style={{ fontSize: 12, color: tokens.muted, fontFamily: 'JetBrains Mono, monospace' }}>{log.actor}</div>
              <div style={{ fontSize: 11, color: tokens.muted, fontFamily: 'JetBrains Mono, monospace' }}>{log.ip}</div>
              <div style={{ fontSize: 11, color: tokens.muted, textAlign: 'right' }}>{log.ts}</div>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

function DocumentsPage() {
  return (
    <>
      <PageTitle
        title="Document Management"
        subtitle="Versioned repository — contracts, SOWs, runbooks, deliverables, license records"
        action={
          <button style={{
            background: tokens.brand, color: '#fff', border: 'none',
            padding: '10px 16px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
          }}>
            <Plus size={14} /> Upload document
          </button>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Total documents', v: '247', i: FileText },
          { l: 'Master agreements', v: '8', i: ShieldCheck },
          { l: 'SOWs active', v: '23', i: GitBranch },
          { l: 'Storage used', v: '4.2 GB', i: Database },
        ].map((s, i) => {
          const Icon = s.i;
          return (
            <Card key={i}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 8, background: tokens.brandSoft, color: tokens.brand,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={16} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>
                    {s.l}
                  </div>
                  <div style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 600, lineHeight: 1 }}>{s.v}</div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <Card>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: tokens.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Document</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Type</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Vertical</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Owner</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Size</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Updated</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((d, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${tokens.border}` }}>
                <td style={{ padding: '14px 0', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 6,
                    background: tokens.surfaceAlt,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <FileText size={14} color={tokens.muted} />
                  </div>
                  <span style={{ fontWeight: 500 }}>{d.name}</span>
                </td>
                <td style={{ padding: '14px 0' }}>
                  <Pill tone="brand">{d.kind}</Pill>
                </td>
                <td style={{ padding: '14px 0', color: tokens.muted }}>{d.vertical}</td>
                <td style={{ padding: '14px 0', color: tokens.muted }}>{d.owner}</td>
                <td style={{ padding: '14px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: tokens.muted }}>{d.size}</td>
                <td style={{ padding: '14px 0', color: tokens.muted, fontSize: 12 }}>{d.updated}</td>
                <td style={{ padding: '14px 0', textAlign: 'right' }}>
                  <button style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: tokens.muted }}>
                    <Download size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function UsersPage() {
  return (
    <>
      <PageTitle
        title="Users & RBAC"
        subtitle="Identity, roles, and permissions across all verticals"
        action={
          <button style={{
            background: tokens.brand, color: '#fff', border: 'none',
            padding: '10px 16px', borderRadius: 8,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
          }}>
            <Plus size={14} /> Invite user
          </button>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Total users', v: '47' },
          { l: 'MFA enabled', v: '46', tone: 'ok' },
          { l: 'Privileged roles', v: '8' },
          { l: 'Inactive (30d)', v: '3', tone: 'warn' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>
              {s.l}
            </div>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 30, fontWeight: 600,
              letterSpacing: -0.5, marginTop: 6,
              color: s.tone === 'warn' ? tokens.warn : s.tone === 'ok' ? tokens.ok : tokens.ink,
            }}>{s.v}</div>
          </Card>
        ))}
      </div>

      <Card>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: tokens.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>User</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Role</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Vertical access</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>MFA</th>
              <th style={{ padding: '8px 0', fontWeight: 600 }}>Last active</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${tokens.border}` }}>
                <td style={{ padding: '14px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%',
                      background: tokens.brand, color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700,
                    }}>{u.name.split(' ').map(n => n[0]).join('')}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{u.name}</div>
                      <div style={{ fontSize: 11, color: tokens.muted, fontFamily: 'JetBrains Mono, monospace' }}>{u.email}</div>
                    </div>
                  </div>
                </td>
                <td style={{ padding: '14px 0' }}>
                  <Pill tone={u.role.includes('Admin') ? 'brand' : 'neutral'}>{u.role}</Pill>
                </td>
                <td style={{ padding: '14px 0', color: tokens.muted, fontSize: 12 }}>{u.verticals}</td>
                <td style={{ padding: '14px 0' }}>
                  {u.mfa
                    ? <Pill tone="ok"><CheckCircle2 size={10} /> Enabled</Pill>
                    : <Pill tone="warn"><AlertCircle size={10} /> Required</Pill>}
                </td>
                <td style={{ padding: '14px 0', color: tokens.muted, fontSize: 12 }}>{u.last}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function CostsPage() {
  const total = costData.reduce((a, b) => a + b.cost, 0);
  return (
    <>
      <PageTitle
        title="Cost & License Tracking"
        subtitle="Per-vertical infrastructure, subscriptions, and Odoo seat consumption"
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Monthly spend', v: `Rp ${total}M`, sub: '+3.2% vs last month' },
          { l: 'Active licenses', v: '459', sub: '12 unused' },
          { l: 'Annual run rate', v: `Rp ${(total * 12 / 1000).toFixed(1)}B`, sub: 'projected' },
          { l: 'Cost per tenant', v: `Rp ${Math.round(total / 63 * 1000)}K`, sub: 'avg' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>
              {s.l}
            </div>
            <div style={{ fontFamily: 'Fraunces, serif', fontSize: 28, fontWeight: 600, letterSpacing: -0.5, marginTop: 6, lineHeight: 1 }}>
              {s.v}
            </div>
            <div style={{ fontSize: 11, color: tokens.muted, marginTop: 6 }}>{s.sub}</div>
          </Card>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Spend by vertical (Rp M)</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={costData}>
              <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} vertical={false} />
              <XAxis dataKey="vertical" stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${tokens.border}` }} />
              <Bar dataKey="cost" fill={tokens.brand} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>License allocation</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {costData.map((c, i) => {
              const max = Math.max(...costData.map(d => d.licenses));
              return (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                    <span>{c.vertical}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: tokens.muted }}>{c.licenses}</span>
                  </div>
                  <div style={{
                    width: '100%', height: 6, background: tokens.border, borderRadius: 3, overflow: 'hidden',
                  }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(c.licenses / max) * 100}%` }}
                      transition={{ duration: 0.6, delay: i * 0.05 }}
                      style={{ height: '100%', background: tokens.brand }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </>
  );
}

// ============================================================================
// ROOT
// ============================================================================
export default function App() {
  const [view, setView] = useState('landing'); // landing | login | app

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={view}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
      >
        {view === 'landing' && <LandingPage onEnterApp={() => setView('login')} />}
        {view === 'login' && <LoginGate onLogin={() => setView('app')} onBack={() => setView('landing')} />}
        {view === 'app' && <AdminShell onLogout={() => setView('landing')} />}
      </motion.div>
    </AnimatePresence>
  );
}
