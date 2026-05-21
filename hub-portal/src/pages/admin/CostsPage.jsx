import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { tokens } from '../../tokens.js';
import { Card, PageTitle, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

export function CostsPage() {
  const [data, setData] = useState({ cost_by_vertical: [], summary: {}, demo: true });
  useEffect(() => { api.costs().then(setData).catch(() => {}); }, []);
  const series = data.cost_by_vertical || [];
  const summary = data.summary || {};
  const total = series.reduce((a, b) => a + (b.cost || 0), 0);

  return (
    <>
      <PageTitle
        title="Cost & License Tracking"
        subtitle="Per-vertical infrastructure, subscriptions, and Odoo seat consumption"
        action={data.demo ? <DemoBadge /> : null}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Monthly spend',   v: summary.monthly ?? `Rp ${total}M`, sub: summary.delta ?? '—' },
          { l: 'Active licenses', v: summary.licenses ?? '—',           sub: summary.licenses_sub ?? '' },
          { l: 'Annual run rate', v: summary.annual ?? `Rp ${(total * 12 / 1000).toFixed(1)}B`, sub: 'projected' },
          { l: 'Cost per tenant', v: summary.per_tenant ?? '—',         sub: 'avg' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>{s.l}</div>
            <div style={{ fontFamily: 'Fraunces, serif', fontSize: 28, fontWeight: 600, letterSpacing: -0.5, marginTop: 6, lineHeight: 1 }}>{s.v}</div>
            <div style={{ fontSize: 11, color: tokens.muted, marginTop: 6 }}>{s.sub}</div>
          </Card>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Spend by vertical (Rp M)</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={series}>
              <defs>
                <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tokens.brand} stopOpacity={1} />
                  <stop offset="100%" stopColor={tokens.accent} stopOpacity={0.9} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={tokens.border} vertical={false} />
              <XAxis dataKey="vertical" stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={tokens.muted} fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${tokens.border}` }} />
              <Bar dataKey="cost" fill="url(#costGrad)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <div style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>License allocation</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {series.map((c, i) => {
              const max = Math.max(1, ...series.map(d => d.licenses || 0));
              return (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                    <span>{c.vertical}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: tokens.muted }}>{c.licenses}</span>
                  </div>
                  <div style={{ width: '100%', height: 6, background: tokens.border, borderRadius: 3, overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${((c.licenses || 0) / max) * 100}%` }}
                      transition={{ duration: 0.6, delay: i * 0.05 }}
                      style={{ height: '100%', background: `linear-gradient(90deg, ${tokens.brand}, ${tokens.accent})` }}
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
