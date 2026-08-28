"use client";

// =============================================================================
// Chart primitives.
//
// Colours are referenced as CSS custom properties (`var(--series-1)`) rather
// than hex, so a theme change repaints the marks without re-rendering React.
// Series colour follows the entity, never its rank: a filter that drops stores
// must not repaint the survivors.
//
// Every chart here ships a hover layer, and every chart on a page is paired
// with a table — three light-mode slots sit under 3:1 contrast, and the
// validator's relief rule requires visible labels or a table view.
// =============================================================================

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { count, dayLabel, dayTick, rupiah, rupiahShort } from "@/lib/format";

const AXIS = { stroke: "var(--border-strong)", fontSize: 11, tickLine: false } as const;
const GRID = { stroke: "var(--border)", strokeDasharray: "3 3", vertical: false } as const;

/** Adds or removes a value from a comma-separated search param. */
export function useToggleParam() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString());
      const current = (next.get(key) ?? "").split(",").filter(Boolean);
      const updated = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      if (updated.length) next.set(key, updated.join(","));
      else next.delete(key);
      const qs = next.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname);
    },
    [pathname, router, searchParams],
  );
}

interface TooltipPayload {
  active?: boolean;
  label?: string | number;
  payload?: { name?: string; value?: number; color?: string; dataKey?: string | number }[];
}

function MoneyTooltip({ active, label, payload, titleFormat }: TooltipPayload & {
  titleFormat?: (v: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{titleFormat ? titleFormat(String(label)) : String(label)}</div>
      {payload.map((entry, i) => (
        <div className="t-row" key={i}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span
              className="swatch"
              style={{
                width: 10,
                height: 10,
                borderRadius: 3,
                background: entry.color,
                display: "inline-block",
              }}
            />
            {entry.name}
          </span>
          <span>{rupiah(entry.value ?? 0)}</span>
        </div>
      ))}
    </div>
  );
}

// --- Daily trend -------------------------------------------------------------

export interface TrendSeries {
  key: string;
  label: string;
  color: string;
}

export function TrendChart({
  data,
  series,
  height = 280,
}: {
  data: Record<string, string | number>[];
  series: TrendSeries[];
  height?: number;
}) {
  return (
    <>
      {series.length > 1 && (
        <div className="legend" style={{ marginBottom: 8 }}>
          {series.map((s) => (
            <span className="item" key={s.key}>
              <span className="swatch" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <defs>
            {series.map((s) => (
              <linearGradient id={`fill-${s.key}`} key={s.key} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.22} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="day" tickFormatter={dayTick} minTickGap={28} {...AXIS} />
          <YAxis tickFormatter={rupiahShort} width={78} {...AXIS} />
          <Tooltip
            content={<MoneyTooltip titleFormat={dayLabel} />}
            cursor={{ stroke: "var(--text-muted)", strokeWidth: 1 }}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#fill-${s.key})`}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </>
  );
}

// --- Ranked bars -------------------------------------------------------------

export interface RankDatum {
  name: string;
  value: number;
  /** Passed back on click, for cross-filtering. */
  id?: string;
  selected?: boolean;
}

export function RankBars({
  data,
  paramKey,
  height,
}: {
  data: RankDatum[];
  /** When set, clicking a bar toggles that value in this search param. */
  paramKey?: string;
  height?: number;
}) {
  const toggle = useToggleParam();
  const anySelected = data.some((d) => d.selected);
  const chartHeight = height ?? Math.max(180, data.length * 26 + 24);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid {...GRID} vertical horizontal={false} />
        <XAxis type="number" tickFormatter={rupiahShort} {...AXIS} />
        <YAxis type="category" dataKey="name" width={190} interval={0} {...AXIS} />
        <Tooltip content={<MoneyTooltip />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar
          dataKey="value"
          name="Penjualan"
          radius={[0, 4, 4, 0]}
          isAnimationActive={false}
          onClick={
            paramKey
              ? (entry: unknown) => {
                  const id = (entry as RankDatum).id ?? (entry as RankDatum).name;
                  toggle(paramKey, id);
                }
              : undefined
          }
          cursor={paramKey ? "pointer" : "default"}
        >
          {data.map((d) => (
            <Cell
              key={d.name}
              fill="var(--series-1)"
              // Dimming the unselected bars keeps identity stable — the colour
              // still belongs to the entity, only its emphasis changes.
              fillOpacity={!anySelected || d.selected ? 1 : 0.35}
              stroke="var(--surface-1)"
              strokeWidth={2}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- Small multiples ---------------------------------------------------------

export function SparkGrid({
  groups,
}: {
  groups: { name: string; total: number; points: { day: string; gross: number }[] }[];
}) {
  // One shared y-domain across all panels: small multiples that each rescale
  // are a lie, since a quiet store then looks as busy as the flagship.
  const max = Math.max(1, ...groups.flatMap((g) => g.points.map((p) => p.gross)));

  return (
    <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
      {groups.map((g) => (
        <div key={g.name}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2 }}>{g.name}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
            {rupiahShort(g.total)}
          </div>
          <ResponsiveContainer width="100%" height={72}>
            <AreaChart data={g.points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
              <YAxis domain={[0, max]} hide />
              <XAxis dataKey="day" hide />
              <Tooltip content={<MoneyTooltip titleFormat={dayLabel} />} />
              <Area
                type="monotone"
                dataKey="gross"
                name={g.name}
                stroke="var(--series-1)"
                strokeWidth={2}
                fill="var(--series-1)"
                fillOpacity={0.14}
                dot={false}
                activeDot={{ r: 3, strokeWidth: 2, stroke: "var(--surface-1)" }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}

// --- Transactions-per-day, a second measure that must not share an axis ------

export function CountTrend({ data, height = 160 }: { data: { day: string; transactions: number }[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="day" tickFormatter={dayTick} minTickGap={28} {...AXIS} />
        <YAxis tickFormatter={count} width={54} {...AXIS} />
        <Tooltip
          cursor={{ stroke: "var(--text-muted)", strokeWidth: 1 }}
          content={({ active, label, payload }: TooltipPayload) =>
            active && payload?.length ? (
              <div className="tooltip">
                <div className="t-title">{dayLabel(String(label))}</div>
                <div className="t-row">
                  <span>Transaksi</span>
                  <span>{count(payload[0].value ?? 0)}</span>
                </div>
              </div>
            ) : null
          }
        />
        <Area
          type="monotone"
          dataKey="transactions"
          stroke="var(--series-2)"
          strokeWidth={2}
          fill="var(--series-2)"
          fillOpacity={0.12}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
