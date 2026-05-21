import React, { useEffect, useState } from 'react';
import { Plus, CheckCircle2, AlertCircle } from 'lucide-react';
import { tokens } from '../../tokens.js';
import { Card, PageTitle, Pill, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

export function UsersPage() {
  const [data, setData] = useState({ users: [], stats: {}, demo: true });
  useEffect(() => { api.users().then(setData).catch(() => {}); }, []);
  const users = data.users || [];
  const stats = data.stats || {};

  return (
    <>
      <PageTitle
        title="Users & RBAC"
        subtitle="Identity, roles, and permissions across all verticals"
        action={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {data.demo && <DemoBadge />}
            <button style={{
              background: tokens.brand, color: '#fff', border: 'none',
              padding: '10px 16px', borderRadius: 8,
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
            }}>
              <Plus size={14} /> Invite user
            </button>
          </div>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { l: 'Total users',       v: stats.total ?? users.length },
          { l: 'MFA enabled',       v: stats.mfa ?? users.filter(u => u.mfa).length, tone: 'ok' },
          { l: 'Privileged roles',  v: stats.privileged ?? '—' },
          { l: 'Inactive (30d)',    v: stats.inactive ?? '—', tone: 'warn' },
        ].map((s, i) => (
          <Card key={i}>
            <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>{s.l}</div>
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
                      background: `linear-gradient(135deg, ${tokens.brand}, ${tokens.accent})`,
                      color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700,
                    }}>{u.name.split(' ').map(n => n[0]).join('').slice(0, 2)}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{u.name}</div>
                      <div style={{ fontSize: 11, color: tokens.muted, fontFamily: 'JetBrains Mono, monospace' }}>{u.email}</div>
                    </div>
                  </div>
                </td>
                <td style={{ padding: '14px 0' }}>
                  <Pill tone={u.role?.includes('Admin') ? 'brand' : 'neutral'}>{u.role}</Pill>
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
