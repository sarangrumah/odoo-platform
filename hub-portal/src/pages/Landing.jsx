import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, Layers, FileText, Users, DollarSign, History, Lock,
  Sparkles, ShieldCheck, KeyRound, FileSearch, ArrowRight,
} from 'lucide-react';
import { tokens, verticalDefs } from '../tokens.js';
import { StatusDot, Pill, ErajayaMark } from '../components/ui.jsx';

export function LandingPage({ onEnterApp }) {
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
            <ErajayaMark size={36} />
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: -0.3 }}>Erajaya</div>
              <div style={{ fontSize: 10, color: tokens.muted, letterSpacing: 1, textTransform: 'uppercase' }}>Odoo Hub</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 32, fontSize: 14, fontWeight: 500 }}>
            <a href="#capabilities" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Capabilities</a>
            <a href="#modules" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Modules</a>
            <a href="#configuration" style={{ color: tokens.ink, textDecoration: 'none', opacity: 0.7 }}>Configuration</a>
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
        <div style={{
          position: 'absolute', top: 0, right: -100, width: 600, height: 600,
          background: `radial-gradient(circle, ${tokens.brand}15 0%, transparent 60%)`,
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', top: 240, right: -60, width: 400, height: 400,
          background: `radial-gradient(circle, ${tokens.accent}12 0%, transparent 60%)`,
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', top: 120, left: 0, width: 4, height: 200,
          background: `linear-gradient(180deg, ${tokens.brand} 0%, ${tokens.accent} 100%)`,
        }} />

        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px', position: 'relative' }}>
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <Pill tone="brand">
              <Sparkles size={11} /> Internal Platform · Erajaya Group
            </Pill>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }}
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
            <span style={{ fontStyle: 'italic', fontWeight: 500, color: tokens.brand }}>every Odoo instance</span>{' '}
            across Erajaya verticals.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }}
            style={{ fontSize: 20, lineHeight: 1.5, color: tokens.muted, maxWidth: 680, marginBottom: 40, fontWeight: 400 }}
          >
            Centralized tenant provisioning, real-time health monitoring, immutable
            audit trail, and document governance — purpose-built for the Value
            Added Services team.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.4 }}
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
              background: 'transparent', color: tokens.accent, border: `1px solid ${tokens.accent}40`,
              padding: '16px 24px', borderRadius: 10,
              fontSize: 15, fontWeight: 600, cursor: 'pointer',
              fontFamily: 'inherit',
            }}>
              View Platform Brief
            </button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.6 }}
            style={{
              marginTop: 80, paddingTop: 32, borderTop: `1px solid ${tokens.border}`,
              display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 32,
            }}
          >
            {[
              { k: '6', l: 'Business verticals', s: 'under unified governance' },
              { k: '99.5%', l: 'SLA target', s: 'aggregate uptime' },
              { k: 'HMAC', l: 'API trust', s: 'orchestrator + AI gateway' },
              { k: 'UU PDP', l: 'Compliant', s: 'No. 27/2022 ready' },
            ].map((s, i) => (
              <div key={i}>
                <div style={{ fontFamily: 'Fraunces, serif', fontSize: 40, fontWeight: 600, letterSpacing: -1.5, lineHeight: 1 }}>{s.k}</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 8 }}>{s.l}</div>
                <div style={{ fontSize: 12, color: tokens.muted, marginTop: 2 }}>{s.s}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* CAPABILITIES */}
      <section id="capabilities" style={{ padding: '120px 0', background: tokens.ink, color: '#fff', position: 'relative' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 72 }}>
            <div>
              <div style={{ fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: tokens.brand, fontWeight: 600, marginBottom: 16 }}>— Platform capabilities</div>
              <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500, letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 720 }}>
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
              { icon: Layers, t: 'Multi-Tenant Management', d: 'Provision, suspend, and configure Odoo instances across all six Erajaya verticals from a single orchestrator — DB-per-tenant isolation, encrypted DEKs, automated install scripts.' },
              { icon: Activity, t: 'Services Monitoring', d: 'Real-time uptime and health probes per tenant. SLA tracking against the 99.5% production target, with Prometheus metrics for the AI gateway and orchestrator.' },
              { icon: History, t: 'Audit Trail', d: 'Append-only log of every administrative action, provisioning event, and key-rotation operation — searchable by actor, target, and time window.' },
              { icon: FileText, t: 'Document Management', d: 'Versioned repository for MSAs, SOWs, runbooks, deliverables, and license inventories — scoped per vertical with access controls.' },
              { icon: Users, t: 'User & RBAC', d: 'Role-based access aligned with the platform security model. MFA enforcement, session policies, and break-glass procedures.' },
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
                  style={{ background: tokens.ink, padding: '40px 32px', transition: 'background 0.3s', cursor: 'default' }}
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
                  <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 24, fontWeight: 500, margin: '0 0 12px', letterSpacing: -0.5 }}>{c.t}</h3>
                  <p style={{ color: '#a1a1aa', fontSize: 14, lineHeight: 1.6, margin: 0 }}>{c.d}</p>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CUSTOM MODULES */}
      <section id="modules" style={{ padding: '120px 0', background: tokens.surface }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ marginBottom: 64 }}>
            <div style={{ fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: tokens.brand, fontWeight: 600, marginBottom: 16 }}>— Custom Odoo modules</div>
            <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500, letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 800 }}>
              Built on Odoo. Extended for <em style={{ color: tokens.brand, fontWeight: 600 }}>Erajaya.</em>
            </h2>
            <p style={{ color: tokens.muted, fontSize: 16, lineHeight: 1.6, margin: '20px 0 0', maxWidth: 720 }}>
              The platform ships Odoo 19 Community as the application core and layers in custom modules
              that fill EE gaps, encode Indonesian compliance, and provide the multi-tenant orchestration
              fabric. Every module is versioned, dependency-graphed, and rollable-back per tenant.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
            {[
              { cat: 'Onboarding', t: 'Onboarding Journey', d: 'State machine intake → BRD → go/no-go → provisioning → UAT → go-live, mirrored bi-directionally to Project tasks.', mods: ['custom_onboarding_journey', 'custom_landing_admin'] },
              { cat: 'AI', t: 'BRD Analyzer', d: 'Upload BRD (PDF/DOCX/PPTX) → AI extracts sections, scores fit vs platform capability catalog, recommends custom modules + mandays, surfaces cross-vertical impact.', mods: ['custom_brd_analyzer', 'custom_ai_bridge', 'custom_ai_features'] },
              { cat: 'Infra', t: 'Tenant Infra & VPS Console', d: 'VPS fleet inventory, SSH bootstrap (harden OS, Docker, Caddy), per-tenant environment (dev/staging/prod), health probes.', mods: ['custom_tenant_infra', 'custom_super_admin'] },
              { cat: 'Hub', t: 'Hub Console & Module Deploy', d: 'Live capability catalog scanned from all addons. Canary deploy with pre-backup, healthcheck gating, and one-click rollback per environment.', mods: ['custom_hub_console'] },
              { cat: 'DevOps', t: 'Dev Cycle Tracker', d: 'Track every recommendation through backlog → in-dev → code review → QA → UAT → deployed. GitHub/GitLab PR + CI webhooks update cycle state automatically.', mods: ['custom_dev_cycle'] },
              { cat: 'Compliance', t: 'Tax & PDP (Indonesia)', d: 'Coretax bukti potong + Bupot Unifikasi, PPh withholding engine (PMK-131), PDP field masking, Pajakku ASPP integration.', mods: ['custom_coretax', 'custom_coretax_bupot', 'custom_pph_witholding', 'custom_pdp_masking', 'custom_coretax_pajakku'] },
              { cat: 'Accounting', t: 'EE-Gap Finance', d: 'Fixed assets, recurring journals, consolidation, follow-up, credit limit, match-line — the parts of Odoo Enterprise Accounting filled in on top of Community.', mods: ['custom_accounting_full', 'custom_accounting_asset', 'custom_accounting_recurring', 'custom_bank_import'] },
              { cat: 'Ops', t: 'Ops Monitoring & Backup', d: 'Prometheus pull, Alertmanager incidents, capacity forecasting; scheduled DB backups to MinIO/S3 with retention + replicate-to-staging.', mods: ['custom_ops_monitor'] },
              { cat: 'Vertical', t: 'Field, HHT, IoT, WMS', d: 'Field service, handheld terminal bridge, IoT ingest, WMS putaway / cycle count / TO engine — vertical-derived modules feeding back into the hub catalog.', mods: ['custom_field_service', 'custom_hht_bridge', 'custom_iot_bridge', 'custom_wms_putaway', 'custom_wms_cycle_count', 'custom_wms_to_engine'] },
            ].map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.08 }}
                style={{
                  background: '#fff', borderRadius: 12,
                  border: `1px solid ${tokens.border}`,
                  padding: 24, display: 'flex', flexDirection: 'column', gap: 12,
                }}
              >
                <div style={{
                  alignSelf: 'flex-start',
                  fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase',
                  color: tokens.brand, fontWeight: 700,
                  padding: '3px 8px', borderRadius: 4, background: tokens.brandSoft,
                }}>{m.cat}</div>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: -0.4, color: tokens.ink }}>{m.t}</h3>
                <p style={{ color: tokens.muted, fontSize: 13, lineHeight: 1.6, margin: 0 }}>{m.d}</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 'auto', paddingTop: 8 }}>
                  {m.mods.map((mod) => (
                    <code key={mod} style={{
                      fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
                      color: tokens.muted, background: tokens.surfaceAlt,
                      padding: '2px 6px', borderRadius: 4, border: `1px solid ${tokens.border}`,
                    }}>{mod}</code>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>

          <div style={{
            marginTop: 48, padding: '24px 32px', borderRadius: 12,
            background: tokens.surfaceAlt, border: `1px solid ${tokens.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
          }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: tokens.ink, marginBottom: 4 }}>
                33+ custom modules currently installed.
              </div>
              <div style={{ fontSize: 12, color: tokens.muted }}>
                Tracked in <code style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>custom.hub.module.catalog</code>,
                deployable per tenant via canary rollout from the admin console.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Pill tone="ok">Production</Pill>
              <Pill tone="info">Partial</Pill>
              <Pill tone="neutral">Scaffold</Pill>
            </div>
          </div>
        </div>
      </section>

      {/* CONFIGURATION */}
      <section id="configuration" style={{ padding: '120px 0', background: tokens.ink, color: '#fff' }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ marginBottom: 64 }}>
            <div style={{ fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: tokens.brand, fontWeight: 600, marginBottom: 16 }}>— Configuration surface</div>
            <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500, letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 800 }}>
              What you can <em style={{ color: tokens.brand, fontWeight: 600 }}>tune</em> per tenant.
            </h2>
            <p style={{ color: '#a1a1aa', fontSize: 16, lineHeight: 1.6, margin: '20px 0 0', maxWidth: 720 }}>
              Configuration is split across three layers: <strong style={{ color: '#fff' }}>tenant lifecycle</strong> (orchestrator),
              <strong style={{ color: '#fff' }}> module behavior</strong> (Odoo Settings / ir.config_parameter), and
              <strong style={{ color: '#fff' }}> integration secrets</strong> (Vault / env). Each layer is
              auditable, versioned, and recoverable from backup.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>
            {[
              {
                t: 'Tenant provisioning',
                items: [
                  'Plan tier (Starter, Growth, Enterprise) → quota & feature flags',
                  'Custom modules selected per vertical (canary or full rollout)',
                  'Backup schedule + retention days (cron expression)',
                  'PITR enable, scheduled DB replicate (prod → staging)',
                  'Custom domain + Caddy reverse proxy with auto-TLS',
                ],
              },
              {
                t: 'Company profile',
                items: [
                  'Legal name, NPWP, bank account (multi-bank)',
                  'Logo, brand colors, default chart-of-accounts',
                  'Default language (id/en), timezone, fiscal year start',
                  'Coretax + Pajakku ASPP credentials (per tenant)',
                  'Approval matrix (engine-driven, multi-tier)',
                ],
              },
              {
                t: 'AI & automation',
                items: [
                  'AI provider (Claude, OpenAI, Ollama) — per workspace',
                  'BRD analyzer prompt + capability catalog (auto-built)',
                  'NLQ chat scope (which models exposed to natural language queries)',
                  'Nightly anomaly scans (account.move, hr.payslip, coretax.transaction)',
                  'AI cost ceiling + alerting per tenant',
                ],
              },
              {
                t: 'Compliance & PDP',
                items: [
                  'PDP field masking registry (per model, per role)',
                  'Coretax e-Faktur sequence + sertel rotation',
                  'PPh witholding rules (PMK-131 seed + custom)',
                  'Audit retention policy + immutable hash-chain log',
                  'Document workspace ACL (MSA, SOW, runbook)',
                ],
              },
              {
                t: 'Infrastructure',
                items: [
                  'SSH credential reference (vault:// or file://)',
                  'Bootstrap templates (harden OS, Docker, Caddy, Odoo) — versioned',
                  'Prometheus scrape targets per VPS',
                  'Grafana dashboard UID embedded in admin console',
                  'GitHub/GitLab webhook secrets for dev cycle tracking',
                ],
              },
              {
                t: 'Identity & access',
                items: [
                  'Odoo res.users RBAC (Onboarding BA, Tenant Infra Manager, Super Admin, …)',
                  'Session policy (TTL, MFA enforcement)',
                  'API key per service-account (orchestrator, hub-portal, AI gateway)',
                  'Break-glass procedure with append-only audit',
                  'Public intake rate-limit (per IP per hour)',
                ],
              },
            ].map((c, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.5, delay: (i % 2) * 0.08 }}
                style={{
                  background: tokens.inkSoft, borderRadius: 12,
                  border: `1px solid ${tokens.borderDark}`,
                  padding: 28,
                }}
              >
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 600, margin: '0 0 16px', color: '#fff' }}>{c.t}</h3>
                <ul style={{ margin: 0, padding: '0 0 0 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {c.items.map((it, j) => (
                    <li key={j} style={{ color: '#c4c4c8', fontSize: 13, lineHeight: 1.55 }}>{it}</li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* VERTICALS */}
      <section id="verticals" style={{ padding: '120px 0', background: tokens.surfaceAlt }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px' }}>
          <div style={{ marginBottom: 64 }}>
            <div style={{ fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: tokens.brand, fontWeight: 600, marginBottom: 16 }}>— Verticals under management</div>
            <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500, letterSpacing: -1.5, lineHeight: 1, margin: 0, maxWidth: 800 }}>
              Six business <em style={{ color: tokens.brand, fontWeight: 600 }}>verticals.</em> One operational layer.
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {verticalDefs.map((v, i) => (
              <motion.div
                key={v.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.06 }}
                whileHover={{ y: -4 }}
                style={{ background: '#fff', borderRadius: 16, padding: 28, border: `1px solid ${tokens.border}`, transition: 'box-shadow 0.3s' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 32 }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: 12,
                    background: `${v.color}15`, border: `1px solid ${v.color}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 24,
                  }}>{v.icon}</div>
                </div>
                <h3 style={{ fontFamily: 'Fraunces, serif', fontSize: 22, fontWeight: 600, margin: '0 0 6px', letterSpacing: -0.5 }}>{v.name}</h3>
                <p style={{ fontSize: 13, color: tokens.muted, margin: '0 0 20px' }}>{v.tagline}</p>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  paddingTop: 16, borderTop: `1px solid ${tokens.border}`,
                  fontSize: 12, color: tokens.muted,
                }}>
                  <span>Status</span>
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
              <div style={{ fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: tokens.brand, fontWeight: 600, marginBottom: 16 }}>— Security posture</div>
              <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 56, fontWeight: 500, letterSpacing: -1.5, lineHeight: 1, margin: '0 0 24px' }}>
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
                  { i: KeyRound, t: 'HMAC-signed APIs', d: 'Orchestrator and AI gateway require X-Custom-Signature on every call.' },
                  { i: Lock, t: 'Per-tenant Fernet DEKs', d: 'AES-256 storage, wrapped by a master KEK, never persisted by Odoo.' },
                  { i: FileSearch, t: 'Immutable audit log', d: 'Append-only, long-term retention, cryptographically chained.' },
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
              {[1, 2, 3, 4].map(n => (
                <motion.div
                  key={n}
                  animate={{ scale: [1, 1.05, 1], opacity: [0.4, 0.7, 0.4] }}
                  transition={{ duration: 3 + n * 0.5, repeat: Infinity, delay: n * 0.3 }}
                  style={{
                    position: 'absolute',
                    width: `${n * 22}%`, height: `${n * 22}%`,
                    border: `1px solid ${n % 2 ? tokens.brand : tokens.accent}${(60 - n * 10).toString(16)}`,
                    borderRadius: '50%',
                  }}
                />
              ))}
              <div style={{
                width: 90, height: 90, borderRadius: '50%',
                background: `linear-gradient(135deg, ${tokens.brand}, ${tokens.accent})`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 60px ${tokens.brand}80`,
                zIndex: 2,
              }}>
                <ShieldCheck size={42} color="#fff" />
              </div>
              {['01 / Edge', '02 / Auth', '03 / App', '04 / Data'].map((label, i) => {
                const pos = [
                  { top: 24, left: 24 }, { top: 24, right: 24 },
                  { bottom: 24, left: 24 }, { bottom: 24, right: 24 },
                ][i];
                return (
                  <div key={i} style={{ position: 'absolute', ...pos, color: '#a1a1aa', fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>
                    {label}
                  </div>
                );
              })}
            </motion.div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="contact" style={{
        padding: '100px 0',
        background: `linear-gradient(135deg, ${tokens.brand} 0%, ${tokens.brandDeep} 60%, ${tokens.accent} 100%)`,
        color: '#fff',
      }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 32px', textAlign: 'center' }}>
          <h2 style={{ fontFamily: 'Fraunces, serif', fontSize: 64, fontWeight: 500, letterSpacing: -2, lineHeight: 1, margin: '0 0 24px' }}>
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

      <footer style={{ padding: '40px 0', background: tokens.ink, color: '#71717a' }}>
        <div style={{
          maxWidth: 1280, margin: '0 auto', padding: '0 32px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12,
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
