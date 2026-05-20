import { useEffect, useState } from 'react';
import { Badge, Section, Table } from '../../components/ui';
import { listAudit } from '../../api';

const MOCK = [
  { id: 1, ts: '2026-05-20 09:15', actor: 'sara@erajaya.id', action: 'tenant.create', target: 'tenant_arkaim', severity: 'info' },
  { id: 2, ts: '2026-05-20 10:01', actor: 'andi@erajaya.id', action: 'journey.stage', target: 'J-2026-014', severity: 'info' },
  { id: 3, ts: '2026-05-20 11:33', actor: 'system', action: 'hmac.mismatch', target: '/v1/intake/submit', severity: 'warning' },
];

export default function AuditPage() {
  const [rows, setRows] = useState<any[]>(MOCK);
  useEffect(() => {
    listAudit(200)
      .then((r) => Array.isArray(r) && r.length && setRows(r))
      .catch(() => {/* keep mock */});
  }, []);
  return (
    <Section title="Audit Log" description="All sensitive actions on the platform">
      <Table
        columns={[
          { key: 'ts', label: 'Timestamp', width: 180 },
          { key: 'actor', label: 'Actor' },
          { key: 'action', label: 'Action' },
          { key: 'target', label: 'Target' },
          {
            key: 'severity',
            label: 'Severity',
            render: (r) => (
              <Badge tone={r.severity === 'warning' ? 'warning' : r.severity === 'danger' ? 'danger' : 'info'}>
                {r.severity}
              </Badge>
            ),
          },
        ]}
        rows={rows}
      />
    </Section>
  );
}
