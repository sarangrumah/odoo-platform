// =============================================================================
// The global filter state, finance edition.
//
// The sales cockpit filters a RANGE — "how did we sell between these two
// dates". Finance almost always asks a different shape of question: "what was
// still open ON this date". So the primary control here is a single cut-off,
// `asOf`, and `from` exists only for the two reports that genuinely need a
// window (trial balance movement, and the ledger activity charts).
//
// Like the sales cockpit, the state lives in the URL search params rather than
// in React state, so every view is a shareable link — which matters more here,
// not less: "the number I am looking at" is an argument an accountant needs to
// be able to send to someone else without ambiguity.
// =============================================================================

/** The three layouts GL Open Items walks through, mirroring Odoo's report. */
export const LAYOUTS = ["summary", "summary_partner", "detail"] as const;
export type Layout = (typeof LAYOUTS)[number];

export interface FinanceFilters {
  /** The cut-off. Everything as-of is measured here. */
  asOf: string;
  /** Start of the movement window. Only trial balance and activity use it. */
  from: string;
  companies: number[];
  accounts: number[];
  partners: number[];
  journals: number[];
  layout: Layout;
  /**
   * Which counterparty the open-items detail is narrowed to. `"none"` means
   * the rows that carry no partner at all — a real choice, distinct from "all".
   */
  focusPartner: number | "none" | null;
}

type Params = Record<string, string | string[] | undefined>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function list(value: string | string[] | undefined): string[] {
  const raw = Array.isArray(value) ? value : value ? [value] : [];
  return raw.flatMap((v) => v.split(",")).map((v) => v.trim()).filter(Boolean);
}

function ids(value: string | string[] | undefined): number[] {
  return list(value).map(Number).filter((n) => Number.isInteger(n) && n > 0);
}

/** Today in Asia/Jakarta — the books are kept in local time, not UTC. */
export function today(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/** First day of the month `iso` falls in. */
export function startOfMonth(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

/** Last day of the month `iso` falls in. */
export function endOfMonth(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).toISOString().slice(0, 10);
}

/** `iso` shifted back by `days` whole days. */
export function minusDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(d.getTime() - days * 86_400_000).toISOString().slice(0, 10);
}

/** Whole days between two ISO dates, inclusive of both ends. */
export function daysBetween(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00Z`).getTime();
  const b = new Date(`${to}T00:00:00Z`).getTime();
  return Math.round((b - a) / 86_400_000);
}

export function parseFinanceFilters(params: Params, defaultCompanies: number[] = []): FinanceFilters {
  const rawAsOf = first(params.asOf);
  const asOf = rawAsOf && ISO_DATE.test(rawAsOf) ? rawAsOf : today();

  const rawFrom = first(params.from);
  const from = rawFrom && ISO_DATE.test(rawFrom) ? rawFrom : startOfMonth(asOf);

  const rawLayout = first(params.layout) as Layout | undefined;
  const layout = rawLayout && (LAYOUTS as readonly string[]).includes(rawLayout) ? rawLayout : "summary";

  const rawFocus = first(params.focusPartner);
  let focusPartner: FinanceFilters["focusPartner"] = null;
  if (rawFocus === "none") focusPartner = "none";
  else if (rawFocus && Number.isInteger(Number(rawFocus)) && Number(rawFocus) > 0) {
    focusPartner = Number(rawFocus);
  }

  const companies = ids(params.companies);

  return {
    asOf,
    // A movement window that runs backwards would silently return nothing;
    // clamp rather than error, and let the filter bar show what it did.
    from: from > asOf ? startOfMonth(asOf) : from,
    companies: companies.length ? companies : defaultCompanies,
    accounts: ids(params.accounts),
    partners: ids(params.partners),
    journals: ids(params.journals),
    layout,
    focusPartner,
  };
}

export function serialiseFinanceFilters(f: FinanceFilters, defaults: { asOf: string }): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.asOf !== defaults.asOf) sp.set("asOf", f.asOf);
  if (f.from !== startOfMonth(f.asOf)) sp.set("from", f.from);
  if (f.accounts.length) sp.set("accounts", f.accounts.join(","));
  if (f.partners.length) sp.set("partners", f.partners.join(","));
  if (f.journals.length) sp.set("journals", f.journals.join(","));
  if (f.layout !== "summary") sp.set("layout", f.layout);
  if (f.focusPartner !== null) sp.set("focusPartner", String(f.focusPartner));
  return sp;
}
