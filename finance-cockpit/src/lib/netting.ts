// =============================================================================
// FIFO netting — a line-for-line port of `custom.report.gl.open.items`.
//
// The ledger alone does not answer "what is still owed". On the clearing
// accounts this exists for, most matching never runs through
// `account.partial.reconcile` at all: GR/IR is settled by the vendor bill
// journal, POS suspense by the daily clearing entry. Those debits and credits
// cancel to the rupiah yet stay `reconciled = false`. In prd_levis_begbal that
// is 58.840 lines on GR/IR textile alone, netting to a fraction of that.
//
// So after the as-of residual is known, the remaining debits and credits of
// each account/partner/currency are offset oldest against oldest, and only what
// survives is reported.
//
// The invariant that makes this safe to trust: netting never changes the signed
// sum. Every step reduces one debit and raises one credit by the same amount,
// so `sum(outstanding)` always equals `sum(residualAsOf)`. The tie page asserts
// exactly that (check #8), and `tests/netting.test.ts` property-tests it.
// =============================================================================

import { isZero } from "@/lib/money";

export interface NettableRow {
  id: number;
  accountId: number;
  partnerId: number | null;
  currencyId: number | null;
  date: string;
  /** Signed. Mutated in place by the netting, hence `outstanding` below. */
  residualAsOf: number;
  outstanding: number;
  [key: string]: unknown;
}

/** Ordering contract: oldest first, ties broken by id — the same as Odoo's. */
function byAge(a: NettableRow, b: NettableRow): number {
  if (a.date !== b.date) return a.date < b.date ? -1 : 1;
  return a.id - b.id;
}

/**
 * Consume the oldest debit against the oldest credit, in place.
 *
 * Both lists must already be in date order. Two pointers, so a 58.000-line
 * GR/IR account costs one pass, not a cross product.
 */
export function fifo(debits: NettableRow[], credits: NettableRow[], rounding: number): void {
  let d = 0;
  let c = 0;
  while (d < debits.length && c < credits.length) {
    const debit = debits[d];
    const credit = credits[c];
    const taken = Math.min(debit.outstanding, -credit.outstanding);
    debit.outstanding -= taken;
    credit.outstanding += taken;
    if (isZero(debit.outstanding, rounding)) {
      debit.outstanding = 0;
      d += 1;
    }
    if (isZero(credit.outstanding, rounding)) {
      credit.outstanding = 0;
      c += 1;
    }
  }
}

function groupKey(row: NettableRow): string {
  return `${row.accountId}|${row.partnerId ?? ""}|${row.currencyId ?? ""}`;
}

/**
 * Offset what the ledger left standing, oldest against oldest.
 *
 * Two passes, and the order matters — the second sees what the first mutated:
 *
 *  1. inside one account/partner/currency, where a debit and a credit really do
 *     settle each other;
 *  2. across partners of the same account, but only for rows that carry NO
 *     partner at all. GR/IR is exactly that case: in prd_levis_begbal 36.839 of
 *     the 75.546 posted lines on account 778 have no partner, because the
 *     goods-receipt credits are booked without one while the bill debits name
 *     the vendor. Pass 1 alone would print both sides of a pair that cancels.
 *
 * A line without a partner makes no claim about who owes it, so there is
 * nothing to protect by keeping it apart. Two lines that BOTH name a partner
 * are never netted against each other.
 *
 * Returns the surviving rows, grouped by account. Rows that net to zero are
 * dropped, and an account whose rows all net to zero disappears entirely —
 * which is the point.
 */
export function netOffsetting(rows: NettableRow[], rounding: number): Map<number, NettableRow[]> {
  for (const row of rows) row.outstanding = row.residualAsOf;

  // --- Pass 1: within account / partner / currency --------------------------
  const groups = new Map<string, NettableRow[]>();
  for (const row of rows) {
    const key = groupKey(row);
    const bucket = groups.get(key);
    if (bucket) bucket.push(row);
    else groups.set(key, [row]);
  }

  for (const entries of groups.values()) {
    entries.sort(byAge);
    fifo(
      entries.filter((e) => e.outstanding > 0),
      entries.filter((e) => e.outstanding < 0),
      rounding,
    );
  }

  // --- Pass 2: across partners, anonymous rows only -------------------------
  // Runs on the OUTPUT of pass 1, not on a fresh copy.
  const byAccountCurrency = new Map<string, NettableRow[]>();
  for (const row of rows) {
    if (isZero(row.outstanding, rounding)) continue;
    const key = `${row.accountId}|${row.currencyId ?? ""}`;
    const bucket = byAccountCurrency.get(key);
    if (bucket) bucket.push(row);
    else byAccountCurrency.set(key, [row]);
  }

  for (const entries of byAccountCurrency.values()) {
    entries.sort(byAge);
    const anonymous = entries.filter((e) => e.partnerId === null);
    if (!anonymous.length) continue;
    // Anonymous debits against every credit, then every debit against the
    // anonymous credits. Two calls, in this order, and each side is re-derived
    // at call time: the first call can zero an anonymous credit, and a list
    // captured beforehand would carry that spent row into the second.
    fifo(
      anonymous.filter((e) => e.outstanding > 0),
      entries.filter((e) => e.outstanding < 0),
      rounding,
    );
    fifo(
      entries.filter((e) => e.outstanding > 0),
      anonymous.filter((e) => e.outstanding < 0),
      rounding,
    );
  }

  // --- Collect survivors ----------------------------------------------------
  const survivors = new Map<number, NettableRow[]>();
  for (const row of rows) {
    if (isZero(row.outstanding, rounding)) continue;
    const bucket = survivors.get(row.accountId);
    if (bucket) bucket.push(row);
    else survivors.set(row.accountId, [row]);
  }
  for (const entries of survivors.values()) entries.sort(byAge);
  return survivors;
}

/**
 * Narrow netted rows to one counterparty.
 *
 * Applied AFTER the netting, never inside the query, and for a reason that is
 * easy to get wrong: partnerless rows offset across partners in pass 2, so
 * filtering the query first would leave them out of that pass and print a
 * larger remainder than the summary promised. `"none"` selects the rows that
 * carry no partner at all — a distinct answer, not "no filter".
 */
export function focusPartner(
  rows: NettableRow[],
  focus: number | "none" | null,
): NettableRow[] {
  if (focus === null) return rows;
  if (focus === "none") return rows.filter((r) => r.partnerId === null);
  return rows.filter((r) => r.partnerId === focus);
}
