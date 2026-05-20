import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card, Section } from '../../components/ui';
import { colors, spacing } from '../../tokens';

const DATA = Array.from({ length: 24 }).map((_, h) => ({
  h: `${h}:00`,
  cpu: 30 + Math.round(Math.random() * 50),
  mem: 40 + Math.round(Math.random() * 30),
}));

export default function MonitoringPage() {
  const [data] = useState(DATA);
  return (
    <Section title="Monitoring" description="24h tenant cluster metrics">
      <Card>
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <AreaChart data={data}>
              <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
              <XAxis dataKey="h" stroke={colors.textDim} fontSize={11} />
              <YAxis stroke={colors.textDim} fontSize={11} />
              <Tooltip contentStyle={{ background: colors.surfaceMuted, border: `1px solid ${colors.border}` }} />
              <Area type="monotone" dataKey="cpu" stroke={colors.accent} fill={colors.accent} fillOpacity={0.2} />
              <Area type="monotone" dataKey="mem" stroke={colors.info} fill={colors.info} fillOpacity={0.2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <div style={{ marginTop: spacing.md, color: colors.textMuted, fontSize: 12 }}>
        TODO: wire to Prometheus / orchestrator metrics endpoint.
      </div>
    </Section>
  );
}
