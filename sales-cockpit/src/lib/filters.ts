// =============================================================================
// The global filter state.
//
// It lives in the URL search params so every view is shareable — which matters
// during a demo, where "send me that screen" is the most common request. Each
// query builds its WHERE clause through `buildScope`, so a filter added here
// applies everywhere at once.
// =============================================================================

/**
 * Fallback extent of the POS data in prd_levis_begbal.
 *
 * These are only a floor: the real extent is read from the database on every
 * request by `dataExtent()` in queries/sales.ts and threaded through as an
 * `Extent`. Hard-coding the end date once meant the dashboard silently stopped
 * at 2026-08-09 while the retail-import feed kept loading days after it.
 */
export const DATA_START = "2026-06-12";
export const DATA_END = "2026-08-09";

/** The first and last day with sales, as read from the database. */
export interface Extent {
  start: string;
  end: string;
}

export const FALLBACK_EXTENT: Extent = { start: DATA_START, end: DATA_END };

export interface Filters {
  from: string;
  to: string;
  stores: number[];
  /** Level-2 of product_category.complete_name, e.g. "MENS BOTTOMS". */
  categories: string[];
  /** "member" = has a loyalty id, "guest" = none, null = both. */
  membership: "member" | "guest" | null;
  associate: string | null;
}

type Params = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function list(value: string | string[] | undefined): string[] {
  const raw = Array.isArray(value) ? value : value ? [value] : [];
  return raw.flatMap((v) => v.split(",")).map((v) => v.trim()).filter(Boolean);
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function parseFilters(params: Params, extent: Extent = FALLBACK_EXTENT): Filters {
  const from = first(params.from);
  const to = first(params.to);
  const membership = first(params.membership);

  return {
    from: from && ISO_DATE.test(from) ? from : extent.start,
    to: to && ISO_DATE.test(to) ? to : extent.end,
    stores: list(params.stores).map(Number).filter((n) => Number.isInteger(n) && n > 0),
    categories: list(params.categories),
    membership: membership === "member" || membership === "guest" ? membership : null,
    associate: first(params.associate)?.trim() || null,
  };
}

export function serialiseFilters(f: Filters, extent: Extent = FALLBACK_EXTENT): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.from !== extent.start) sp.set("from", f.from);
  if (f.to !== extent.end) sp.set("to", f.to);
  if (f.stores.length) sp.set("stores", f.stores.join(","));
  if (f.categories.length) sp.set("categories", f.categories.join(","));
  if (f.membership) sp.set("membership", f.membership);
  if (f.associate) sp.set("associate", f.associate);
  return sp;
}

/**
 * The category label the whole cockpit groups and filters by.
 *
 * Level 2 where it exists, otherwise the category's own name: a root category
 * such as "Labor (Service)" or "Miscellaneous" has no level 2, and calling it
 * uncategorised was wrong — it IS categorised, just one level up. Only a
 * product with no `categ_id` at all falls through to "Uncategorised".
 *
 * Display and filter must share this expression, or clicking a bar produces a
 * filter that matches nothing.
 */
export const CATEGORY_LABEL =
  `COALESCE(NULLIF(split_part(pc.complete_name, ' / ', 2), ''), pc.complete_name, 'Uncategorised')`;

export interface Scope {
  /** SQL predicates joined with AND, always non-empty. */
  where: string;
  params: unknown[];
  /** True when a filter needs the line/product joins, not just the order. */
  needsLines: boolean;
}

/**
 * Build the shared WHERE clause.
 *
 * Table aliases are fixed by contract: `o` = pos_order, `l` = pos_order_line,
 * `pc` = product_category. Every query in queries/ uses those names.
 */
export function buildScope(f: Filters): Scope {
  const where: string[] = [];
  const params: unknown[] = [];

  // `date_order` is a timestamp; `< to + 1 day` keeps the last day inclusive
  // without rounding the column and losing the index.
  params.push(f.from);
  where.push(`o.date_order >= $${params.length}::date`);
  params.push(f.to);
  where.push(`o.date_order < ($${params.length}::date + interval '1 day')`);

  if (f.stores.length) {
    params.push(f.stores);
    where.push(`c.id = ANY($${params.length}::int[])`);
  }

  if (f.membership === "member") {
    where.push(`o.ri_member_type IS NOT NULL AND o.ri_member_type <> ''`);
  } else if (f.membership === "guest") {
    where.push(`(o.ri_member_type IS NULL OR o.ri_member_type = '')`);
  }

  let needsLines = false;

  if (f.categories.length) {
    params.push(f.categories);
    where.push(`${CATEGORY_LABEL} = ANY($${params.length}::text[])`);
    needsLines = true;
  }

  if (f.associate) {
    params.push(f.associate);
    where.push(`l.ri_staff_name = $${params.length}`);
    needsLines = true;
  }

  return { where: where.join("\n      AND "), params, needsLines };
}

/**
 * The immediately preceding window of equal length, for period-over-period
 * deltas. A 30-day range compares against the 30 days before it.
 */
export function previousPeriod(f: Filters): { from: string; to: string } {
  const from = new Date(`${f.from}T00:00:00Z`);
  const to = new Date(`${f.to}T00:00:00Z`);
  const days = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
  const prevTo = new Date(from.getTime() - 86_400_000);
  const prevFrom = new Date(prevTo.getTime() - (days - 1) * 86_400_000);
  return {
    from: prevFrom.toISOString().slice(0, 10),
    to: prevTo.toISOString().slice(0, 10),
  };
}

/**
 * Month to date, anchored to the last day WITH DATA rather than to today.
 *
 * The retail-import feed runs a day or more behind, so a calendar-today anchor
 * would count days the dashboard has no rows for and drag every MTD average
 * down. `from` is the first of that month, `to` is the last loaded day.
 */
export function monthToDate(extent: Extent): { from: string; to: string } {
  const end = new Date(`${extent.end}T00:00:00Z`);
  const first = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1))
    .toISOString()
    .slice(0, 10);
  // Never reach behind the first day with data: in the very first month of the
  // dataset the month starts before the data does.
  return { from: first < extent.start ? extent.start : first, to: extent.end };
}

/**
 * The same slice of the previous month: the same day numbers, clamped to that
 * month's length (a 31 Mar MTD compares against 1–28/29 Feb, never into March).
 *
 * Both endpoints are mirrored, not just the end: when the month-to-date window
 * is itself clipped to the first day with data, comparing it against a full
 * previous month would flatter or damn it for days it never covered.
 *
 * This is the honest MTD comparison — the preceding window of equal length used
 * elsewhere straddles two months and mixes a month-end with a month-start.
 */
export function sameSpanPreviousMonth(range: { from: string; to: string }): {
  from: string;
  to: string;
} {
  const to = new Date(`${range.to}T00:00:00Z`);
  const year = to.getUTCFullYear();
  const month = to.getUTCMonth();
  const daysInPrev = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const clamp = (day: number) => Math.min(day, daysInPrev);
  const fromDay = clamp(Number(range.from.slice(8, 10)));
  const toDay = clamp(to.getUTCDate());
  const iso = (day: number) =>
    new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10);
  return { from: iso(fromDay), to: iso(toDay) };
}

/** Whole days in an inclusive ISO date range. */
export function daysInRange(range: { from: string; to: string }): number {
  const from = new Date(`${range.from}T00:00:00Z`).getTime();
  const to = new Date(`${range.to}T00:00:00Z`).getTime();
  return Math.round((to - from) / 86_400_000) + 1;
}

/** Days in the calendar month that `iso` falls in. */
export function daysInMonth(iso: string): number {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
}
