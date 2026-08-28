// =============================================================================
// Pulling the arguments out of a sentence.
//
// The finance assistant needs a different shape of slot from the sales one. A
// sales question is about a RANGE ("penjualan bulan lalu"); a finance question
// is almost always about a CUT-OFF ("berapa hutang per akhir Juli"). So the
// primary slot here is a single date, and the movement window is derived from
// it rather than parsed separately.
//
// Everything is anchored to a caller-supplied "today" rather than to the wall
// clock, so the tests do not drift and a question asked at 23:59 does not mean
// something different a minute later.
// =============================================================================

import type { Catalog, CatalogAccount, CatalogPartner } from "@/lib/agent/catalog";
import { endOfMonth, startOfMonth } from "@/lib/finance-filters";

export function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const DAY = 86_400_000;
const iso = (d: Date) => d.toISOString().slice(0, 10);
const parse = (s: string) => new Date(`${s}T00:00:00Z`);
const shift = (s: string, days: number) => iso(new Date(parse(s).getTime() + days * DAY));

const MONTHS: Record<string, number> = {
  januari: 1, january: 1, jan: 1,
  februari: 2, february: 2, feb: 2, pebruari: 2,
  maret: 3, march: 3, mar: 3,
  april: 4, apr: 4,
  mei: 5, may: 5,
  juni: 6, june: 6, jun: 6,
  juli: 7, july: 7, jul: 7,
  agustus: 8, august: 8, agu: 8, ags: 8, aug: 8,
  september: 9, sept: 9, sep: 9,
  oktober: 10, october: 10, okt: 10, oct: 10,
  november: 11, nov: 11, nopember: 11,
  desember: 12, december: 12, des: 12, dec: 12,
};

const MONTH_WORDS = Object.keys(MONTHS).join("|");

export interface AsOfMatch {
  asOf: string;
  /** How the phrase was understood, echoed back so the reader can check it. */
  label: string;
}

/**
 * Read a cut-off out of the sentence.
 *
 * Order matters: the most specific patterns are tried first, so "akhir bulan
 * lalu" is not consumed by the bare "bulan lalu" rule and turned into the first
 * of the month.
 */
export function extractAsOf(text: string, today: string): AsOfMatch | null {
  const t = normalise(text);

  // --- explicit dates -------------------------------------------------------
  const ymd = t.match(/\b(20\d{2})[\s-](\d{1,2})[\s-](\d{1,2})\b/);
  if (ymd) {
    const [, y, m, d] = ymd;
    const value = `${y}-${String(Number(m)).padStart(2, "0")}-${String(Number(d)).padStart(2, "0")}`;
    return { asOf: value, label: `per ${value}` };
  }

  const dmy = t.match(new RegExp(`\\b(\\d{1,2})\\s+(${MONTH_WORDS})\\s*(20\\d{2})?\\b`));
  if (dmy) {
    const day = Number(dmy[1]);
    const month = MONTHS[dmy[2]];
    const year = dmy[3] ? Number(dmy[3]) : Number(today.slice(0, 4));
    if (day >= 1 && day <= 31) {
      const value = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      return { asOf: value, label: `per ${value}` };
    }
  }

  // --- end of a named month -------------------------------------------------
  const endOfNamed = t.match(new RegExp(`\\b(akhir|per|sampai|hingga|s\\s*d)\\s+(${MONTH_WORDS})\\s*(20\\d{2})?\\b`));
  if (endOfNamed) {
    const month = MONTHS[endOfNamed[2]];
    const year = endOfNamed[3] ? Number(endOfNamed[3]) : Number(today.slice(0, 4));
    const value = endOfMonth(`${year}-${String(month).padStart(2, "0")}-01`);
    return { asOf: value, label: `akhir ${endOfNamed[2]} ${year}` };
  }

  // --- relative months ------------------------------------------------------
  if (/\bakhir\s+bulan\s+(lalu|kemarin|sebelumnya)\b/.test(t) || /\bbulan\s+lalu\b/.test(t)) {
    const d = parse(today);
    const value = iso(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 0)));
    return { asOf: value, label: "akhir bulan lalu" };
  }
  if (/\bakhir\s+bulan\s+ini\b/.test(t)) {
    return { asOf: endOfMonth(today), label: "akhir bulan ini" };
  }
  if (/\bakhir\s+tahun\s+lalu\b/.test(t)) {
    const year = Number(today.slice(0, 4)) - 1;
    return { asOf: `${year}-12-31`, label: `akhir ${year}` };
  }

  // --- a bare month name ----------------------------------------------------
  const named = t.match(new RegExp(`\\b(${MONTH_WORDS})\\s*(20\\d{2})?\\b`));
  if (named) {
    const month = MONTHS[named[1]];
    const year = named[2] ? Number(named[2]) : Number(today.slice(0, 4));
    const value = endOfMonth(`${year}-${String(month).padStart(2, "0")}-01`);
    return { asOf: value, label: `akhir ${named[1]} ${year}` };
  }

  // --- today / yesterday ----------------------------------------------------
  if (/\b(hari\s+ini|sekarang|saat\s+ini|terkini|current)\b/.test(t)) {
    return { asOf: today, label: "hari ini" };
  }
  if (/\bkemarin\b/.test(t)) {
    return { asOf: shift(today, -1), label: "kemarin" };
  }

  return null;
}

/** Whether the sentence mentions a period at all, however vaguely. */
export function mentionsPeriod(text: string, today: string): boolean {
  return extractAsOf(text, today) !== null;
}

// --- entity resolution --------------------------------------------------------

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
 * Words that appear in a company or account name without identifying it.
 *
 * Nearly every vendor here is "PT SOMETHING TBK", and nearly every clearing
 * account contains the word "clearing". Requiring every word would make
 * "sinar eka" fail against "PT SINAR EKA SELARAS TBK"; requiring any word would
 * let "pt" match all of them. Stripping the generic half and requiring all of
 * what remains gets both right.
 */
const GENERIC_NAME_WORDS = new Set([
  "pt", "cv", "tbk", "persero", "indonesia", "jakarta",
  "account", "accounts", "akun", "rekening",
  "third", "parties", "party", "related",
  "the", "dan", "and", "of", "for",
]);

function findEntities<T>(text: string, entries: T[], nameOf: (entry: T) => string): T[] {
  const t = normalise(text);
  const words = t.split(" ");
  const found: T[] = [];

  for (const entry of entries) {
    const name = normalise(nameOf(entry));
    if (!name) continue;

    if (name.length >= 4 && t.includes(name)) {
      found.push(entry);
      continue;
    }

    const significant = name.split(" ").filter((w) => w.length >= 4);
    const parts = significant.filter((w) => !GENERIC_NAME_WORDS.has(w));
    if (
      parts.length &&
      parts.every((part) =>
        words.some((w) => w === part || (w.length >= 5 && withinEdits(w, part, 1))),
      )
    ) {
      found.push(entry);
    }
  }

  return found;
}

export interface Slots {
  asOf: AsOfMatch | null;
  accountIds: number[];
  partnerIds: number[];
  limit?: number;
}

export function extractSlots(text: string, today: string, cat: Catalog): Slots {
  const t = normalise(text);

  // An account code typed verbatim is the least ambiguous thing a user can do,
  // so it wins over any name match.
  const codes = Array.from(t.matchAll(/\b(\d{6,10})\b/g)).map((m) => m[1]);
  const byCode = codes
    .map((c) => cat.accounts.find((a) => a.code === c))
    .filter((a): a is CatalogAccount => Boolean(a));

  const byName: CatalogAccount[] = byCode.length
    ? []
    : findEntities(text, cat.accounts, (a) => a.name);
  const accounts = [...byCode, ...byName];

  const partners: CatalogPartner[] = findEntities(text, cat.partners, (p) => p.name);

  const limitMatch = t.match(/\b(?:top|teratas|pertama|sebanyak)\s+(\d{1,2})\b/);
  const limit = limitMatch ? Number(limitMatch[1]) : undefined;

  return {
    asOf: extractAsOf(text, today),
    // A question naming twenty accounts is a question about all of them; the
    // skills clamp anyway, but keeping the list short keeps the SQL sane.
    accountIds: accounts.slice(0, 8).map((a) => a.id),
    partnerIds: partners.slice(0, 8).map((p) => p.id),
    limit,
  };
}

/** The movement window a trial-balance style question implies. */
export function movementFrom(asOf: string): string {
  return startOfMonth(asOf);
}
