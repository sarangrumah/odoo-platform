import React, { useEffect, useState } from 'react';
import { Download, Filter } from 'lucide-react';
import { tokens } from '../../tokens.js';
import { Card, PageTitle, StatusDot, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

export function AuditPage() {
  const [data, setData] = useState({ events: [], stats: {}, demo: true });
  useEffect(() => {
    api.audit().then(setData).catch(() => {});
  }, []);
  const events = data.events || [];
  const stats = data.stats || {};

  return (
    <>
      <PageTitle
        title="Audit Trail"
        subtitle="Immutable record of every administrative action, login, and configuration change"
        action={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {data.demo && <DemoBadge />}
            <button style={{
              background: tokens.surfaceAlt, border: `1px solid ${tokens.border}`,
              padding: '10px 16px', borderRadius: 8,
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
            }}>
              <Download size={14} /> Export
            </button>
          </div>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Events (24h)', v: stats.events_24h ?? '—' },
          { l: 'Unique actors', v: stats.unique_actors ?? '—' },
          { l: 'Failed attempts', v: stats.failed ?? '—', tone: 'err' },
          { l: 'Retention', v: stats.retention ?? '7 yrs' },
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
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: tokens.surfaceAlt, padding: '6px 10px', borderRadius: 6,
            fontSize: 12, color: tokens.muted,
          }}>
            <Filter size={12} /> All actions
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {events.map((log, i) => (
            <div key={log.id} style={{
              display: 'grid',
              gridTemplateColumns: '24px 200px 1fr 200px 120px 80px',
              alignItems: 'center', gap: 16, padding: '14px 0',
              borderBottom: i < events.length - 1 ? `1px solid ${tokens.border}` : 'none',
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
