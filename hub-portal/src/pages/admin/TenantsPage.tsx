import { useEffect, useState } from 'react';
import { Badge, Card, Input, Section, Table } from '../../components/ui';
import { spacing } from '../../tokens';
import { listTenants } from '../../api';

interface Tenant {
  id: number;
  name: string;
  vertical: string;
  status: string;
  db: string;
  go_live?: string;
}

const MOCK: Tenant[] = [
  { id: 1, name: 'Erajaya Tower A', vertical: 'residensia', status: 'live', db: 'tenant_erajaya_a', go_live: '2025-09-12' },
  { id: 2, name: 'JDS Pratama', vertical: 'jds', status: 'uat', db: 'tenant_jds_pratama', go_live: '2026-06-01' },
  { id: 3, name: 'Telkom Pulsa', vertical: 'ppob', status: 'live', db: 'tenant_telkom_ppob' },
];

export default function TenantsPage() {
  const [rows, setRows] = useState<Tenant[]>(MOCK);
  const [q, setQ] = useState('');

  useEffect(() => {
    listTenants()
      .then((r) => Array.isArray(r) && r.length && setRows(r as Tenant[]))
      .catch(() => {/* keep mock */});
  }, []);

  const filtered = rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <Section title="Tenants" description="Provisioned tenants across all verticals">
      <Card style={{ marginBottom: spacing.md }}>
        <Input placeholder="Search tenants…" value={q} onChange={(e) => setQ(e.target.value)} />
      </Card>
      <Table
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'vertical', label: 'Vertical', render: (r) => <Badge tone="info">{r.vertical}</Badge> },
          { key: 'status', label: 'Status', render: (r) => <Badge tone={r.status === 'live' ? 'success' : 'warning'}>{r.status}</Badge> },
          { key: 'db', label: 'Database' },
          { key: 'go_live', label: 'Go-live' },
        ]}
        rows={filtered}
      />
    </Section>
  );
}
