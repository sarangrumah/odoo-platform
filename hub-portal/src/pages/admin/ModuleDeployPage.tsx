import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Package, Rocket, Search } from 'lucide-react';
import { Badge, Button, Card, Input, Modal, Section, Select, Table } from '../../components/ui';
import EmptyState from '../../components/EmptyState';
import ConfigRequiredBanner from '../../components/ConfigRequiredBanner';
import { colors, spacing } from '../../tokens';
import { createDeployment, listDeployments, listModuleCatalog, listTenants } from '../../api';

const PAGE_SIZE = 20;
const CATEGORIES = ['core', 'compliance', 'ee_gap', 'operations', 'vertical'];
const MATURITIES = ['scaffold', 'partial', 'production'];

export default function ModuleDeployPage() {
  const [catalog, setCatalog] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [fCategory, setFCategory] = useState('');
  const [fMaturity, setFMaturity] = useState('');
  const [page, setPage] = useState(1);
  const [openMod, setOpenMod] = useState<any | null>(null);
  const [tenantId, setTenantId] = useState('');
  const [deployMode, setDeployMode] = useState<'install' | 'upgrade' | 'uninstall'>('install');
  const [canary, setCanary] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [apiError, setApiError] = useState<{ message: string; configRequired: boolean } | null>(null);

  const refreshDeployments = () =>
    listDeployments().then((d) => Array.isArray(d) && setDeployments(d)).catch(() => null);

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
      listTenants().catch(() => null),
    ]).then(([c, d, t]) => {
      if (Array.isArray(c)) setCatalog(c);
      if (Array.isArray(d)) setDeployments(d);
      if (Array.isArray(t)) {
        setTenants(t);
        if (t.length > 0) setTenantId(String(t[0].id));
      }
      setLoaded(true);
    });
  }, []);

  async function deploy() {
    if (!openMod || !tenantId) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await createDeployment({
        catalog_id: openMod.id,
        tenant_id: Number(tenantId),
        deploy_mode: deployMode,
        canary_phase: canary ? 'canary' : 'full',
      });
      await refreshDeployments();
      setOpenMod(null);
    } catch (e: any) {
      setSubmitError(e?.detail || e?.message || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  const filtered = useMemo(() => {
    const needle = q.toLowerCase();
    return catalog.filter((m) => {
      if (fCategory && m.category !== fCategory) return false;
      if (fMaturity && m.maturity !== fMaturity) return false;
      if (!needle) return true;
      const haystack = `${m.module_name || ''} ${m.summary || ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [catalog, q, fCategory, fMaturity]);

  useEffect(() => {
    setPage(1);
  }, [q, fCategory, fMaturity]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

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
        <Card style={{ marginBottom: spacing.md, display: 'flex', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '1 1 240px', minWidth: 240 }}>
            <Search size={14} color={colors.textMuted} />
            <Input placeholder="Search module…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select value={fCategory} onChange={(e) => setFCategory(e.target.value)} style={{ minWidth: 160 }}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Select value={fMaturity} onChange={(e) => setFMaturity(e.target.value)} style={{ minWidth: 160 }}>
            <option value="">All maturities</option>
            {MATURITIES.map((m) => <option key={m} value={m}>{m}</option>)}
          </Select>
        </Card>
        <Table
          columns={[
            { key: 'module_name', label: 'Module name' },
            { key: 'category', label: 'Category', render: (r) => <Badge tone="info">{r.category || '—'}</Badge> },
            {
              key: 'maturity',
              label: 'Maturity',
              render: (r) => <Badge tone={r.maturity === 'production' ? 'success' : r.maturity === 'partial' ? 'warning' : undefined}>{r.maturity || '—'}</Badge>,
            },
            { key: 'version', label: 'Version' },
            { key: 'deployment_count', label: 'Deployed' },
            {
              key: 'actions',
              label: '',
              render: (r) => (
                <Button size="sm" onClick={() => { setOpenMod(r); setSubmitError(null); }}>
                  <Rocket size={12} /> Deploy
                </Button>
              ),
            },
          ]}
          data={pageRows}
        />
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginTop: spacing.sm, fontSize: 12, color: colors.textMuted,
        }}>
          <span>
            {filtered.length === 0
              ? '0 modules'
              : `${(safePage - 1) * PAGE_SIZE + 1}–${Math.min(safePage * PAGE_SIZE, filtered.length)} of ${filtered.length}`}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
            <Button size="sm" variant="ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage <= 1}>
              <ChevronLeft size={14} /> Prev
            </Button>
            <span>Page {safePage} / {totalPages}</span>
            <Button size="sm" variant="ghost" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}>
              Next <ChevronRight size={14} />
            </Button>
          </div>
        </div>
        </>
        )}
      </Section>

      <Section title="Deployment history">
        <Table
          columns={[
            { key: 'catalog_id', label: 'Module', render: (r) => Array.isArray(r.catalog_id) ? r.catalog_id[1] : r.catalog_id || '—' },
            { key: 'tenant_id', label: 'Tenant', render: (r) => Array.isArray(r.tenant_id) ? r.tenant_id[1] : r.tenant_id || '—' },
            { key: 'deploy_mode', label: 'Mode' },
            {
              key: 'state',
              label: 'State',
              render: (r) => <Badge tone={r.state === 'installed' ? 'success' : r.state === 'failed' ? 'danger' : 'warning'}>{r.state}</Badge>,
            },
            {
              key: 'canary_phase',
              label: 'Canary',
              render: (r) => <Badge tone={r.canary_phase === 'full' ? 'success' : r.canary_phase === 'rolled_back' ? 'danger' : 'warning'}>{r.canary_phase || 'none'}</Badge>,
            },
            { key: 'requested_at', label: 'Requested at' },
          ]}
          data={deployments}
        />
      </Section>

      <Modal open={!!openMod} onClose={() => setOpenMod(null)} title={openMod ? `Deploy: ${openMod.module_name}` : ''}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Tenant
            <Select value={tenantId} onChange={(e) => setTenantId(e.target.value)} style={{ marginTop: 4 }} disabled={tenants.length === 0}>
              {tenants.length === 0 && <option value="">No tenants registered</option>}
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.display_name || t.slug} ({t.slug})
                </option>
              ))}
            </Select>
          </label>
          <label style={{ fontSize: 12, color: colors.textMuted }}>
            Mode
            <Select value={deployMode} onChange={(e) => setDeployMode(e.target.value as any)} style={{ marginTop: 4 }}>
              <option value="install">install</option>
              <option value="upgrade">upgrade</option>
              <option value="uninstall">uninstall</option>
            </Select>
          </label>
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={canary} onChange={(e) => setCanary(e.target.checked)} />
            Canary rollout (10% → 50% → 100%)
          </label>
          {submitError && (
            <div style={{ fontSize: 12, color: '#b91c1c', padding: '8px 12px', background: '#fef2f2', borderRadius: 6 }}>
              {submitError}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: spacing.sm }}>
            <Button variant="ghost" onClick={() => setOpenMod(null)} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={deploy} disabled={submitting || !tenantId}>
              <Rocket size={14} /> {submitting ? 'Deploying…' : 'Deploy'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
