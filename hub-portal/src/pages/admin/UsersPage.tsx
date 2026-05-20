import { useEffect, useState } from 'react';
import { Badge, Section, Table } from '../../components/ui';
import { listUsers } from '../../api';

const MOCK = [
  { id: 1, name: 'Sara Sopian', email: 'sara@erajaya.id', role: 'platform_admin', last_login: '2026-05-19' },
  { id: 2, name: 'Andi BA', email: 'andi@erajaya.id', role: 'business_analyst', last_login: '2026-05-20' },
  { id: 3, name: 'Risma Ops', email: 'risma@erajaya.id', role: 'operations', last_login: '2026-05-20' },
];

export default function UsersPage() {
  const [rows, setRows] = useState<any[]>(MOCK);
  useEffect(() => {
    listUsers()
      .then((r) => Array.isArray(r) && r.length && setRows(r))
      .catch(() => {/* keep mock */});
  }, []);
  return (
    <Section title="Users" description="Platform operators & business analysts">
      <Table
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'email', label: 'Email' },
          { key: 'role', label: 'Role', render: (r) => <Badge tone="info">{r.role}</Badge> },
          { key: 'last_login', label: 'Last login' },
        ]}
        rows={rows}
      />
    </Section>
  );
}
