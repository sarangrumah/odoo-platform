import React, { useEffect, useState } from 'react';
import { Plus, FileText, ShieldCheck, GitBranch, Database, Download } from 'lucide-react';
import { tokens } from '../../tokens.js';
import { Card, PageTitle, Pill, DemoBadge } from '../../components/ui.jsx';
import { api } from '../../api';

export function DocumentsPage() {
  const [data, setData] = useState({ documents: [], stats: {}, demo: true });
  useEffect(() => { api.documents().then(setData).catch(() => {}); }, []);
  const docs = data.documents || [];
  const stats = data.stats || {};

  const statCards = [
    { l: 'Total documents',   v: stats.total ?? docs.length, i: FileText },
    { l: 'Master agreements', v: stats.msa ?? '—', i: ShieldCheck },
    { l: 'SOWs active',       v: stats.sow ?? '—', i: GitBranch },
    { l: 'Storage used',      v: stats.storage ?? '—', i: Database },
  ];

  return (
    <>
      <PageTitle
        title="Document Management"
        subtitle="Versioned repository — contracts, SOWs, runbooks, deliverables, license records"
        action={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {data.demo && <DemoBadge />}
            <button style={{
              background: tokens.brand, color: '#fff', border: 'none',
              padding: '10px 16px', borderRadius: 8,
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'inherit',
            }}>
              <Plus size={14} /> Upload document
            </button>
          </div>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {statCards.map((s, i) => {
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
                  <div style={{ fontSize: 11, color: tokens.muted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>{s.l}</div>
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
            {docs.map((d, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${tokens.border}` }}>
                <td style={{ padding: '14px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 6, background: tokens.surfaceAlt, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <FileText size={14} color={tokens.muted} />
                    </div>
                    <span style={{ fontWeight: 500 }}>{d.name}</span>
                  </div>
                </td>
                <td style={{ padding: '14px 0' }}><Pill tone="brand">{d.kind}</Pill></td>
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
