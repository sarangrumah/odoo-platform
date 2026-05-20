import { useEffect, useState } from 'react';
import { Badge, Card, Modal, Section, Table } from '../../components/ui';
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

const MOCK = [
  { id: 1, name: 'DC-001 Add PDP masking to residensia', state: 'in_dev', assignee_id: [3, 'Dimas Dev'], estimate_md: 3, pr_count: 2, open_pr_count: 1, merged_pr_count: 1, ci_status: 'passing' },
  { id: 2, name: 'DC-002 Coretax bupot vendor export', state: 'code_review', assignee_id: [4, 'Lina Dev'], estimate_md: 5, pr_count: 1, open_pr_count: 1, merged_pr_count: 0, ci_status: 'passing' },
  { id: 3, name: 'DC-003 HHT scan UI refresh', state: 'qa', assignee_id: [3, 'Dimas Dev'], estimate_md: 2, pr_count: 3, open_pr_count: 0, merged_pr_count: 3, ci_status: 'failing' },
  { id: 4, name: 'DC-004 Recurring invoice template', state: 'backlog', assignee_id: false, estimate_md: 8, pr_count: 0, open_pr_count: 0, merged_pr_count: 0, ci_status: '—' },
  { id: 5, name: 'DC-005 BRD analyzer prompt v2', state: 'deployed', assignee_id: [5, 'Aulia Dev'], estimate_md: 4, pr_count: 2, open_pr_count: 0, merged_pr_count: 2, ci_status: 'passing' },
];

export default function DevCyclePage() {
  const [cycles, setCycles] = useState<any[]>(MOCK);
  const [open, setOpen] = useState<any | null>(null);
  const [prs, setPrs] = useState<any[]>([]);

  useEffect(() => {
    listDevCycles().then((r) => Array.isArray(r) && r.length && setCycles(r)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    listDevCyclePrs(open.id)
      .then((r) => setPrs(Array.isArray(r) ? r : []))
      .catch(() =>
        setPrs([
          { id: 1, name: 'PR #142 add masking rules', url: '#', state: 'merged', ci_status: 'passing', merged_at: '2026-05-19' },
          { id: 2, name: 'PR #143 refactor handler', url: '#', state: 'open', ci_status: 'passing' },
        ]),
      );
  }, [open]);

  return (
    <Section title="Dev Cycles" description="Tasks → PR → CI → deploy lifecycle">
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
                    {Array.isArray(c.assignee_id) ? c.assignee_id[1] : 'Unassigned'} · {c.estimate_md}md
                  </div>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {c.open_pr_count > 0 && <Badge tone="warning">open {c.open_pr_count}</Badge>}
                    {c.merged_pr_count > 0 && <Badge tone="success">merged {c.merged_pr_count}</Badge>}
                    <Badge tone={c.ci_status === 'failing' ? 'danger' : c.ci_status === 'passing' ? 'success' : 'info'}>
                      CI: {c.ci_status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? open.name : ''} width={760}>
        {open && (
          <div>
            <Card style={{ marginBottom: spacing.md }}>
              <div style={{ fontSize: 13 }}>
                State: <Badge>{open.state}</Badge> · Estimate: {open.estimate_md}md
              </div>
            </Card>
            <h4 style={{ margin: '0 0 8px' }}>Pull requests</h4>
            <Table
              columns={[
                { key: 'name', label: 'PR' },
                { key: 'state', label: 'State', render: (r) => <Badge tone={r.state === 'merged' ? 'success' : 'warning'}>{r.state}</Badge> },
                { key: 'ci_status', label: 'CI', render: (r) => <Badge tone={r.ci_status === 'passing' ? 'success' : 'danger'}>{r.ci_status}</Badge> },
                { key: 'merged_at', label: 'Merged at' },
              ]}
              rows={prs}
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
