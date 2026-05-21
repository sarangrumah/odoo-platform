import React, { useEffect, useState } from 'react';
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity, AlertCircle, Layers, DollarSign, ArrowUpRight, Check } from 'lucide-react';
import { tokens, verticalDefs } from '../../tokens.js';
import { Card, PageTitle, Pill, StatusDot, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

// Deterministic synthetic series so the chart is stable across renders
// until the orchestrator exposes a real /metrics aggregation endpoint.
const uptimeData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  uptime: 98.5 + ((i * 37) % 100) / 70,
  latency: 110 + ((i * 53) % 100) * 1.6,
}));

export function DashboardPage() {
  const [tenants, setTenants] = useState([]);
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'unreachable' }));
    api.listTenants()
      .then(setTenants)
      .catch(e => setErr(String(e)));
  }, []);

  const active = tenants.filter(t => t.state === 'active').length;
  const suspended = tenants.filter(t => t.state === 'suspended').length;
  const total = tenants.length;

  const stats = [
    { label: 'Active tenants', value: String(active), delta: `${total} total`, icon: Layers, tone: tokens.brand },
    { label: 'Orchestrator',   value: health?.status === 'ok' ? 'OK' : (health?.status || '…'), delta: health?.version ? `v${health.version}` : '', icon: Activity, tone: health?.status === 'ok' ? tokens.ok : tokens.warn },
    { label: 'Suspended',      value: String(suspended), delta: suspended > 0 ? 'action needed' : 'none', icon: AlertCircle, tone: suspended > 0 ? tokens.warn : tokens.ok },
    { label: 'Verticals',      value: String(verticalDefs.length), delta: 'governed', icon: DollarSign, tone: tokens.accent },
  ];

  // Group tenants by `features.vertical` when set, otherwise distribute evenly.
  const byVertical = verticalDefs.map(v => ({
    ...v,
    tenants: tenants.filter(t => (t.features?.vertical || '') === v.id).length || 0,
  }));
  const pieData = byVertical.some(v => v.tenants > 0)
    ? byVertical
    : verticalDefs.map(v => ({ ...v, tenants: 1 })); // placeholder

  return (
    <>
      <PageTitle
        title="Welcome to Erajaya Odoo Hub"
        subtitle={err ? `Tenant data unavailable — ${err}` : 'Operational snapshot across all Erajaya Odoo verticals'}
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
                {s.delta && (
                  <span style={{
                    fontSize: 11, fontWeight: 600, color: tokens.muted,
                    background: tokens.surfaceAlt, padding: '2px 8px', borderRadius: 4,
                  }}>{s.delta}</span>
                )}
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
              <div style={{ fontSize: 11, color: tokens.muted, display: 'flex', gap: 8, alignItems: 'center', marginTop: 2 }}>
                <span>Synthetic series</span><DemoBadge />
              </div>
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
            <div style={{ fontSize: 11, color: tokens.muted }}>{total} active instances</div>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={pieData} dataKey="tenants" nameKey="name" innerRadius={50} outerRadius={75} paddingAngle={2}>
                {pieData.map((v, i) => <Cell key={i} fill={v.color} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {byVertical.slice(0, 4).map(v => (
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
            <div style={{ fontSize: 14, fontWeight: 600 }}>Recent tenants</div>
            <div style={{ fontSize: 11, color: tokens.muted }}>Last entries from the orchestrator registry</div>
          </div>
          <button style={{
            background: 'transparent', border: 'none', color: tokens.brand,
            fontSize: 12, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'inherit',
          }}>
            View all <ArrowUpRight size={12} />
          </button>
        </div>
        {tenants.length === 0 && (
          <div style={{ padding: 20, textAlign: 'center', color: tokens.muted, fontSize: 13 }}>
            {err
              ? 'Orchestrator unreachable. Check the BFF logs (`docker logs erajaya-hub-portal`).'
              : 'No tenants provisioned yet — use the orchestrator API or the Tenants page.'}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {tenants.slice(0, 5).map((t, i) => (
            <div key={t.slug} style={{
              display: 'grid', gridTemplateColumns: '20px 1fr 1.5fr 1fr 120px',
              alignItems: 'center', gap: 12, padding: '10px 0',
              borderBottom: i < Math.min(tenants.length, 5) - 1 ? `1px solid ${tokens.border}` : 'none',
              fontSize: 13,
            }}>
              <StatusDot status={t.state} />
              <code style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', color: tokens.brand }}>
                {t.slug}
              </code>
              <div style={{ color: tokens.muted, fontSize: 12 }}>{t.display_name}</div>
              <div style={{ fontSize: 12, color: tokens.muted }}>{t.plan_tier || '—'}</div>
              <div style={{ fontSize: 11, color: tokens.muted, textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>{t.db_name}</div>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
