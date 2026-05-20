import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  FileText,
  Lightbulb,
  Server,
  Package,
  Code2,
  MessageSquare,
  LayoutDashboard,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Badge, Button, Card, Tabs } from '../../components/ui';
import { colors, radii, spacing } from '../../tokens';
import { getJourney, listRecommendations } from '../../api';

interface Props {
  journeyId: number;
  onBack: () => void;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: colors.danger,
  high: colors.warning,
  medium: colors.info,
  low: colors.textMuted,
};

export default function JourneyWorkspacePage({ journeyId, onBack }: Props) {
  const [tab, setTab] = useState('overview');
  const [journey, setJourney] = useState<any>({
    id: journeyId,
    name: `J-2026-${String(journeyId).padStart(3, '0')}`,
    partner_name: 'Erajaya Tower B',
    vertical_target: 'residensia',
    stage: 'brd_analyzed',
    mandays_estimate: 42,
    target_go_live: '2026-08-15',
    ba_user_id: [3, 'Andi BA'],
    notes: 'Initial intake from Yulianto (CEO). 5 towers, 1200 units total.',
  });
  const [recs, setRecs] = useState<any[]>([
    { id: 1, name: 'Enable PDP masking on contact module', severity: 'critical', category: 'compliance', estimate_md: 3, status: 'open', rationale: 'PII exposure in default residential contact form.' },
    { id: 2, name: 'Adopt custom_accounting_recurring for monthly IPL', severity: 'high', category: 'finance', estimate_md: 5, status: 'open', rationale: 'CE accounting lacks recurring template; needed for IPL invoicing.' },
    { id: 3, name: 'Add Bupot Unifikasi to vendor payouts', severity: 'medium', category: 'tax', estimate_md: 4, status: 'open', rationale: 'PPh23 withholding required for security contractor.' },
    { id: 4, name: 'Extend HHT scan for asset audit', severity: 'low', category: 'ops', estimate_md: 2, status: 'open' },
  ]);

  useEffect(() => {
    getJourney(journeyId)
      .then((rows) => {
        if (Array.isArray(rows) && rows[0]) setJourney(rows[0]);
      })
      .catch(() => {/* keep mock */});
    listRecommendations(journeyId)
      .then((rows) => {
        if (Array.isArray(rows) && rows.length) setRecs(rows);
      })
      .catch(() => {/* keep mock */});
  }, [journeyId]);

  const severityCounts = useMemo(() => {
    const acc: Record<string, number> = {};
    recs.forEach((r) => (acc[r.severity] = (acc[r.severity] || 0) + 1));
    return Object.entries(acc).map(([k, v]) => ({ name: k, value: v, color: SEVERITY_COLORS[k] || colors.accent }));
  }, [recs]);

  const mandaysByCategory = useMemo(() => {
    const acc: Record<string, number> = {};
    recs.forEach((r) => (acc[r.category] = (acc[r.category] || 0) + (r.estimate_md || 0)));
    return Object.entries(acc).map(([k, v]) => ({ category: k, md: v }));
  }, [recs]);

  return (
    <div style={{ display: 'flex', gap: spacing.lg, minHeight: '100%' }}>
      {/* Sidebar */}
      <div style={{ width: 260, flexShrink: 0 }}>
        <Button variant="ghost" onClick={onBack} style={{ marginBottom: spacing.md }}>
          <ArrowLeft size={14} /> Back to pipeline
        </Button>
        <Card>
          <div style={{ fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 1 }}>
            {journey.name}
          </div>
          <h2 style={{ margin: '4px 0 12px', fontSize: 18 }}>{journey.partner_name}</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
            <Row k="Vertical" v={<Badge tone="info">{journey.vertical_target}</Badge>} />
            <Row k="Stage" v={<Badge tone="warning">{journey.stage}</Badge>} />
            <Row k="Mandays" v={journey.mandays_estimate} />
            <Row k="BA" v={Array.isArray(journey.ba_user_id) ? journey.ba_user_id[1] : '—'} />
            <Row k="Target go-live" v={journey.target_go_live} />
          </div>
        </Card>
        <Card style={{ marginTop: spacing.md }}>
          <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 8 }}>SMART LINKS</div>
          {[
            { i: FileText, label: 'BRD document' },
            { i: Lightbulb, label: 'Recommendations' },
            { i: Server, label: 'VPS' },
            { i: Package, label: 'Tenant DB' },
            { i: Code2, label: 'Dev tasks' },
          ].map((l) => {
            const Icon = l.i;
            return (
              <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', fontSize: 12, color: colors.textMuted, cursor: 'pointer' }}>
                <Icon size={14} /> {l.label}
              </div>
            );
          })}
        </Card>
      </div>

      {/* Main */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: 'overview', label: 'Overview', icon: <LayoutDashboard size={13} /> },
            { key: 'brd', label: 'BRD Analysis', icon: <FileText size={13} /> },
            { key: 'recs', label: 'Recommendations', icon: <Lightbulb size={13} /> },
            { key: 'vps', label: 'VPS', icon: <Server size={13} /> },
            { key: 'modules', label: 'Modules', icon: <Package size={13} /> },
            { key: 'dev', label: 'Dev Cycles', icon: <Code2 size={13} /> },
            { key: 'activity', label: 'Activity', icon: <MessageSquare size={13} /> },
          ]}
        />

        {tab === 'overview' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
            <Card>
              <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 8 }}>Mandays by category</div>
              <div style={{ height: 220 }}>
                <ResponsiveContainer>
                  <BarChart data={mandaysByCategory}>
                    <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
                    <XAxis dataKey="category" stroke={colors.textDim} fontSize={11} />
                    <YAxis stroke={colors.textDim} fontSize={11} />
                    <Tooltip contentStyle={{ background: colors.surfaceMuted, border: `1px solid ${colors.border}` }} />
                    <Bar dataKey="md" fill={colors.accent} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 8 }}>Severity distribution</div>
              <div style={{ height: 220 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={severityCounts} dataKey="value" nameKey="name" outerRadius={80} label>
                      {severityCounts.map((s, i) => (
                        <Cell key={i} fill={s.color} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: colors.surfaceMuted, border: `1px solid ${colors.border}` }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        )}

        {tab === 'brd' && (
          <Card>
            <h3 style={{ marginTop: 0 }}>BRD Analysis</h3>
            <p style={{ color: colors.textMuted, fontSize: 13 }}>
              Last analyzer run: 2026-05-18. {recs.length} recommendations generated.
              <br />
              TODO: render parsed sections and analyzer transcript.
            </p>
          </Card>
        )}

        {tab === 'recs' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
            {recs.map((r) => (
              <Card key={r.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                      <Badge tone={r.severity === 'critical' || r.severity === 'high' ? 'danger' : r.severity === 'medium' ? 'warning' : 'info'}>
                        {r.severity}
                      </Badge>
                      <Badge>{r.category}</Badge>
                      {r.estimate_md != null && <Badge>{r.estimate_md} md</Badge>}
                    </div>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.name}</div>
                    {r.rationale && (
                      <div style={{ fontSize: 12, color: colors.textMuted }}>{r.rationale}</div>
                    )}
                    {r.cross_vertical_impact_json && (
                      <pre
                        style={{
                          background: colors.bg,
                          border: `1px solid ${colors.border}`,
                          borderRadius: radii.sm,
                          padding: 10,
                          fontSize: 11,
                          marginTop: 8,
                          overflow: 'auto',
                        }}
                      >
                        {typeof r.cross_vertical_impact_json === 'string'
                          ? r.cross_vertical_impact_json
                          : JSON.stringify(r.cross_vertical_impact_json, null, 2)}
                      </pre>
                    )}
                  </div>
                  <Badge tone={r.status === 'accepted' ? 'success' : 'warning'}>{r.status || 'open'}</Badge>
                </div>
              </Card>
            ))}
          </div>
        )}

        {tab === 'vps' && (
          <Card>
            <h3 style={{ marginTop: 0 }}>VPS</h3>
            <p style={{ color: colors.textMuted, fontSize: 13 }}>
              No VPS assigned yet. Use the VPS Console to register and bootstrap a node.
            </p>
          </Card>
        )}

        {tab === 'modules' && (
          <Card>
            <h3 style={{ marginTop: 0 }}>Module deployment plan</h3>
            <p style={{ color: colors.textMuted, fontSize: 13 }}>
              Pending — see Module Deploy page for catalog & deployment scheduler.
            </p>
          </Card>
        )}

        {tab === 'dev' && (
          <Card>
            <h3 style={{ marginTop: 0 }}>Dev Cycles linked to this journey</h3>
            <p style={{ color: colors.textMuted, fontSize: 13 }}>
              TODO: filter dev.cycle by journey_id and render summary.
            </p>
          </Card>
        )}

        {tab === 'activity' && (
          <Card>
            <h3 style={{ marginTop: 0 }}>Activity (mail.thread)</h3>
            <p style={{ color: colors.textMuted, fontSize: 13 }}>
              TODO: stream chatter messages via mail.message search_read.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: colors.textDim }}>{k}</span>
      <span>{v}</span>
    </div>
  );
}
