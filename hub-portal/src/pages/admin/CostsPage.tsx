import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card, Section } from '../../components/ui';
import { colors } from '../../tokens';

const DATA = [
  { tenant: 'Erajaya A', cost: 14 },
  { tenant: 'JDS Pratama', cost: 10 },
  { tenant: 'Telkom PPOB', cost: 22 },
  { tenant: 'Arkaim', cost: 8 },
];

export default function CostsPage() {
  return (
    <Section title="Costs" description="Monthly cost per tenant (Rp juta)">
      <Card>
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={DATA}>
              <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
              <XAxis dataKey="tenant" stroke={colors.textDim} fontSize={11} />
              <YAxis stroke={colors.textDim} fontSize={11} />
              <Tooltip contentStyle={{ background: colors.surfaceMuted, border: `1px solid ${colors.border}` }} />
              <Bar dataKey="cost" fill={colors.brand} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </Section>
  );
}
