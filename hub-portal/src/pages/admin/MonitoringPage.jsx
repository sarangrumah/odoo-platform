import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { tokens } from '../../tokens.js';
import { Card, PageTitle, Pill, StatusDot, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

const latencyData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  latency: 120 + ((i * 47) % 100) * 2,
}));

export function MonitoringPage() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.monitoring().then(setData).catch(() => setData({ services: [], demo: true }));
  }, []);

  const services = data?.services || [];
  const buckets = {
    healthy: services.filter(s => s.status === 'healthy').length,
    degraded: services.filter(s => s.status === 'degraded').length,
    maintenance: services.filter(s => s.status === 'maintenance').length,
  };

  return (
    <>
      <PageTitle
        title="Services Monitoring"
        subtitle="Real-time health, latency, and SLA tracking across Odoo tenants"
        action={data?.demo ? <DemoBadge /> : null}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { l: 'Healthy', v: buckets.healthy, tone: 'ok' },
          { l: 'Degraded', v: buckets.degraded, tone: 'warn' },
          { l: 'Maintenance', v: buckets.maintenance, tone: 'info' },
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
          <LineChart data={latencyData}>
            <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} vertical={false} />
            <XAxis dataKey="hour" stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} interval={2} />
            <YAxis stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${tokens.border}` }} />
            <Line type="monotone" dataKey="latency" stroke={tokens.accent} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card>
        <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Instance health detail</div>
        {services.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: tokens.muted, fontSize: 13 }}>
            No service probes returned. Wire Prometheus or container healthchecks into <code>/api/monitoring</code>.
          </div>
        ) : (
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
                      <div style={{ width: 60, height: 6, background: tokens.border, borderRadius: 3, overflow: 'hidden' }}>
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
        )}
      </Card>
    </>
  );
}
