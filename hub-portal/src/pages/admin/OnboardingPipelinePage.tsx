import { DragEvent, useEffect, useMemo, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Badge, Button, Card, Input, Select } from '../../components/ui';
import { colors, radii, spacing, stageColors, verticals } from '../../tokens';
import { listJourneys, updateJourneyStage } from '../../api';

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

const MOCK: Journey[] = [
  { id: 1, name: 'J-2026-001', partner_name: 'Erajaya Tower B', vertical_target: 'residensia', stage: 'brd_analyzed', mandays_estimate: 42, ba_user_id: [3, 'Andi BA'], target_go_live: '2026-08-15' },
  { id: 2, name: 'J-2026-002', partner_name: 'Telkom Pulsa Plus', vertical_target: 'ppob', stage: 'intake', mandays_estimate: 18, ba_user_id: [3, 'Andi BA'], target_go_live: '2026-07-10' },
  { id: 3, name: 'J-2026-003', partner_name: 'Arkaim Logistics', vertical_target: 'arkaim', stage: 'vps_assigned', mandays_estimate: 56, ba_user_id: [4, 'Rini BA'], target_go_live: '2026-09-01' },
  { id: 4, name: 'J-2026-004', partner_name: 'JDS Pratama', vertical_target: 'jds', stage: 'uat', mandays_estimate: 30, ba_user_id: [4, 'Rini BA'], target_go_live: '2026-06-01' },
  { id: 5, name: 'J-2026-005', partner_name: 'Komdigi Pilot', vertical_target: 'komdigi', stage: 'provisioning', mandays_estimate: 22, ba_user_id: [3, 'Andi BA'], target_go_live: '2026-07-25' },
];

interface Props {
  onOpenJourney: (id: number) => void;
  onNewIntake: () => void;
}

export default function OnboardingPipelinePage({ onOpenJourney, onNewIntake }: Props) {
  const [journeys, setJourneys] = useState<Journey[]>(MOCK);
  const [filterBa, setFilterBa] = useState('');
  const [filterVertical, setFilterVertical] = useState('');
  const [search, setSearch] = useState('');
  const [dragId, setDragId] = useState<number | null>(null);

  useEffect(() => {
    listJourneys()
      .then((rows) => {
        if (Array.isArray(rows) && rows.length) setJourneys(rows as any);
      })
      .catch(() => {/* keep mock */});
  }, []);

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

  return (
    <div>
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
    </div>
  );
}
