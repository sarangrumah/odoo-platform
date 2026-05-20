import { useEffect, useState } from 'react';
import { Badge, Section, Table } from '../../components/ui';
import { listDocuments } from '../../api';

const MOCK = [
  { id: 1, name: 'PMK-131 Mapping', kind: 'compliance', updated: '2026-04-12', size: '1.2 MB' },
  { id: 2, name: 'Erajaya Tower A — BRD', kind: 'brd', updated: '2026-05-04', size: '3.4 MB' },
  { id: 3, name: 'JDS Onboarding Runbook', kind: 'runbook', updated: '2026-05-19', size: '420 KB' },
];

export default function DocumentsPage() {
  const [rows, setRows] = useState<any[]>(MOCK);
  useEffect(() => {
    listDocuments()
      .then((r) => Array.isArray(r) && r.length && setRows(r))
      .catch(() => {/* keep mock */});
  }, []);
  return (
    <Section title="Documents" description="BRDs, runbooks, compliance references">
      <Table
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'kind', label: 'Kind', render: (r) => <Badge tone="info">{r.kind}</Badge> },
          { key: 'updated', label: 'Updated', width: 140 },
          { key: 'size', label: 'Size', width: 100 },
        ]}
        rows={rows}
      />
    </Section>
  );
}
