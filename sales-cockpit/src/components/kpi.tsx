import { deltaLabel } from "@/lib/format";

/**
 * A stat tile: the headline number, and what it was in the preceding window of
 * equal length. `higherIsBetter=false` flips the colour for metrics where a
 * rise is bad — nothing in the fast path uses it yet, but discount depth will.
 */
export function Kpi({
  label,
  value,
  previous,
  current,
  hint,
  higherIsBetter = true,
}: {
  label: string;
  value: string;
  current?: number;
  previous?: number;
  hint?: string;
  higherIsBetter?: boolean;
}) {
  const delta =
    current !== undefined && previous !== undefined ? deltaLabel(current, previous) : null;
  const sign = delta ? (higherIsBetter ? delta.sign : ((delta.sign * -1) as -1 | 0 | 1)) : 0;

  return (
    <div className="card kpi">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      <span className="foot">
        {delta && (
          <span className="delta" data-sign={sign}>
            {delta.text}
          </span>
        )}
        <span>{hint ?? (delta ? "vs periode sebelumnya" : "")}</span>
      </span>
    </div>
  );
}
