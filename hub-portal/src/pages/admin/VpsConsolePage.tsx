import { useEffect, useRef, useState } from 'react';
import { Server, Play, Trash2, RefreshCw, Cloud } from 'lucide-react';
import { Badge, Button, Card, Modal, Section, Table, Tabs } from '../../components/ui';
import { colors, spacing } from '../../tokens';
import { bootstrapVps, deployStack, listVps } from '../../api';

interface Vps {
  id: number;
  name: string;
  host: string;
  state: string;
  region?: string;
  envs?: string[];
  grafana_dashboard_url?: string;
}

const MOCK: Vps[] = [
  { id: 1, name: 'erajaya-prod-01', host: '10.20.30.41', state: 'live', region: 'jkt-1', envs: ['prod'], grafana_dashboard_url: 'https://grafana.local/d/erajaya' },
  { id: 2, name: 'jds-staging', host: '10.20.30.42', state: 'bootstrapping', region: 'jkt-1', envs: ['staging'] },
  { id: 3, name: 'arkaim-prod-01', host: '10.20.30.43', state: 'registered', region: 'sgp-1', envs: [] },
];

export default function VpsConsolePage() {
  const [rows, setRows] = useState<Vps[]>(MOCK);
  const [open, setOpen] = useState<Vps | null>(null);
  const [tab, setTab] = useState('info');
  const [log, setLog] = useState<string[]>(['[boot] waiting…']);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    listVps()
      .then((r) => Array.isArray(r) && r.length && setRows(r as any))
      .catch(() => {/* keep mock */});
  }, []);

  // Bootstrap log polling — placeholder.
  useEffect(() => {
    if (!open || tab !== 'log') return;
    pollRef.current = window.setInterval(() => {
      setLog((l) => [...l, `[${new Date().toLocaleTimeString()}] tick ${l.length}`]);
    }, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [open, tab]);

  return (
    <Section
      title="VPS Console"
      description="Tenant infrastructure nodes"
      actions={
        <Button>
          <Server size={14} /> Register VPS
        </Button>
      }
    >
      <Table
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'host', label: 'Host' },
          { key: 'region', label: 'Region' },
          {
            key: 'state',
            label: 'State',
            render: (r) => (
              <Badge
                tone={
                  r.state === 'live' ? 'success' : r.state === 'bootstrapping' ? 'warning' : 'info'
                }
              >
                {r.state}
              </Badge>
            ),
          },
          {
            key: 'envs',
            label: 'Envs',
            render: (r) => (r.envs || []).map((e: string) => <Badge key={e} style={{ marginRight: 4 }}>{e}</Badge>),
          },
          {
            key: 'actions',
            label: '',
            render: (r) => (
              <Button size="sm" variant="secondary" onClick={() => { setOpen(r); setTab('info'); }}>
                Manage
              </Button>
            ),
          },
        ]}
        rows={rows}
      />

      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `VPS: ${open.name}` : ''} width={900}>
        {open && (
          <div>
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { key: 'info', label: 'Info' },
                { key: 'envs', label: 'Environments' },
                { key: 'log', label: 'Bootstrap Log' },
                { key: 'health', label: 'Health' },
              ]}
            />

            {tab === 'info' && (
              <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                <div>Host: <code>{open.host}</code></div>
                <div>Region: {open.region}</div>
                <div>State: <Badge tone="info">{open.state}</Badge></div>
                <div style={{ display: 'flex', gap: spacing.sm, marginTop: spacing.md }}>
                  <Button onClick={() => bootstrapVps(open.id).catch(() => {})}>
                    <Play size={14} /> Bootstrap
                  </Button>
                  <Button variant="secondary" onClick={() => deployStack(open.id, 'prod').catch(() => {})}>
                    <Cloud size={14} /> Deploy stack
                  </Button>
                  <Button variant="secondary">
                    <RefreshCw size={14} /> Sync addons
                  </Button>
                  <Button variant="danger">
                    <Trash2 size={14} /> Decommission
                  </Button>
                </div>
              </div>
            )}

            {tab === 'envs' && (
              <Table
                columns={[
                  { key: 'env', label: 'Env' },
                  { key: 'compose', label: 'Compose profile' },
                  { key: 'state', label: 'State', render: (r) => <Badge tone="success">{r.state}</Badge> },
                ]}
                rows={(open.envs || []).map((e) => ({ id: e, env: e, compose: `${e}.yml`, state: 'running' }))}
              />
            )}

            {tab === 'log' && (
              <pre
                style={{
                  background: colors.bg,
                  border: `1px solid ${colors.border}`,
                  padding: spacing.md,
                  borderRadius: 8,
                  fontSize: 12,
                  maxHeight: 360,
                  overflow: 'auto',
                  color: colors.success,
                }}
              >
                {log.join('\n')}
              </pre>
            )}

            {tab === 'health' && (
              <div>
                {open.grafana_dashboard_url ? (
                  <iframe
                    title="Grafana"
                    src={open.grafana_dashboard_url}
                    style={{ width: '100%', height: 380, border: `1px solid ${colors.border}`, borderRadius: 8 }}
                  />
                ) : (
                  <div style={{ color: colors.textMuted, fontSize: 13 }}>
                    No Grafana dashboard URL configured for this VPS.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </Section>
  );
}
