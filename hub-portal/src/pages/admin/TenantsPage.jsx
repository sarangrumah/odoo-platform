import React, { useEffect, useState } from 'react';
import { Plus, Filter, ChevronRight, MoreVertical } from 'lucide-react';
import { tokens, verticalDefs } from '../../tokens.js';
import { Card, PageTitle, Pill, StatusDot } from '../../components/ui.jsx';
import { api } from '../../api';

export function TenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.listTenants().then(setTenants).catch(e => setErr(String(e)));
  }, []);

  const byVertical = verticalDefs.map(v => ({
    ...v,
    count: tenants.filter(t => (t.features?.vertical || '') === v.id).length,
  }));

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
        {byVertical.map(v => (
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
                  {v.count}
                </div>
                <div style={{ fontSize: 10, color: tokens.muted, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  tenants
                </div>
              </div>
              <Pill tone={v.count > 0 ? 'ok' : 'neutral'}>
                <StatusDot status={v.count > 0 ? 'healthy' : 'archived'} /> {v.count > 0 ? 'Active' : 'Empty'}
              </Pill>
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

        {err && (
          <div style={{ padding: 16, background: '#FEE2E2', borderRadius: 8, fontSize: 13, color: '#991B1B' }}>
            Orchestrator unreachable: <code>{err}</code>
          </div>
        )}
        {!err && tenants.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center', color: tokens.muted, fontSize: 13 }}>
            No tenants in the registry. Provision via <code>POST /v1/tenants</code> on the orchestrator.
          </div>
        )}

        {tenants.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: tokens.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                <th style={{ padding: '8px 0', fontWeight: 600 }}>Slug</th>
                <th style={{ padding: '8px 0', fontWeight: 600 }}>Display name</th>
                <th style={{ padding: '8px 0', fontWeight: 600 }}>Database</th>
                <th style={{ padding: '8px 0', fontWeight: 600 }}>Plan</th>
                <th style={{ padding: '8px 0', fontWeight: 600 }}>State</th>
                <th style={{ padding: '8px 0', fontWeight: 600 }}></th>
              </tr>
            </thead>
            <tbody>
              {tenants.map(t => (
                <tr key={t.slug} style={{ borderTop: `1px solid ${tokens.border}` }}>
                  <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: tokens.brand, fontWeight: 600 }}>{t.slug}</td>
                  <td style={{ padding: '12px 0' }}>{t.display_name}</td>
                  <td style={{ padding: '12px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: tokens.muted }}>{t.db_name}</td>
                  <td style={{ padding: '12px 0', color: tokens.muted }}>{t.plan_tier || '—'}</td>
                  <td style={{ padding: '12px 0' }}>
                    <Pill tone={t.state === 'active' ? 'ok' : t.state === 'suspended' ? 'warn' : 'neutral'}>
                      <StatusDot status={t.state} /> {t.state}
                    </Pill>
                  </td>
                  <td style={{ padding: '12px 0', textAlign: 'right' }}>
                    <button style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: tokens.muted }}>
                      <ChevronRight size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
