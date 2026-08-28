// =============================================================================
// Currency comparison, the way Odoo does it.
//
// Every "is this zero" decision in the accounting reports goes through
// `currency.is_zero()`, which is `abs(value) < rounding / 2` — NOT a fixed
// epsilon. In prd_levis_begbal the company currency is IDR with
// `res_currency.rounding = 0.01`, so the threshold is 0.005.
//
// Getting this wrong is not cosmetic. Compare against a smaller epsilon and
// float noise from tens of thousands of partial reconciliations survives as
// rows the ledger considers settled: GR/IR textile alone carries 58.840 open
// lines, and printing the residue of each one would bury the handful that are
// genuinely open. Compare against a larger one and real balances vanish.
//
// The rounding is read from the database on every request rather than baked in
// here, because it is a per-currency setting an accountant can change; see
// `companyRounding` in queries/common.ts. This module stays free of database
// and React imports so the netting can be unit-tested without either.
// =============================================================================

/** Fallback only. The real value is read by `companyRounding()` in common.ts. */
export const IDR_ROUNDING = 0.01;

/** Odoo's `currency.is_zero`. */
export function isZero(value: number, rounding: number): boolean {
  return Math.abs(value) < rounding / 2;
}

/** Odoo's `currency.round`, to the same multiple-of-rounding grid. */
export function roundTo(value: number, rounding: number): number {
  if (!(rounding > 0)) return value;
  return Math.round(value / rounding) * rounding;
}

/** True when two amounts are the same to the currency's precision. */
export function isEqual(a: number, b: number, rounding: number): boolean {
  return isZero(a - b, rounding);
}
