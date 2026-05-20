import { useEffect, useState } from 'react';
import { Package, Rocket, Search } from 'lucide-react';
import { Badge, Button, Card, Input, Modal, Section, Select, Table } from '../../components/ui';
import EmptyState from '../../components/EmptyState';
import ConfigRequiredBanner from '../../components/ConfigRequiredBanner';
import { colors, spacing } from '../../tokens';
import { createDeployment, listDeployments, listModuleCatalog } from '../../api';

export default function ModuleDeployPage() {
  const [catalog, setCatalog] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [openMod, setOpenMod] = useState<any | null>(null);
  const [tenant, setTenant] = useState('1');
  const [env, setEnv] = useState('staging');
  const [canary, setCanary] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [apiError, setApiError] = useState<{ message: string; configRequired: boolean } | null>(null);

  useEffect(() => {
    const detectConfig = (msg: string) =>
      /turnstile|api key|webhook secret|vault|prometheus|ANTHROPIC|requires config/i.test(msg);
    Promise.all([
      listModuleCatalog().catch((e: any) => {
        const msg = e?.detail || e?.message || String(e);
        setApiError({ message: msg, configRequired: detectConfig(msg) });
        return null;
      }),
      listDeployments().catch(() => null),
    ]).then(([c, d]) => {
      if (Array.isArray(c)) setCatalog(c);
      if (Array.isArray(d)) setDeployments(d);
      setLoaded(true);
    });
  }, []);

  async function deploy() {
    if (!openMod) return;
    try {
      await createDeployment({
        module_id: openMod.id,
        tenant_id: Number(tenant),
        env,
        canary_phase: canary ? '10%' : 'full',
      });
    } catch {/* TODO surface error */}
    setOpenMod(null);
  }

  const filtered = catalog.filter(
    (m) => m.name.toLowerCase().includes(q.toLowerCase()) || m.technical_name.toLowerCase().includes(q.toLowerCase()),
  );

  const showCatalogEmpty = loaded && catalog.length === 0;

  return (
    <div>
      {apiError?.configRequired && (
        <ConfigRequiredBanner feature="Module deploy" hint={apiError.message} />
      )}
      <Section title="Module Catalog" description="Custom modules available for deployment">
        {showCatalogEmpty ? (
          <EmptyState
            icon={<Package size={48} />}
            title="No modules in catalog"
            description="The Hub module catalog is empty. Wait for the next catalog sync or run 'Rescan Catalog' from Hub Console."
          />
        ) : (
        <>
        <Card style={{ marginBottom: spacing.md, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Search size={14} color={colors.textMuted} />
          <Input placeholder="Search module…" value={q} onChange={(e) => setQ(e.target.value)} />
        </Card>
        <Table
          columns={[
            { key: 'name', label: 'Name' },
            { key: 'technical_name', label: 'Technical name' },
            { key: 'category', label: 'Category', render: (r) => <Badge tone="info">{r.category}</Badge> },
            { key: 'version', label: 'Version' },
            {
              key: 'canary',
              label: 'Canary',
              render: (r) => (r.is_canary_enabled ? <Badge tone="warning">enabled</Badge> : <Badge>disabled</Badge>),
            },
            {
              key: 'actions',
              label: '',
              render: (r) => (
                <Button size="sm" onClick={() => setOpenMod(r)}>
                  <Rocket size={12} /> Deploy
                </Button>
              ),
            },
          ]}
          rows={filtered}
        />
        </>
        )}
      </Section>

      <Section title="Deployment history">
        <Table
          columns={[
            { key: 'name', label: 'Ref' },
            { key: 'module_id', label: 'Module', render: (r) => Array.isArray(r.module_id) ? r.module_id[1] : r.module_id },
            { key: 'tenant_id', label: 'Tenant', render: (r) => Array.isArray(r.tenant_id) ? r.tenant_id[1] : r.tenant_id },
            { key: 'env', label: 'Env' },
            {
              key: 'state',
              label: 'State',
              render: (r) => <Badge tone={r.state === 'deployed' ? 'success' : 'warning'}>{r.state}</Badge>,
            },
            {
              key: 'canary_phase',
              label: 'Canary',
              render: (r) => <Badge tone={r.canary_phase === 'full' ? 'success' : 'warning'}>{r.canary_phase}</Badge>,
            },
            { key: 'deployed_at', label: 'Deployed at' },
          ]}
          rows={deployments}
        />
      </Section>

      <Modal open={!!openMod} onClose={() => setOpenMod(null)} title={openMod ? `Deploy: ${openMod.name}` : ''}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Tenant
            <Select value={tenant} onChange={(e) => setTenant(e.target.value)} style={{ marginTop: 4 }}>
              <option value="1">Erajaya Tower A</option>
              <option value="2">JDS Pratama</option>
              <option value="3">Telkom Pulsa</option>
            </Select>
          </label>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Environment
            <Select value={env} onChange={(e) => setEnv(e.target.value)} style={{ marginTop: 4 }}>
              <option value="staging">staging</option>
              <option value="prod">prod</option>
            </Select>
          </label>
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={canary} onChange={(e) => setCanary(e.target.checked)} />
            Canary rollout (10% → 50% → 100%)
          </label>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: spacing.sm }}>
            <Button variant="ghost" onClick={() => setOpenMod(null)}>
              Cancel
            </Button>
            <Button onClick={deploy}>
              <Rocket size={14} /> Deploy
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
