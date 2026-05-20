import { DragEvent, useEffect, useMemo, useState } from 'react';
import { Inbox, Plus, Search, Workflow, X } from 'lucide-react';
import { Badge, Button, Card, Input, Select } from '../../components/ui';
import EmptyState from '../../components/EmptyState';
import ConfigRequiredBanner from '../../components/ConfigRequiredBanner';
import { colors, radii, spacing, stageColors, verticals } from '../../tokens';
import {
  listJourneys, updateJourneyStage,
  listPublicSubmissions, promoteSubmission, rejectSubmission,
} from '../../api';

const STAGES: { key: string; label: string }[] = [
  { key: 'intake', label: 'Intake' },
  { key: 'brd_uploaded', label: 'BRD Uploaded' },
  { key: 'brd_analyzed', label: 'BRD Analyzed' },
  { key: 'go_no_go', label: 'Go / No-Go' },
  { key: 'vps_assigned', label: 'VPS Assigned' },
  { key: 'provisioning', label: 'Provisioning' },
  { key: 'modules_deploying', label: 'Modules Deploying' },
  { key: 'uat', label: 'UAT' },
  { key: 'go_live', label: 'Go Live' },
  { key: 'closed', label: 'Closed' },
];

interface Journey {
  id: number;
  name: string;
  partner_name: string;
  vertical_target: string;
  stage: string;
  mandays_estimate?: number;
  ba_user_id?: [number, string] | false;
  target_go_live?: string;
  progress_pct?: number;
}

interface Props {
  onOpenJourney: (id: number) => void;
  onNewIntake: () => void;
}

export default function OnboardingPipelinePage({ onOpenJourney, onNewIntake }: Props) {
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [filterBa, setFilterBa] = useState('');
  const [filterVertical, setFilterVertical] = useState('');
  const [search, setSearch] = useState('');
  const [dragId, setDragId] = useState<number | null>(null);
  const [apiError, setApiError] = useState<{ message: string; configRequired: boolean } | null>(null);
  const [loaded, setLoaded] = useState(false);

  function refresh() {
    Promise.all([listJourneys(), listPublicSubmissions('submitted')])
      .then(([j, s]) => {
        if (Array.isArray(j)) setJourneys(j as any);
        if (Array.isArray(s)) setSubmissions(s);
        setLoaded(true);
      })
      .catch((err: any) => {
        const msg = err?.detail || err?.message || String(err);
        const configRequired =
          /turnstile|api key|webhook secret|vault|prometheus|ANTHROPIC|requires config/i.test(msg);
        setApiError({ message: msg, configRequired });
        setLoaded(true);
      });
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onPromote(id: number) {
    setBusyId(id);
    try {
      const res = await promoteSubmission(id);
      refresh();
      // action_promote_to_journey returns an ir.actions.act_window with res_id
      const jid = res?.res_id;
      if (jid) setTimeout(() => onOpenJourney(jid), 200);
    } catch (e: any) {
      alert('Promote failed: ' + (e?.detail || e?.message || e));
    } finally {
      setBusyId(null);
    }
  }

  async function onReject(id: number) {
    if (!confirm('Reject this submission? It will be hidden from the inbox.')) return;
    setBusyId(id);
    try {
      await rejectSubmission(id);
      refresh();
    } finally {
      setBusyId(null);
    }
  }

  function parsePayload(raw: string) {
    try { return JSON.parse(raw || '{}'); } catch { return {}; }
  }

  const filtered = useMemo(() => {
    return journeys.filter((j) => {
      if (filterVertical && j.vertical_target !== filterVertical) return false;
      if (filterBa) {
        const ba = Array.isArray(j.ba_user_id) ? j.ba_user_id[1] : '';
        if (!ba.toLowerCase().includes(filterBa.toLowerCase())) return false;
      }
      if (search && !j.partner_name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [journeys, filterBa, filterVertical, search]);

  function onDrop(stage: string) {
    if (dragId == null) return;
    const id = dragId;
    setDragId(null);
    setJourneys((prev) => prev.map((j) => (j.id === id ? { ...j, stage } : j)));
    updateJourneyStage(id, stage).catch(() => {
      // Roll back UI silently — server will be retried.
      // TODO: surface toast + revert.
    });
  }

  function onDragStart(e: DragEvent, id: number) {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
  }

  const showEmptyState = loaded && journeys.length === 0;

  return (
    <div>
      {apiError?.configRequired && (
        <ConfigRequiredBanner
          feature="Onboarding pipeline"
          hint={apiError.message}
        />
      )}
      {submissions.length > 0 && (
        <Card style={{ marginBottom: spacing.md, padding: spacing.md, background: '#FEF6E6', border: `1px solid #F5D78E` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: spacing.sm }}>
            <Inbox size={16} color="#92400E" />
            <strong style={{ color: '#92400E', fontSize: 13 }}>
              Public Inbox — {submissions.length} new intake submission{submissions.length === 1 ? '' : 's'} awaiting promotion
            </strong>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {submissions.map((s) => {
              const p = parsePayload(s.raw_payload_json);
              const fileCount = (p.brd_file_base64s || []).length;
              const moduleCount = (p.modules_wishlist || []).length;
              return (
                <div key={s.id} style={{
                  background: '#fff', borderRadius: radii.md, padding: spacing.sm,
                  border: `1px solid ${colors.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>
                      {p.company_name || 'Untitled submission'}
                    </div>
                    <div style={{ fontSize: 11, color: colors.muted, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      <span>Vertical: <strong>{p.vertical_target || '—'}</strong></span>
                      <span>{p.contact_email || '—'}</span>
                      <span>{moduleCount} module{moduleCount === 1 ? '' : 's'} requested</span>
                      <span>{fileCount} BRD file{fileCount === 1 ? '' : 's'}</span>
                      <span>{new Date(s.submitted_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button
                      variant="ghost"
                      onClick={() => onReject(s.id)}
                      disabled={busyId === s.id}
                      style={{ color: colors.muted }}
                    >
                      <X size={12} /> Reject
                    </Button>
                    <Button
                      onClick={() => onPromote(s.id)}
                      disabled={busyId === s.id}
                    >
                      {busyId === s.id ? 'Promoting…' : 'Promote to Journey →'}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card style={{ marginBottom: spacing.md, display: 'flex', gap: spacing.sm, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '1 1 220px' }}>
          <Search size={14} color={colors.textMuted} />
          <Input placeholder="Search partner…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Input placeholder="Filter BA…" value={filterBa} onChange={(e) => setFilterBa(e.target.value)} style={{ width: 160 }} />
        <Select value={filterVertical} onChange={(e) => setFilterVertical(e.target.value)}>
          <option value="">All verticals</option>
          {verticals.map((v) => (
            <option key={v.value} value={v.value}>
              {v.label}
            </option>
          ))}
        </Select>
        <Button onClick={onNewIntake}>
          <Plus size={14} /> New intake
        </Button>
      </Card>

      {showEmptyState ? (
        <EmptyState
          icon={<Workflow size={48} />}
          title="No onboarding journeys yet"
          description="Submit your first BRD intake to start tracking a customer onboarding lifecycle."
          action={
            <Button onClick={onNewIntake}>
              <Plus size={14} /> New Intake
            </Button>
          }
        />
      ) : (
      <div
        style={{
          display: 'flex',
          gap: spacing.md,
          overflowX: 'auto',
          paddingBottom: spacing.md,
        }}
      >
        {STAGES.map((stage) => {
          const items = filtered.filter((j) => j.stage === stage.key);
          return (
            <div
              key={stage.key}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => onDrop(stage.key)}
              style={{
                minWidth: 260,
                background: colors.surface,
                border: `1px solid ${colors.border}`,
                borderTop: `3px solid ${stageColors[stage.key] || colors.accent}`,
                borderRadius: radii.md,
                padding: spacing.sm,
                display: 'flex',
                flexDirection: 'column',
                gap: spacing.sm,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 6px' }}>
                <span style={{ fontWeight: 600, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  {stage.label}
                </span>
                <Badge>{items.length}</Badge>
              </div>
              {items.map((j) => (
                <div
                  key={j.id}
                  draggable
                  onDragStart={(e) => onDragStart(e, j.id)}
                  onClick={() => onOpenJourney(j.id)}
                  style={{
                    background: colors.surfaceMuted,
                    border: `1px solid ${colors.border}`,
                    borderRadius: radii.md,
                    padding: spacing.sm,
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 2 }}>{j.partner_name}</div>
                  <div style={{ color: colors.textMuted, marginBottom: 6 }}>{j.name}</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
                    <Badge tone="info">{j.vertical_target}</Badge>
                    {j.mandays_estimate != null && <Badge>{j.mandays_estimate} md</Badge>}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, color: colors.textDim, fontSize: 11 }}>
                    <span>BA: {Array.isArray(j.ba_user_id) ? j.ba_user_id[1] : '—'}</span>
                    <span>{j.target_go_live || ''}</span>
                  </div>
                </div>
              ))}
              {items.length === 0 && (
                <div style={{ color: colors.textDim, fontSize: 11, textAlign: 'center', padding: spacing.md }}>
                  Drop here
                </div>
              )}
            </div>
          );
        })}
      </div>
      )}
    </div>
  );
}
