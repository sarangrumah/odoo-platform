"use client";

// =============================================================================
// Chart primitives, finance edition.
//
// Same system as the sales cockpit: colours are CSS custom properties
// (`var(--series-1)`) rather than hex, so a theme change repaints the marks
// without re-rendering React, and colour follows the entity rather than its
// rank. The palette was validated against both surfaces — categorical
// #2a78d6 / #eb6834 / #1baf7a passes lightness, chroma, CVD separation and the
// normal-vision floor in light and dark. Light mode raises one contrast WARN on
// --series-3 (2.74:1), which obliges relief: every chart here is paired with the
// table that carries the same numbers, and that is not optional.
//
// Two deliberate differences from the sales charts:
//
//   * Almost every chart is SINGLE-SERIES. Finance questions here are one
//     measure over a dimension, and eight hues when the story is one number is
//     the most common way a chart misses its point.
//   * Aging is drawn as ordered bars in one hue, never as seven stacked
//     colours. Past about seven colour classes adjacent bins blur, and the
//     bucket table beside it already carries the split.
//
// Amounts are drawn as magnitudes. A payable is negative in the ledger, but bar
// length is not the place to carry a bookkeeping sign — the sign lives in the
// table and in the tooltip, and the axis says what it is measuring.
// =============================================================================

import { useRouter } from "next/navigation";
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

import { count, monthLabel, rupiah, rupiahShort } from "@/lib/format";

const AXIS = { stroke: "var(--border-strong)", fontSize: 11, tickLine: false } as const;
const GRID = { stroke: "var(--border)", strokeDasharray: "3 3", vertical: false } as const;

interface TooltipPayload {
  active?: boolean;
  label?: string | number;
  payload?: {
    name?: string;
    value?: number;
    color?: string;
    payload?: Record<string, unknown>;
  }[];
}

/**
 * The shared hover layer.
 *
 * `signed` prints the ledger sign, so a reader who wonders why a bar is long
 * and the table says -55 billion gets the answer without leaving the chart.
 */
function ChartTooltip({
  active,
  label,
  payload,
  titleFormat,
  valueFormat = rupiah,
  signedKey,
}: TooltipPayload & {
  titleFormat?: (v: string) => string;
  valueFormat?: (v: number) => string;
  signedKey?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0];
  const signed = signedKey ? (row.payload?.[signedKey] as number | undefined) : undefined;

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
          <span>{valueFormat(entry.value ?? 0)}</span>
        </div>
      ))}
      {signed !== undefined && signed < 0 && (
        <div className="t-row" style={{ color: "var(--text-muted)" }}>
          <span>Di buku besar</span>
          <span>{rupiah(signed)}</span>
        </div>
      )}
    </div>
  );
}

// --- Ordered categories, one hue ---------------------------------------------

export interface OrderedDatum {
  /** Category label. Order is the array order — never sorted by value. */
  name: string;
  value: number;
  /** The ledger-signed original, shown in the tooltip. */
  signed?: number;
}

/**
 * Magnitude across an ORDERED category — aging buckets, weeks, months.
 *
 * The order is the data's own, not the values': "31–60 hari" sits between
 * "1–30" and "61–90" whatever their sizes, because that adjacency is the
 * information. One hue, because position already carries the ordering and a
 * second encoding of the same fact would only add noise.
 */
export function OrderedBars({
  data,
  height = 240,
  valueFormat = rupiahShort,
  tooltipFormat = rupiah,
  emptyLabel = "Tidak ada data pada rentang ini.",
}: {
  data: OrderedDatum[];
  height?: number;
  valueFormat?: (v: number) => string;
  tooltipFormat?: (v: number) => string;
  emptyLabel?: string;
}) {
  if (!data.some((d) => d.value)) return <p className="sub">{emptyLabel}</p>;

  // When the series carries both signs, the bars must straddle a zero baseline.
  // Drawing magnitudes instead would make a net credit and a net debit of
  // similar size look like the same thing, which is the opposite of the truth.
  const hasNegative = data.some((d) => d.value < 0);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" interval={0} tickMargin={6} {...AXIS} />
        <YAxis tickFormatter={valueFormat} width={78} {...AXIS} />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={<ChartTooltip valueFormat={tooltipFormat} signedKey="signed" />}
        />
        <Bar
          dataKey="value"
          name="Nilai"
          // 4px rounded data-end, anchored to the baseline. With negatives in
          // the series a single radius would round the wrong end of the bars
          // below zero, so those are drawn square.
          radius={hasNegative ? 0 : [4, 4, 0, 0]}
          isAnimationActive={false}
          fill="var(--series-1)"
          // 2px surface gap between adjacent bars.
          stroke="var(--surface-1)"
          strokeWidth={2}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- Ranked bars --------------------------------------------------------------

export interface RankDatum {
  name: string;
  value: number;
  signed?: number;
  /** Navigating here on click, when the row has somewhere to drill to. */
  href?: string;
}

/**
 * Top-N by magnitude, biggest first.
 *
 * Horizontal because the labels are vendor and account names, which do not fit
 * under a vertical axis at any readable size.
 */
export function RankBars({
  data,
  height,
  labelWidth = 220,
  valueFormat = rupiahShort,
  tooltipFormat = rupiah,
  emptyLabel = "Tidak ada data pada rentang ini.",
}: {
  data: RankDatum[];
  height?: number;
  labelWidth?: number;
  valueFormat?: (v: number) => string;
  tooltipFormat?: (v: number) => string;
  emptyLabel?: string;
}) {
  const router = useRouter();
  const onClick = useCallback(
    (entry: unknown) => {
      const href = (entry as RankDatum)?.href;
      if (href) router.push(href);
    },
    [router],
  );

  if (!data.length) return <p className="sub">{emptyLabel}</p>;

  const clickable = data.some((d) => d.href);
  // 34px a row, not 26: these labels are vendor and account names that wrap to
  // two lines, and at the tighter pitch the second line collides with the row
  // below it.
  const chartHeight = height ?? Math.max(180, data.length * 34 + 28);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid {...GRID} vertical horizontal={false} />
        <XAxis type="number" tickFormatter={valueFormat} {...AXIS} />
        <YAxis type="category" dataKey="name" width={labelWidth} interval={0} {...AXIS} />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={<ChartTooltip valueFormat={tooltipFormat} signedKey="signed" />}
        />
        <Bar
          dataKey="value"
          name="Nilai"
          radius={[0, 4, 4, 0]}
          isAnimationActive={false}
          onClick={clickable ? onClick : undefined}
          cursor={clickable ? "pointer" : "default"}
        >
          {data.map((d) => (
            <Cell
              key={d.name}
              fill="var(--series-1)"
              stroke="var(--surface-1)"
              strokeWidth={2}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- Change over time ---------------------------------------------------------

export interface TrendSeries {
  key: string;
  label: string;
  /** A CSS custom property, in the fixed order --series-1, -2, -3. */
  color: string;
}

export const SERIES_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"] as const;

/**
 * A measure over months.
 *
 * A legend appears from two series up; one series needs none, because the card
 * heading already names it. Never a second y-axis — two measures of different
 * scale get two charts.
 */
export function MonthlyTrend({
  data,
  series,
  height = 240,
  valueFormat = rupiahShort,
  tooltipFormat = rupiah,
  emptyLabel = "Belum ada data bulanan.",
}: {
  data: Record<string, string | number>[];
  series: TrendSeries[];
  height?: number;
  valueFormat?: (v: number) => string;
  tooltipFormat?: (v: number) => string;
  emptyLabel?: string;
}) {
  if (!data.length) return <p className="sub">{emptyLabel}</p>;

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
              <linearGradient id={`fin-fill-${s.key}`} key={s.key} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.22} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="month" tickFormatter={monthLabel} minTickGap={24} {...AXIS} />
          <YAxis tickFormatter={valueFormat} width={78} {...AXIS} />
          <Tooltip
            cursor={{ stroke: "var(--text-muted)", strokeWidth: 1 }}
            content={<ChartTooltip titleFormat={monthLabel} valueFormat={tooltipFormat} />}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#fin-fill-${s.key})`}
              dot={false}
              // 2px surface ring on the hovered mark, so overlapping series
              // stay separable.
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </>
  );
}

/** Counts, not money — a separate axis formatter and tooltip wording. */
export function CountBars({
  data,
  height = 200,
  emptyLabel = "Tidak ada data.",
}: {
  data: OrderedDatum[];
  height?: number;
  emptyLabel?: string;
}) {
  return (
    <OrderedBars
      data={data}
      height={height}
      valueFormat={count}
      tooltipFormat={count}
      emptyLabel={emptyLabel}
    />
  );
}
