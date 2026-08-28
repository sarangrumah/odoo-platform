// =============================================================================
// Slot extraction: turning a sentence into Filters, without a model.
//
// Everything here is anchored to the DATA's last day, never to the wall clock.
// The retail-import feed runs behind, so "hari ini" asked on 20 August against
// data that stops on 9 August must mean 9 August — anchoring to the calendar
// would answer "Rp 0" and be technically correct and completely useless.
// =============================================================================

// Type-only import: this module stays free of runtime dependencies so the date
// arithmetic can be unit-tested without a database or a React runtime behind it.
import type { Catalog } from "@/lib/agent/catalog";
import type { Extent, Filters } from "@/lib/filters";

// --- text normalisation ------------------------------------------------------

/** Lowercase, strip punctuation, collapse whitespace. Kept as words, not chars. */
export function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// --- date arithmetic (UTC throughout, to match the DATE columns) -------------

const DAY = 86_400_000;
const iso = (d: Date) => d.toISOString().slice(0, 10);
const parse = (s: string) => new Date(`${s}T00:00:00Z`);
const shift = (s: string, days: number) => iso(new Date(parse(s).getTime() + days * DAY));

function monthRange(year: number, month: number): { from: string; to: string } {
  const from = new Date(Date.UTC(year, month, 1));
  const to = new Date(Date.UTC(year, month + 1, 0));
  return { from: iso(from), to: iso(to) };
}

/** Monday-based week containing `day`. Indonesian retail weeks start Monday. */
function weekRange(day: string): { from: string; to: string } {
  const d = parse(day);
  const dow = (d.getUTCDay() + 6) % 7; // 0 = Monday
  const from = new Date(d.getTime() - dow * DAY);
  return { from: iso(from), to: iso(new Date(from.getTime() + 6 * DAY)) };
}

/**
 * Clip a range to the days that actually have data.
 *
 * Returns null when the request lands entirely outside the dataset — the caller
 * turns that into "data hanya tersedia sampai …" instead of a silent Rp 0.
 */
function clip(range: { from: string; to: string }, extent: Extent) {
  const from = range.from < extent.start ? extent.start : range.from;
  const to = range.to > extent.end ? extent.end : range.to;
  return from > to ? null : { from, to };
}

const MONTHS: Record<string, number> = {
  januari: 0, jan: 0,
  februari: 1, feb: 1, pebruari: 1,
  maret: 2, mar: 2,
  april: 3, apr: 3,
  mei: 4,
  juni: 5, jun: 5,
  juli: 6, jul: 6,
  agustus: 7, agu: 7, ags: 7, agt: 7, aug: 7,
  september: 8, sep: 8, sept: 8,
  oktober: 9, okt: 9, oct: 9,
  november: 10, nov: 10,
  desember: 11, des: 11, dec: 11,
};

export interface RangeMatch {
  from: string;
  to: string;
  /** True when the phrase resolved to a period outside the loaded data. */
  clipped: boolean;
  /** The phrase that produced it, for the audit log. */
  phrase: string;
}

interface RawRange {
  from: string;
  to: string;
  phrase: string;
}

/**
 * The period the sentence names, BEFORE clipping to the loaded data.
 *
 * Kept separate from extractRange so the two "no range" cases stay
 * distinguishable: nothing was said about time, versus a period was named and
 * it lies outside the dataset. The first inherits the filter bar; the second
 * has to be told to the reader.
 */
function rawRange(text: string, extent: Extent): RawRange | null {
  const t = normalise(text);
  const end = extent.end;
  const endYear = Number(end.slice(0, 4));

  const hit = (phrase: string, range: { from: string; to: string }): RawRange => ({
    ...range,
    phrase,
  });

  // --- explicit ISO dates: "2026-07-15" or "dari 2026-07-01 sampai 2026-07-31"
  const isoDates = t.match(/\d{4}-\d{2}-\d{2}/g);
  if (isoDates?.length) {
    const sorted = [...isoDates].sort();
    return hit(isoDates.join(" .. "), { from: sorted[0], to: sorted[sorted.length - 1] });
  }

  // --- "n hari terakhir" / "7 hari terakhir"
  const lastDays = t.match(/(\d{1,3})\s+hari\s+(terakhir|belakangan|kebelakang)/);
  if (lastDays) {
    const n = Math.min(Number(lastDays[1]), 400);
    return hit(lastDays[0], { from: shift(end, -(n - 1)), to: end });
  }

  // --- "n bulan terakhir"
  const lastMonths = t.match(/(\d{1,2})\s+bulan\s+(terakhir|belakangan)/);
  if (lastMonths) {
    const n = Math.min(Number(lastMonths[1]), 24);
    const e = parse(end);
    const from = new Date(Date.UTC(e.getUTCFullYear(), e.getUTCMonth() - (n - 1), 1));
    return hit(lastMonths[0], { from: iso(from), to: end });
  }

  // --- "15 juli" / "15 juli 2026" / "juli 2026" / "juli"
  const dayMonth = t.match(
    new RegExp(`\\b(\\d{1,2})\\s+(${Object.keys(MONTHS).join("|")})\\b(?:\\s+(\\d{4}))?`),
  );
  if (dayMonth) {
    const day = Number(dayMonth[1]);
    const month = MONTHS[dayMonth[2]];
    const year = dayMonth[3] ? Number(dayMonth[3]) : endYear;
    const d = iso(new Date(Date.UTC(year, month, day)));
    return hit(dayMonth[0], { from: d, to: d });
  }

  const bareMonth = t.match(
    new RegExp(`\\b(?:bulan\\s+)?(${Object.keys(MONTHS).join("|")})\\b(?:\\s+(\\d{4}))?`),
  );
  if (bareMonth) {
    const month = MONTHS[bareMonth[1]];
    const year = bareMonth[2] ? Number(bareMonth[2]) : endYear;
    return hit(bareMonth[0], monthRange(year, month));
  }

  // --- quarters: "q2", "kuartal 2", "triwulan 3"
  const quarter = t.match(/\b(?:q|kuartal\s*|triwulan\s*)([1-4])\b(?:\s+(\d{4}))?/);
  if (quarter) {
    const qn = Number(quarter[1]);
    const year = quarter[2] ? Number(quarter[2]) : endYear;
    return hit(quarter[0], {
      from: monthRange(year, (qn - 1) * 3).from,
      to: monthRange(year, qn * 3 - 1).to,
    });
  }

  // --- relative phrases, all anchored to the last day WITH DATA
  const e = parse(end);
  const relatives: [RegExp, () => { from: string; to: string }][] = [
    [/\bhari\s+ini\b|\bhr\s+ini\b/, () => ({ from: end, to: end })],
    [/\bkemarin\b|\bkemaren\b/, () => ({ from: shift(end, -1), to: shift(end, -1) })],
    [/\bminggu\s+ini\b|\bpekan\s+ini\b/, () => weekRange(end)],
    [
      /\bminggu\s+lalu\b|\bpekan\s+lalu\b|\bminggu\s+kemarin\b/,
      () => weekRange(shift(weekRange(end).from, -1)),
    ],
    [
      /\bbulan\s+ini\b/,
      () => ({ from: monthRange(e.getUTCFullYear(), e.getUTCMonth()).from, to: end }),
    ],
    [
      /\bbulan\s+lalu\b|\bbulan\s+kemarin\b/,
      () => monthRange(e.getUTCFullYear(), e.getUTCMonth() - 1),
    ],
    [
      /\btahun\s+ini\b/,
      () => ({ from: monthRange(e.getUTCFullYear(), 0).from, to: end }),
    ],
    [/\btahun\s+lalu\b/, () => ({ from: `${endYear - 1}-01-01`, to: `${endYear - 1}-12-31` })],
    [/\bsepanjang\s+(waktu|data)\b|\bkeseluruhan\b|\btotal\s+semua\b|\bsemua\s+waktu\b/,
      () => ({ from: extent.start, to: extent.end })],
  ];

  for (const [re, build] of relatives) {
    const m = t.match(re);
    if (m) return hit(m[0], build());
  }

  return null;
}

/** True when the sentence names a period at all, in or out of the data. */
export function recognisedTimePhrase(text: string, extent: Extent): boolean {
  return rawRange(text, extent) !== null;
}

/**
 * The period the sentence names, clipped to the days that have data. Null when
 * no period was named, or when the one named lies entirely outside the data.
 */
export function extractRange(text: string, extent: Extent): RangeMatch | null {
  const raw = rawRange(text, extent);
  if (!raw) return null;
  const clipped = clip(raw, extent);
  if (!clipped) return null;
  return {
    ...clipped,
    clipped: clipped.from !== raw.from || clipped.to !== raw.to,
    phrase: raw.phrase,
  };
}

// --- entity matching ---------------------------------------------------------

/**
 * Levenshtein distance, capped: we only ever ask "is this within 2 edits", so
 * the full matrix is never worth building for long strings.
 */
function withinEdits(a: string, b: string, max: number): boolean {
  if (Math.abs(a.length - b.length) > max) return false;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const curr = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
      best = Math.min(best, curr[j]);
    }
    if (best > max) return false;
    prev = curr;
  }
  return prev[b.length] <= max;
}

/**
 * Words that appear in a venue name without identifying it.
 *
 * "OLS SES - PACIFIC PLACE MALL" is typed as "Pacific Place": requiring every
 * word of the stored name would reject that, and requiring only some words
 * would let "mall" alone match three different stores. Stripping the generic
 * half and requiring all of what remains is the rule that gets both right.
 */
const GENERIC_NAME_WORDS = new Set([
  "levis", "levi", "ols", "ses",
  // Note "park" is absent on purpose: "CENTRAL PARK" needs it to stay distinctive.
  "mall", "mal", "plaza", "plasa", "square", "city", "town",
  "store", "shop", "outlet", "toko", "cabang", "gerai",
]);

/**
 * Match a catalogue entry inside the sentence.
 *
 * Substring first — store names here read like "LEVI'S GRAND INDONESIA", and a
 * user types "grand indonesia". Fuzzy matching is applied per word and only to
 * words long enough for an edit distance to mean something, so "toko" never
 * fuzzily matches "toka".
 */
function findEntities<T>(
  text: string,
  entries: T[],
  nameOf: (entry: T) => string,
): T[] {
  const t = normalise(text);
  const words = t.split(" ");
  const found: T[] = [];

  for (const entry of entries) {
    const name = normalise(nameOf(entry));
    if (!name) continue;

    // Drop the chain prefix so "levi's" in a store name is not what matches.
    const distinctive = name.replace(/^levi ?s\b/, "").trim() || name;

    if (t.includes(distinctive)) {
      found.push(entry);
      continue;
    }

    // Every significant word of the name must appear (in any order), with a
    // small typo allowance. "grand indonesia" matches "GRAND INDONESIA MALL".
    const significant = distinctive.split(" ").filter((w) => w.length >= 4);
    const parts = significant.filter((w) => !GENERIC_NAME_WORDS.has(w));
    if (
      parts.length &&
      parts.every((part) => words.some((w) => w === part || (w.length >= 5 && withinEdits(w, part, 1))))
    ) {
      found.push(entry);
    }
  }

  return found;
}

export interface Slots {
  range: RangeMatch | null;
  storeIds: number[];
  categories: string[];
  membership: "member" | "guest" | null;
  limit?: number;
  /** True when a time phrase was recognised but fell outside the data. */
  outOfRange: boolean;
}

export function extractSlots(text: string, extent: Extent, cat: Catalog): Slots {
  const t = normalise(text);

  const range = extractRange(text, extent);
  // "januari" parses fine and then clips to nothing. Without this the answer
  // would quietly fall back to the filter bar's range and report June's figures
  // to somebody who asked about January.
  const outOfRange = range === null && recognisedTimePhrase(text, extent);

  const stores = findEntities(text, cat.stores, (s) => s.name);
  const categories = findEntities(text, cat.categories, (c) => c);

  const membership = /\bmember\b|\bmembership\b|\bloyalty\b/.test(t)
    ? /\bnon[\s-]?member\b|\bbukan\s+member\b|\btanpa\s+member\b|\bguest\b/.test(t)
      ? ("guest" as const)
      : ("member" as const)
    : /\bguest\b|\bnon[\s-]?member\b/.test(t)
      ? ("guest" as const)
      : null;

  // "top 5", "5 besar", "10 toko teratas". The optional noun in the middle is
  // an explicit list rather than \w+, so "15 juli tertinggi" cannot be read as
  // a limit of fifteen.
  const limitMatch =
    t.match(/\b(?:top|teratas|besar|terbesar)\s+(\d{1,2})\b/) ??
    t.match(
      /\b(\d{1,2})\s+(?:(?:toko|store|outlet|cabang|produk|barang|item|sku|kategori|spg|kasir|staff|nama)\s+)?(?:teratas|besar|terbesar|terlaris|tertinggi)\b/,
    );
  const limit = limitMatch ? Number(limitMatch[1]) : undefined;

  return {
    range,
    storeIds: stores.map((s) => s.id),
    categories,
    membership,
    limit,
    outOfRange,
  };
}

/**
 * Fold the slots onto the filters the dashboard currently has.
 *
 * Anything the sentence did not mention is inherited, so "produk terlaris"
 * respects the date range and store the reader already picked in the filter bar
 * — the assistant answers about what is on screen, not about everything.
 */
export function applySlots(base: Filters, slots: Slots): Filters {
  return {
    from: slots.range ? slots.range.from : base.from,
    to: slots.range ? slots.range.to : base.to,
    stores: slots.storeIds.length ? slots.storeIds : base.stores,
    categories: slots.categories.length ? slots.categories : base.categories,
    membership: slots.membership ?? base.membership,
    associate: base.associate,
  };
}
