import React, { useEffect, useMemo, useState } from 'react';
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
import { Badge, Button, Card, Spinner, Tabs } from '../../components/ui';
import EmptyState from '../../components/EmptyState';
import ConfigRequiredBanner from '../../components/ConfigRequiredBanner';
import { colors, radii, spacing } from '../../tokens';
import { getJourney, listRecommendations, listBrdDocuments, runBrdExtract, runBrdAnalyze, runBrdAnalyzeAsync, listCapabilityEntries, rejectRecommendationAsLesson } from '../../api';

function partnerName(j: any): string {
  return Array.isArray(j?.partner_id) ? j.partner_id[1] : (j?.name || '—');
}
function baName(j: any): string {
  return Array.isArray(j?.ba_id) ? j.ba_id[1] : '—';
}
function readJsonField(raw: any): any {
  if (!raw) return {};
  if (typeof raw !== 'string') return raw;
  try { return JSON.parse(raw); } catch { return {}; }
}

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

const TYPE_TONE: Record<string, 'danger' | 'warning' | 'success' | 'info'> = {
  new: 'danger',
  extend: 'warning',
  reuse: 'success',
};
const TYPE_LABEL: Record<string, string> = {
  new: 'NEW MODULE',
  extend: 'EXTEND',
  reuse: 'REUSE',
};

// Render a many2one tuple [id, label] OR an array of such tuples.
function m2oLabel(v: any): string {
  if (Array.isArray(v) && v.length === 2 && typeof v[1] === 'string') return v[1];
  return String(v);
}

export default function JourneyWorkspacePage({ journeyId, onBack }: Props) {
  const [tab, setTab] = useState('overview');
  const [journey, setJourney] = useState<any>(null);
  const [recs, setRecs] = useState<any[]>([]);
  const [brds, setBrds] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [apiError, setApiError] = useState<{ message: string; configRequired: boolean } | null>(null);
  const [busyBrd, setBusyBrd] = useState<number | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<any | null>(null);
  const [capabilityEntries, setCapabilityEntries] = useState<any[]>([]);

  function refresh() {
    if (journeyId == null) {
      setLoaded(true);
      return;
    }
    const detectConfig = (msg: string) =>
      /turnstile|api key|webhook secret|vault|prometheus|ANTHROPIC|requires config/i.test(msg);
    Promise.all([
      getJourney(journeyId).catch((e: any) => {
        const msg = e?.detail || e?.message || String(e);
        setApiError({ message: msg, configRequired: detectConfig(msg) });
        return null;
      }),
      listRecommendations(journeyId).catch(() => []),
      listBrdDocuments(journeyId).catch(() => []),
    ]).then(([j, r, b]) => {
      if (Array.isArray(j) && j[0]) setJourney(j[0]);
      if (Array.isArray(r)) setRecs(r);
      if (Array.isArray(b)) setBrds(b);
      setLoaded(true);
    });
  }

  useEffect(() => { refresh(); }, [journeyId]);

  function openReject(rec: any) {
    setRejectTarget(rec);
    if (capabilityEntries.length === 0) {
      listCapabilityEntries().then((rows) => setCapabilityEntries(rows || [])).catch(() => {});
    }
  }

  async function doExtract(id: number) {
    setBusyBrd(id); setActionMsg('Extract running…');
    try { await runBrdExtract(id); setActionMsg('Extract completed. State now extracted.'); refresh(); }
    catch (e: any) { setActionMsg('Extract failed: ' + (e?.detail || e?.message || e)); }
    finally { setBusyBrd(null); }
  }
  async function doAnalyze(id: number) {
    setBusyBrd(id);
    setActionMsg('AI analysis dispatched — polling for completion (up to ~10 min).');
    try {
      await runBrdAnalyzeAsync(id);
      // Poll state every 5s for up to 10 min. queue_job worker flips state
      // 'analyzing' → 'analyzed' (or back to 'extracted' on hard failure).
      const deadline = Date.now() + 10 * 60 * 1000;
      let final: any = null;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 5000));
        const fresh = await listBrdDocuments(journeyId!);
        const me = (fresh || []).find((x: any) => x.id === id);
        if (!me) continue;
        if (me.state === 'analyzed' || me.state === 'extracted') {
          final = me;
          break;
        }
      }
      if (final && final.state === 'analyzed') {
        const secs = final.last_ai_section_count || 0;
        const recs = final.last_ai_recommendation_count || 0;
        setActionMsg(
          recs > 0
            ? `AI analysis complete: ${secs} sections analyzed, ${recs} recommendations created. Open the Recommendations tab.`
            : `AI ran but returned ${secs} sections / ${recs} recommendations. See the diagnostic dump on the BRD card below.`,
        );
      } else if (final && final.state === 'extracted') {
        setActionMsg('AI analysis failed on the worker — BRD reverted to extracted. Check the queue_job log.');
      } else {
        setActionMsg('AI analysis still running on the worker. Refresh the page later to see results.');
      }
      refresh();
    } catch (e: any) {
      setActionMsg('Analyze failed: ' + (e?.detail || e?.message || e));
    } finally {
      setBusyBrd(null);
    }
  }

  // Kept for power users / debugging: synchronous variant retained but unused
  // by default. Reference via window for ad-hoc invocation if needed.
  void runBrdAnalyze;

  const severityCounts = useMemo(() => {
    const acc: Record<string, number> = {};
    recs.forEach((r) => (acc[r.severity] = (acc[r.severity] || 0) + 1));
    return Object.entries(acc).map(([k, v]) => ({ name: k, value: v, color: SEVERITY_COLORS[k] || colors.accent }));
  }, [recs]);

  const mandaysByCategory = useMemo(() => {
    const acc: Record<string, number> = {};
    recs.forEach((r) => {
      const k = r.severity || 'unknown';
      acc[k] = (acc[k] || 0) + (r.estimated_md || 0);
    });
    return Object.entries(acc).map(([k, v]) => ({ category: k, md: v }));
  }, [recs]);

  if (!loaded || journey === null) {
    if (!loaded) {
      return (
        <div style={{ padding: spacing.lg, color: colors.textMuted, fontSize: 13 }}>Loading…</div>
      );
    }
    return (
      <div>
        {apiError?.configRequired && (
          <ConfigRequiredBanner feature="Journey workspace" hint={apiError.message} />
        )}
        <EmptyState
          title="No journey selected"
          description="Pick a journey from the onboarding pipeline to view its workspace."
          action={
            <Button onClick={onBack}>
              <ArrowLeft size={14} /> Back to Pipeline
            </Button>
          }
        />
      </div>
    );
  }

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
          <h2 style={{ margin: '4px 0 12px', fontSize: 18 }}>{partnerName(journey)}</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
            {(() => {
              const cp = readJsonField(journey.company_profile_json);
              return <Row k="Vertical" v={<Badge tone="info">{cp.vertical_target || '—'}</Badge>} />;
            })()}
            <Row k="Stage" v={<Badge tone="warning">{journey.stage}</Badge>} />
            <Row k="Mandays" v={journey.mandays_estimate || 0} />
            <Row k="BA" v={baName(journey)} />
            <Row k="Target go-live" v={journey.target_go_live || '—'} />
          </div>
        </Card>
        <Card style={{ marginTop: spacing.md }}>
          <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 8 }}>SMART LINKS</div>
          {[
            { i: FileText, label: 'BRD document', tab: 'brd' },
            { i: Lightbulb, label: 'Recommendations', tab: 'recs' },
            { i: Server, label: 'VPS', tab: 'vps' },
            { i: Package, label: 'Tenant DB', tab: 'modules' },
            { i: Code2, label: 'Dev tasks', tab: 'dev' },
          ].map((l) => {
            const Icon = l.i;
            const active = tab === l.tab;
            return (
              <div
                key={l.label}
                onClick={() => setTab(l.tab)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 8px', margin: '2px -8px',
                  borderRadius: radii.sm, fontSize: 12,
                  color: active ? colors.text : colors.textMuted,
                  background: active ? colors.surfaceMuted : 'transparent',
                  cursor: 'pointer',
                }}
              >
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
          recs.length === 0 ? (
            <Card>
              <h3 style={{ marginTop: 0, marginBottom: 8 }}>Overview</h3>
              <p style={{ color: colors.textMuted, fontSize: 13, marginBottom: 16 }}>
                {brds.length === 0
                  ? 'No BRD documents attached yet. Upload a BRD via the intake wizard, or attach one in the BRD Analysis tab below.'
                  : `${brds.length} BRD document${brds.length === 1 ? '' : 's'} attached. Open the BRD Analysis tab to extract sections and run AI analysis — recommendations will then appear here.`}
              </p>
              {(() => {
                const cp = readJsonField(journey.company_profile_json);
                if (Object.keys(cp).length === 0) return null;
                return (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
                    <Row k="Company" v={cp.company_name || '—'} />
                    <Row k="Email" v={cp.contact_email || '—'} />
                    <Row k="Phone" v={cp.contact_phone || '—'} />
                    <Row k="NPWP" v={cp.npwp || '—'} />
                    <Row k="Bank" v={cp.bank_name ? `${cp.bank_name} · ${cp.bank_account || '—'}` : '—'} />
                    <Row k="Modules requested" v={(cp.modules_wishlist || []).length} />
                  </div>
                );
              })()}
            </Card>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
              <Card>
                <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 8 }}>Mandays by severity</div>
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
          )
        )}

        {tab === 'brd' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
            {actionMsg && (
              <div style={{
                padding: 12, borderRadius: radii.md,
                background: actionMsg.startsWith('Extract failed') || actionMsg.startsWith('Analyze failed') ? '#FEE2E2' : '#D1FAE5',
                color: actionMsg.startsWith('Extract failed') || actionMsg.startsWith('Analyze failed') ? '#991B1B' : '#065F46',
                fontSize: 13,
              }}>
                {actionMsg}
              </div>
            )}
            {brds.length === 0 ? (
              <Card>
                <h3 style={{ marginTop: 0 }}>BRD Analysis</h3>
                <p style={{ color: colors.textMuted, fontSize: 13 }}>
                  No BRD documents attached to this journey yet. Upload BRD files via the intake wizard (and they'll auto-attach on Promote to Journey), or add them via Odoo's BRD Analyzer menu.
                </p>
              </Card>
            ) : brds.map((b) => (
              <Card key={b.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{b.name || b.document_filename || `BRD #${b.id}`}</div>
                    <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 8 }}>
                      {b.reference && <span style={{ marginRight: 12 }}>Ref: <code>{b.reference}</code></span>}
                      {b.document_filename && <span style={{ marginRight: 12 }}>File: {b.document_filename}</span>}
                      {b.document_mime && <span>{b.document_mime}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                      <Badge tone={b.state === 'analyzed' || b.state === 'approved' ? 'success' : b.state === 'extracted' || b.state === 'reviewed' ? 'info' : 'warning'}>
                        {b.state || 'draft'}
                      </Badge>
                      {b.overall_fit_pct != null && b.overall_fit_pct > 0 && (
                        <Badge tone={b.overall_fit_pct >= 70 ? 'success' : b.overall_fit_pct >= 40 ? 'warning' : 'danger'}>
                          fit: {b.overall_fit_pct}%
                        </Badge>
                      )}
                      {b.severity_summary && <Badge>{b.severity_summary}</Badge>}
                      {b.business_domain && <Badge>{b.business_domain}</Badge>}
                      {b.last_ai_at && (
                        <Badge tone="info">
                          last run: {new Date(b.last_ai_at).toLocaleString()} ·
                          {' '}{b.last_ai_section_count || 0} secs ·
                          {' '}{b.last_ai_recommendation_count || 0} recs
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'stretch', minWidth: 170 }}>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busyBrd === b.id}
                      onClick={() => doExtract(b.id)}
                    >
                      {busyBrd === b.id ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          <Spinner size={10} /> Extracting…
                        </span>
                      ) : '1. Extract'}
                    </Button>
                    <Button
                      size="sm"
                      disabled={busyBrd === b.id || b.state === 'draft'}
                      onClick={() => doAnalyze(b.id)}
                      title={b.state === 'draft' ? 'Run Extract first' : 'Run AI analysis'}
                    >
                      {busyBrd === b.id ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          <Spinner size={10} /> AI analyzing…
                        </span>
                      ) : '2. Run AI Analyze'}
                    </Button>
                  </div>
                </div>

                {/* Diagnostic dump: visible after Analyze runs. Lets BA see exactly
                    what came back from the model when recommendations = 0. */}
                {b.last_ai_raw && (
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: colors.textMuted }}>
                      Raw AI response (last run · click to expand · for diagnosis)
                    </summary>
                    <pre style={{
                      background: '#0b1220', color: '#e6edf7',
                      padding: 12, borderRadius: 6, marginTop: 8,
                      fontSize: 11, lineHeight: 1.4, maxHeight: 360,
                      overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    }}>
                      {String(b.last_ai_raw).slice(0, 12000)}
                      {String(b.last_ai_raw).length > 12000 ? '\n…(truncated, full text in Odoo brd.document.last_ai_raw)' : ''}
                    </pre>
                  </details>
                )}
              </Card>
            ))}
          </div>
        )}

        {tab === 'recs' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
            {/* Summary header: type counts, BRD fit & coverage. Tells the analyst
                at a glance how many recs are NEW vs reuse, and how much of the
                BRD is already covered by hub modules. */}
            {recs.length > 0 && (
              <Card>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
                  <div style={{ fontSize: 12, color: colors.textMuted }}>Total: <b style={{ color: colors.text }}>{recs.length}</b></div>
                  {(['new', 'extend', 'reuse'] as const).map((t) => {
                    const n = recs.filter((r) => r.recommendation_type === t).length;
                    if (n === 0) return null;
                    return (
                      <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                        <Badge tone={TYPE_TONE[t]}>{TYPE_LABEL[t]}</Badge>
                        <b style={{ color: colors.text }}>{n}</b>
                      </div>
                    );
                  })}
                  {brds.map((b) => {
                    if (b.overall_fit_pct == null && !b.severity_summary) return null;
                    return (
                      <div key={b.id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: colors.textMuted }}>
                        <span>BRD #{b.id}:</span>
                        {b.overall_fit_pct != null && (
                          <Badge
                            tone={b.overall_fit_pct >= 70 ? 'success' : b.overall_fit_pct >= 40 ? 'warning' : 'danger'}
                            title="Weighted average of per-section fit_score (must_have=3, should_have=2, nice_to_have=1)."
                          >
                            fit: {b.overall_fit_pct}%
                          </Badge>
                        )}
                        {b.severity_summary && (
                          <Badge title="Per-section gap_status: covered | partial | missing | unclear.">
                            {b.severity_summary}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}
            {recs.map((r) => (
              <Card key={r.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                      {r.recommendation_type && (
                        <Badge tone={TYPE_TONE[r.recommendation_type] || 'info'}>
                          {TYPE_LABEL[r.recommendation_type] || r.recommendation_type}
                        </Badge>
                      )}
                      <Badge tone={r.severity === 'must_have' ? 'danger' : r.severity === 'should_have' ? 'warning' : 'info'}>
                        {r.severity || 'n/a'}
                      </Badge>
                      {r.compat_strategy && <Badge>{r.compat_strategy}</Badge>}
                      {r.estimated_md != null && r.estimated_md > 0 && <Badge>{r.estimated_md} md</Badge>}
                      {r.breaking_change && <Badge tone="danger">breaking</Badge>}
                      {r.impact_severity && <Badge tone={r.impact_severity === 'critical' || r.impact_severity === 'high' ? 'danger' : 'warning'}>impact: {r.impact_severity}</Badge>}
                    </div>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.name}</div>
                    {r.scope && (
                      <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>{r.scope}</div>
                    )}
                    {r.justification && (
                      <div style={{ fontSize: 12, color: colors.textMuted, fontStyle: 'italic' }}>{r.justification}</div>
                    )}
                    {(Array.isArray(r.depends_on_module_ids) && r.depends_on_module_ids.length > 0) && (
                      <div style={{ marginTop: 8, fontSize: 11, color: colors.textMuted }}>
                        <span style={{ marginRight: 6 }}>Depends on existing:</span>
                        {r.depends_on_module_ids.map((m: any) => (
                          <Badge key={Array.isArray(m) ? m[0] : m} tone="success">{m2oLabel(m)}</Badge>
                        ))}
                      </div>
                    )}
                    {(Array.isArray(r.impact_module_ids) && r.impact_module_ids.length > 0) && (
                      <div style={{ marginTop: 4, fontSize: 11, color: colors.textMuted }}>
                        <span style={{ marginRight: 6 }}>Impacts:</span>
                        {r.impact_module_ids.map((m: any) => (
                          <Badge key={Array.isArray(m) ? m[0] : m} tone="warning">{m2oLabel(m)}</Badge>
                        ))}
                      </div>
                    )}
                    {(Array.isArray(r.depends_on_proposed_ids) && r.depends_on_proposed_ids.length > 0) && (
                      <div style={{ marginTop: 4, fontSize: 11, color: colors.textMuted }}>
                        <span style={{ marginRight: 6 }}>Depends on proposed:</span>
                        {r.depends_on_proposed_ids.map((m: any) => (
                          <Badge key={Array.isArray(m) ? m[0] : m}>{m2oLabel(m)}</Badge>
                        ))}
                      </div>
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
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end', minWidth: 140 }}>
                    <Badge tone={r.state === 'approved' ? 'success' : r.state === 'canceled' ? 'danger' : 'warning'}>{r.state || 'draft'}</Badge>
                    {r.state !== 'canceled' && r.state !== 'built' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openReject(r)}
                        title="Mark this recommendation as wrong and save the correction as a lesson the AI will read on future runs."
                      >
                        Reject &amp; save as lesson
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {rejectTarget && (
          <RejectAsLessonModal
            recommendation={rejectTarget}
            capabilityEntries={capabilityEntries}
            onClose={() => setRejectTarget(null)}
            onSaved={() => {
              setRejectTarget(null);
              setActionMsg(`Lesson saved. Recommendation "${rejectTarget.name}" canceled.`);
              refresh();
            }}
          />
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

interface RejectModalProps {
  recommendation: any;
  capabilityEntries: any[];
  onClose: () => void;
  onSaved: () => void;
}

function RejectAsLessonModal({ recommendation, capabilityEntries, onClose, onSaved }: RejectModalProps) {
  const [name, setName] = useState(`Reject ${recommendation.name}`);
  const [reason, setReason] = useState(
    `Rejected manually by analyst — the LLM proposed ${recommendation.name} but existing hub modules already cover this capability.`,
  );
  const [severity, setSeverity] = useState<'blocker' | 'hint'>('hint');
  const [filter, setFilter] = useState('');
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const sectionPattern = (recommendation.scope || recommendation.justification || recommendation.name || '').slice(0, 500);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return capabilityEntries.slice(0, 100);
    return capabilityEntries.filter((e) => (e.module_name || '').toLowerCase().includes(q)).slice(0, 100);
  }, [filter, capabilityEntries]);

  function toggle(id: number) {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setPicked(next);
  }

  async function save() {
    setErr(null);
    if (picked.size === 0) {
      setErr('Pick at least one existing module that already covers the capability.');
      return;
    }
    if (!reason.trim()) {
      setErr('Reason is required — this becomes the rationale shown to the AI on future runs.');
      return;
    }
    setSaving(true);
    try {
      await rejectRecommendationAsLesson(recommendation.id, {
        name,
        section_pattern: sectionPattern,
        rejected_proposals: [recommendation.name],
        correct_module_ids: Array.from(picked),
        reason,
        severity,
      });
      onSaved();
    } catch (e: any) {
      setErr(e?.detail || e?.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560, maxHeight: '85vh', overflow: 'auto',
          background: colors.surface, borderRadius: radii.md,
          border: `1px solid ${colors.border}`, padding: spacing.lg,
        }}
      >
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Reject &amp; save as lesson</h3>
        <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 12 }}>
          Cancels <code>{recommendation.name}</code> and writes a <code>brd.lesson</code> so future AI runs map this section to the correct existing modules.
        </div>

        <Label>Lesson name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />

        <Label>Severity</Label>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as 'blocker' | 'hint')}
          style={{ width: '100%', padding: 8, fontSize: 13, borderRadius: radii.sm, border: `1px solid ${colors.border}`, marginBottom: 10 }}
        >
          <option value="hint">Hint (injected only when section keywords match)</option>
          <option value="blocker">Blocker (always injected into AI prompt)</option>
        </select>

        <Label>Use instead (existing modules that already cover this)</Label>
        <Input placeholder="Filter modules…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div style={{
          maxHeight: 200, overflow: 'auto', marginTop: 6, marginBottom: 10,
          border: `1px solid ${colors.border}`, borderRadius: radii.sm,
        }}>
          {capabilityEntries.length === 0 ? (
            <div style={{ padding: 12, fontSize: 12, color: colors.textMuted }}>Loading modules…</div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 12, fontSize: 12, color: colors.textMuted }}>No matches.</div>
          ) : filtered.map((e) => (
            <div
              key={e.id}
              onClick={() => toggle(e.id)}
              style={{
                padding: '6px 10px', fontSize: 12, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 8,
                background: picked.has(e.id) ? colors.surfaceMuted : 'transparent',
              }}
            >
              <input type="checkbox" readOnly checked={picked.has(e.id)} />
              <span style={{ flex: 1 }}>{e.module_name}</span>
              {e.maturity && <Badge>{e.maturity}</Badge>}
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 10 }}>
          {picked.size} selected
        </div>

        <Label>Reason</Label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          style={{ width: '100%', padding: 8, fontSize: 13, borderRadius: radii.sm, border: `1px solid ${colors.border}`, marginBottom: 10, fontFamily: 'inherit' }}
        />

        <details style={{ marginBottom: 10 }}>
          <summary style={{ fontSize: 12, color: colors.textMuted, cursor: 'pointer' }}>
            Section keywords (auto-extracted)
          </summary>
          <pre style={{
            background: colors.bg, padding: 8, borderRadius: radii.sm,
            fontSize: 11, marginTop: 6, maxHeight: 100, overflow: 'auto',
            whiteSpace: 'pre-wrap',
          }}>{sectionPattern}</pre>
        </details>

        {err && (
          <div style={{ padding: 8, background: '#FEE2E2', color: '#991B1B', borderRadius: radii.sm, fontSize: 12, marginBottom: 10 }}>
            {err}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save lesson & cancel rec'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Label({ children }: { children: any }) {
  return <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 4, marginTop: 4 }}>{children}</div>;
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{
        width: '100%', padding: 8, fontSize: 13,
        borderRadius: radii.sm, border: `1px solid ${colors.border}`,
        marginBottom: 8,
        ...(props.style || {}),
      }}
    />
  );
}
