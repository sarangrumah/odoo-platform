import { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { Building2, Activity, AlertTriangle, DollarSign } from 'lucide-react';
import { Card, Section } from '../../components/ui';
import { colors, spacing } from '../../tokens';

const KPI = [
  { icon: Building2, label: 'Active tenants', value: '12', delta: '+2 this month' },
  { icon: Activity, label: 'Uptime (30d)', value: '99.62%', delta: 'SLA 99.50%' },
  { icon: AlertTriangle, label: 'Open incidents', value: '3', delta: '1 P2 · 2 P3' },
  { icon: DollarSign, label: 'Monthly run-rate', value: 'Rp 184M', delta: '+4.1% vs Apr' },
];

const SAMPLE_SERIES = Array.from({ length: 14 }).map((_, i) => ({
  day: `D${i + 1}`,
  requests: 4000 + Math.round(Math.random() * 2200),
  errors: 30 + Math.round(Math.random() * 40),
}));

export default function DashboardPage() {
  // TODO: hook to api.getMetrics() once endpoint stabilises.
  const [series] = useState(SAMPLE_SERIES);

  useEffect(() => {
    // placeholder for fetch
  }, []);

  return (
    <div>
      <Section title="Overview" description="Platform health at a glance">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: spacing.md,
          }}
        >
          {KPI.map((k) => {
            const Icon = k.icon;
            return (
              <Card key={k.label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: colors.textMuted, fontSize: 12 }}>{k.label}</span>
                  <Icon size={16} color={colors.accent} />
                </div>
                <div style={{ fontSize: 28, fontWeight: 700, marginTop: 6 }}>{k.value}</div>
                <div style={{ fontSize: 11, color: colors.textDim }}>{k.delta}</div>
              </Card>
            );
          })}
        </div>
      </Section>

      <Section title="Traffic (14 days)">
        <Card>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={series}>
                <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke={colors.textDim} fontSize={11} />
                <YAxis stroke={colors.textDim} fontSize={11} />
                <Tooltip contentStyle={{ background: colors.surfaceMuted, border: `1px solid ${colors.border}` }} />
                <Line type="monotone" dataKey="requests" stroke={colors.accent} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="errors" stroke={colors.danger} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </Section>
    </div>
  );
}
