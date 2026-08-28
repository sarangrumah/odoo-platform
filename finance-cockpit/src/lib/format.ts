// =============================================================================
// Formatting. Indonesian conventions throughout: "." thousands, "," decimals.
// =============================================================================

const ID = "id-ID";

/**
 * Compact rupiah for chart labels and KPI tiles: Rp 4,19 M / Rp 763 jt.
 *
 * Built by hand rather than with Intl `notation: "compact"`, whose Indonesian
 * output ("Rp 4,2 M" for milyar but "rb" for thousands) mixes registers and
 * emits a non-breaking space that shows up as "Â" once it passes through
 * Odoo-flavoured pipelines.
 */
export function rupiahShort(value: number): string {
  const sign = value < 0 ? "-" : "";
  const v = Math.abs(value);
  const unit = (scaled: number, suffix: string) =>
    // Precision by significant digits, not by unit. A flat 0 decimals in the
    // "jt" band rendered ATV of Rp 1.449.223 as "Rp 1 jt" — the headline KPI
    // lost its only meaningful digits.
    `${sign}Rp ${scaled.toLocaleString(ID, {
      maximumFractionDigits: scaled < 10 ? 2 : scaled < 100 ? 1 : 0,
    })} ${suffix}`;

  if (v >= 1e12) return unit(v / 1e12, "T");
  if (v >= 1e9) return unit(v / 1e9, "M");
  if (v >= 1e6) return unit(v / 1e6, "jt");
  if (v >= 1e3) return unit(v / 1e3, "rb");
  return `${sign}Rp ${v.toLocaleString(ID, { maximumFractionDigits: 0 })}`;
}

/** Full rupiah, for tooltips and tables where the exact figure matters. */
export function rupiah(value: number): string {
  return `Rp ${Math.round(value).toLocaleString(ID)}`;
}

export function count(value: number): string {
  return Math.round(value).toLocaleString(ID);
}

export function decimal(value: number, digits = 2): string {
  return value.toLocaleString(ID, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function percent(fraction: number, digits = 1): string {
  return `${(fraction * 100).toLocaleString(ID, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/** "12 Jun 2026" */
export function dayLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(ID, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** "12 Jun" — for dense axis ticks. */
export function dayTick(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(ID, { day: "numeric", month: "short", timeZone: "UTC" });
}

export function monthLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(ID, { month: "long", year: "numeric", timeZone: "UTC" });
}

/** Signed delta for period-over-period, e.g. "+12,4%" / "−3,1%". */
export function deltaLabel(current: number, previous: number): { text: string; sign: -1 | 0 | 1 } {
  if (!previous) return { text: "—", sign: 0 };
  const change = (current - previous) / Math.abs(previous);
  const sign = change > 0.0005 ? 1 : change < -0.0005 ? -1 : 0;
  const arrow = sign > 0 ? "+" : sign < 0 ? "−" : "";
  return { text: `${arrow}${percent(Math.abs(change))}`, sign };
}

/** Escape a value for CSV export. */
export function csvCell(value: string | number): string {
  const s = String(value);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
