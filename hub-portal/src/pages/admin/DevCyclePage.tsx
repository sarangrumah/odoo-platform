import { useEffect, useState } from 'react';
import { Code2 } from 'lucide-react';
import { Badge, Card, Modal, Section, Table } from '../../components/ui';
import EmptyState from '../../components/EmptyState';
import ConfigRequiredBanner from '../../components/ConfigRequiredBanner';
import { colors, radii, spacing } from '../../tokens';
import { listDevCyclePrs, listDevCycles } from '../../api';

const STATES = [
  { key: 'backlog', label: 'Backlog' },
  { key: 'in_dev', label: 'In Dev' },
  { key: 'code_review', label: 'Code Review' },
  { key: 'qa', label: 'QA' },
  { key: 'uat', label: 'UAT' },
  { key: 'deployed', label: 'Deployed' },
  { key: 'done', label: 'Done' },
];

export default function DevCyclePage() {
  const [cycles, setCycles] = useState<any[]>([]);
  const [open, setOpen] = useState<any | null>(null);
  const [prs, setPrs] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [apiError, setApiError] = useState<{ message: string; configRequired: boolean } | null>(null);

  useEffect(() => {
    listDevCycles()
      .then((r) => {
        if (Array.isArray(r)) setCycles(r);
        setLoaded(true);
      })
      .catch((err: any) => {
        const msg = err?.detail || err?.message || String(err);
        const configRequired =
          /turnstile|api key|webhook secret|vault|prometheus|ANTHROPIC|requires config/i.test(msg);
        setApiError({ message: msg, configRequired });
        setLoaded(true);
      });
  }, []);

  useEffect(() => {
    if (!open) return;
    listDevCyclePrs(open.id)
      .then((r) => setPrs(Array.isArray(r) ? r : []))
      .catch(() => setPrs([]));
  }, [open]);

  const showEmpty = loaded && cycles.length === 0;

  return (
    <Section title="Dev Cycles" description="Tasks → PR → CI → deploy lifecycle">
      {apiError?.configRequired && (
        <ConfigRequiredBanner feature="Dev cycles" hint={apiError.message} />
      )}
      {showEmpty ? (
        <EmptyState
          icon={<Code2 size={48} />}
          title="No dev cycles yet"
          description="Create a dev cycle from a BRD recommendation, or wait for GitHub/GitLab webhook events."
        />
      ) : (
      <div style={{ display: 'flex', gap: spacing.md, overflowX: 'auto', paddingBottom: spacing.md }}>
        {STATES.map((s) => {
          const items = cycles.filter((c) => c.state === s.key);
          return (
            <div
              key={s.key}
              style={{
                minWidth: 260,
                background: colors.surface,
                border: `1px solid ${colors.border}`,
                borderRadius: radii.md,
                padding: spacing.sm,
                display: 'flex',
                flexDirection: 'column',
                gap: spacing.sm,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 6px' }}>
                <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  {s.label}
                </span>
                <Badge>{items.length}</Badge>
              </div>
              {items.map((c) => (
                <div
                  key={c.id}
                  onClick={() => setOpen(c)}
                  style={{
                    background: colors.surfaceMuted,
                    border: `1px solid ${colors.border}`,
                    borderRadius: radii.md,
                    padding: spacing.sm,
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>{c.name}</div>
                  <div style={{ color: colors.textMuted, marginBottom: 6 }}>
                    {Array.isArray(c.assignee_id) ? c.assignee_id[1] : 'Unassigned'}
                    {c.estimate_md != null && c.estimate_md > 0 ? ` · ${c.estimate_md}md` : ''}
                  </div>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {c.env_progress && <Badge tone="info">env: {c.env_progress}</Badge>}
                    {c.pr_count > 0 && <Badge>PRs: {c.pr_count}</Badge>}
                    {c.deployment_count > 0 && <Badge tone="success">deploys: {c.deployment_count}</Badge>}
                  </div>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? open.name : ''} width={760}>
        {open && (
          <div>
            <Card style={{ marginBottom: spacing.md }}>
              <div style={{ fontSize: 13 }}>
                State: <Badge>{open.state}</Badge>
                {open.estimate_md != null && open.estimate_md > 0 && ` · Estimate: ${open.estimate_md}md`}
                {open.branch_name && ` · Branch: `}{open.branch_name && <code style={{ fontSize: 11 }}>{open.branch_name}</code>}
              </div>
            </Card>
            <h4 style={{ margin: '0 0 8px' }}>Pull requests</h4>
            <Table
              columns={[
                {
                  key: 'pr_url',
                  label: 'PR',
                  render: (r) => r.pr_url ? <a href={r.pr_url} target="_blank" rel="noreferrer">{r.provider} #{r.pr_number}</a> : `${r.provider || ''} #${r.pr_number || ''}`,
                },
                { key: 'state', label: 'State', render: (r) => <Badge tone={r.state === 'merged' ? 'success' : 'warning'}>{r.state}</Badge> },
                { key: 'ci_status', label: 'CI', render: (r) => <Badge tone={r.ci_status === 'success' ? 'success' : r.ci_status === 'failure' || r.ci_status === 'error' ? 'danger' : 'info'}>{r.ci_status || '—'}</Badge> },
                { key: 'merged_at', label: 'Merged at' },
              ]}
              data={prs}
            />
            <h4 style={{ margin: '16px 0 8px' }}>Webhook log</h4>
            <div
              style={{
                background: colors.bg,
                border: `1px solid ${colors.border}`,
                borderRadius: 8,
                padding: spacing.md,
                fontSize: 11,
                color: colors.textMuted,
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              TODO: hook to github webhook events stream.
            </div>
          </div>
        )}
      </Modal>
    </Section>
  );
}
