// =============================================================================
// Accounts payable / receivable — aging, and what is waiting to be paid.
//
// The aging here is a line-for-line port of `custom.report.aged.receivable`
// (and its payable subclass), including two things that look like mistakes and
// are not:
//
//   1. NO journal exclusion. The aged reports read `account.move.line` directly
//      and never filter `x_custom_report_excluded`, unlike the trial balance.
//      Adding it here would make the aging disagree with Odoo.
//
//   2. `d_0_30` really means 1–30 days. `_classify_bucket` returns `not_due`
//      for `days <= 0` before the bucket table is consulted, so a document due
//      exactly on the cut-off is not overdue.
//
// Two variants are computed and BOTH are shown:
//
//   `parity`  — `reconciled = false` and the CURRENT `amount_residual`, exactly
//               what Odoo prints. A document settled after the cut-off already
//               appears reduced. This is the headline, because the promise is
//               that the dashboard ties to the report.
//   `asOf`    — residual rebuilt to the cut-off (queries/common.ts). Different
//               by design; the tie page prices the difference rather than
//               hiding it.
// =============================================================================

import { q, num } from "@/lib/db";

import { BUCKETS, classifyBucket, type BucketCode } from "@/lib/aging";
import {
  companyRounding,
  openLinesAsOf,
  rootCompanyId,
} from "@/lib/queries/common";

export { BUCKETS, classifyBucket };
export type { BucketCode };

/** The same seven-way split, in SQL. Kept beside the TS twin on purpose. */
const BUCKET_CASE = `
      CASE
        WHEN due IS NULL OR due >= $2::date THEN 'not_due'
        WHEN ($2::date - due) <= 0   THEN 'not_due'
        WHEN ($2::date - due) <= 30  THEN 'd_0_30'
        WHEN ($2::date - due) <= 60  THEN 'd_31_60'
        WHEN ($2::date - due) <= 90  THEN 'd_61_90'
        WHEN ($2::date - due) <= 180 THEN 'd_91_180'
        WHEN ($2::date - due) <= 365 THEN 'd_181_365'
        ELSE 'd_over_365'
      END`;

export type AgingSide = "payable" | "receivable";

const ACCOUNT_TYPE: Record<AgingSide, string> = {
  payable: "liability_payable",
  receivable: "asset_receivable",
};

export interface AgingRow {
  partnerId: number;
  partnerName: string;
  itemCount: number;
  maxOverdueDays: number;
  total: number;
  buckets: Record<BucketCode, number>;
}

function emptyBuckets(): Record<BucketCode, number> {
  return Object.fromEntries(BUCKETS.map((b) => [b.code, 0])) as Record<BucketCode, number>;
}

/**
 * Aged payable / receivable per counterparty — the parity variant.
 *
 * Deliberately `amount_residual` and `reconciled = false`, matching
 * `_open_lines` and `_build_summary_lines`. `amount_residual <> 0` reproduces
 * the report's `if not residual: continue`.
 */
export async function agingByPartner(side: AgingSide, scope: {
  asOf: string;
  companies: number[];
}): Promise<AgingRow[]> {
  const rows = await q<Record<string, string | null>>(
    `
    WITH open_lines AS (
      SELECT aml.partner_id, aml.amount_residual,
             COALESCE(aml.date_maturity, aml.date) AS due
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY($1::int[])
         AND aa.account_type = $3
         AND aml.parent_state = 'posted'
         AND aml.reconciled = false
         AND aml.date <= $2::date
         AND aml.amount_residual <> 0
    ),
    bucketed AS (
      SELECT o.*, ${BUCKET_CASE} AS bucket,
             GREATEST($2::date - o.due, 0) AS overdue_days
        FROM open_lines o
    )
    SELECT COALESCE(b.partner_id, 0) AS partner_id,
           COALESCE(rp.name, 'Tanpa lawan transaksi') AS partner_name,
           COUNT(*) AS item_count,
           MAX(b.overdue_days) AS max_overdue_days,
           SUM(b.amount_residual) AS total,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'not_due')    AS not_due,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_0_30')     AS d_0_30,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_31_60')    AS d_31_60,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_61_90')    AS d_61_90,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_91_180')   AS d_91_180,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_181_365')  AS d_181_365,
           SUM(b.amount_residual) FILTER (WHERE b.bucket = 'd_over_365') AS d_over_365
      FROM bucketed b
      LEFT JOIN res_partner rp ON rp.id = b.partner_id
     GROUP BY 1, 2
     ORDER BY ABS(SUM(b.amount_residual)) DESC`,
    [scope.companies, scope.asOf, ACCOUNT_TYPE[side]],
  );

  return rows.map((r) => ({
    partnerId: num(r.partner_id),
    partnerName: String(r.partner_name ?? ""),
    itemCount: num(r.item_count),
    maxOverdueDays: num(r.max_overdue_days),
    total: num(r.total),
    buckets: {
      not_due: num(r.not_due),
      d_0_30: num(r.d_0_30),
      d_31_60: num(r.d_31_60),
      d_61_90: num(r.d_61_90),
      d_91_180: num(r.d_91_180),
      d_181_365: num(r.d_181_365),
      d_over_365: num(r.d_over_365),
    },
  }));
}

export interface AgingDocument {
  moveId: number;
  docNo: string;
  reference: string;
  docDate: string;
  dueDate: string | null;
  overdueDays: number;
  bucket: BucketCode;
  accountCode: string;
  original: number;
  paid: number;
  outstanding: number;
}

/** One row per open document for a single counterparty — the detail layout. */
export async function agingDocuments(
  side: AgingSide,
  partnerId: number,
  scope: { asOf: string; companies: number[] },
): Promise<AgingDocument[]> {
  const rows = await q<Record<string, string | null>>(
    `
    WITH open_lines AS (
      SELECT aml.move_id, aml.move_name, COALESCE(aml.ref, '') AS ref, aml.date,
             aml.date_maturity, aml.balance, aml.amount_residual,
             aa.code_store ->> $4 AS account_code,
             COALESCE(aml.date_maturity, aml.date) AS due
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY($1::int[])
         AND aa.account_type = $3
         AND aml.parent_state = 'posted'
         AND aml.reconciled = false
         AND aml.date <= $2::date
         AND aml.amount_residual <> 0
         AND COALESCE(aml.partner_id, 0) = $5
    )
    SELECT o.*, ${BUCKET_CASE} AS bucket, GREATEST($2::date - o.due, 0) AS overdue_days
      FROM open_lines o
     ORDER BY o.due NULLS LAST, o.move_name`,
    [scope.companies, scope.asOf, ACCOUNT_TYPE[side], String(await rootCompanyId()), partnerId],
  );

  return rows.map((r) => ({
    moveId: num(r.move_id),
    docNo: String(r.move_name ?? ""),
    reference: String(r.ref ?? ""),
    docDate: String(r.date ?? ""),
    dueDate: r.date_maturity ? String(r.date_maturity) : null,
    overdueDays: num(r.overdue_days),
    bucket: String(r.bucket ?? "not_due") as BucketCode,
    accountCode: String(r.account_code ?? ""),
    original: num(r.balance),
    paid: num(r.balance) - num(r.amount_residual),
    outstanding: num(r.amount_residual),
  }));
}

export interface AgingTotals {
  total: number;
  buckets: Record<BucketCode, number>;
  itemCount: number;
  partnerCount: number;
}

export function totalsOf(rows: AgingRow[]): AgingTotals {
  const buckets = emptyBuckets();
  let total = 0;
  let itemCount = 0;
  for (const row of rows) {
    total += row.total;
    itemCount += row.itemCount;
    for (const b of BUCKETS) buckets[b.code] += row.buckets[b.code];
  }
  return { total, buckets, itemCount, partnerCount: rows.length };
}

/**
 * The as-of variant of the same aging, for the bridge on the tie page.
 *
 * Buckets are computed in TypeScript here rather than in SQL, because the rows
 * already come back from the shared as-of query and re-running the whole CTE
 * with a second bucket expression would be a second full sweep for nothing.
 */
export async function agingAsOfTotals(side: AgingSide, scope: {
  asOf: string;
  companies: number[];
}): Promise<AgingTotals> {
  const rounding = await companyRounding(scope.companies[0]);
  const lines = await openLinesAsOf({
    asOf: scope.asOf,
    companies: scope.companies,
    accountTypes: [ACCOUNT_TYPE[side]],
    rounding,
  });

  const buckets = emptyBuckets();
  const partners = new Set<number | null>();
  let total = 0;
  for (const line of lines) {
    const bucket = classifyBucket(line.dateMaturity ?? line.date, scope.asOf);
    buckets[bucket] += line.residualAsOf;
    total += line.residualAsOf;
    partners.add(line.partnerId);
  }
  return { total, buckets, itemCount: lines.length, partnerCount: partners.size };
}

export interface UnpaidBill {
  moveId: number;
  name: string;
  partnerName: string;
  invoiceDate: string;
  dueDate: string | null;
  paymentState: string;
  amountTotal: number;
  amountResidual: number;
}

/** Posted vendor bills that still owe something. */
export async function unpaidBills(scope: {
  asOf: string;
  companies: number[];
  limit?: number;
}): Promise<UnpaidBill[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT am.id, am.name, COALESCE(rp.name, '') AS partner_name,
            am.invoice_date, am.invoice_date_due, am.payment_state,
            am.amount_total_signed, am.amount_residual_signed
       FROM account_move am
       LEFT JOIN res_partner rp ON rp.id = am.commercial_partner_id
      WHERE am.company_id = ANY($1::int[])
        AND am.state = 'posted'
        AND am.move_type IN ('in_invoice', 'in_refund')
        AND am.payment_state IN ('not_paid', 'partial')
        AND am.date <= $2::date
      ORDER BY am.invoice_date_due NULLS LAST, am.name
      LIMIT $3`,
    [scope.companies, scope.asOf, scope.limit ?? 200],
  );

  return rows.map((r) => ({
    moveId: num(r.id),
    name: String(r.name ?? ""),
    partnerName: String(r.partner_name ?? ""),
    invoiceDate: String(r.invoice_date ?? ""),
    dueDate: r.invoice_date_due ? String(r.invoice_date_due) : null,
    paymentState: String(r.payment_state ?? ""),
    amountTotal: num(r.amount_total_signed),
    amountResidual: num(r.amount_residual_signed),
  }));
}

export interface DueWeek {
  weekStart: string;
  amount: number;
  itemCount: number;
}

/** What falls due in the four weeks after the cut-off. */
export async function upcomingDue(scope: {
  asOf: string;
  companies: number[];
  weeks?: number;
}): Promise<DueWeek[]> {
  const weeks = scope.weeks ?? 4;
  const rows = await q<Record<string, string | null>>(
    `SELECT (date_trunc('week', COALESCE(aml.date_maturity, aml.date)))::date AS week_start,
            SUM(aml.amount_residual) AS amount,
            COUNT(*) AS item_count
       FROM account_move_line aml
       JOIN account_account aa ON aa.id = aml.account_id
      WHERE aml.company_id = ANY($1::int[])
        AND aa.account_type = 'liability_payable'
        AND aml.parent_state = 'posted'
        AND aml.reconciled = false
        AND aml.amount_residual <> 0
        AND COALESCE(aml.date_maturity, aml.date) > $2::date
        AND COALESCE(aml.date_maturity, aml.date) <= ($2::date + ($3 || ' weeks')::interval)
      GROUP BY 1
      ORDER BY 1`,
    [scope.companies, scope.asOf, String(weeks)],
  );
  return rows.map((r) => ({
    weekStart: String(r.week_start ?? ""),
    amount: num(r.amount),
    itemCount: num(r.item_count),
  }));
}

export interface UnappliedPayment {
  paymentId: number;
  moveName: string;
  partnerName: string;
  date: string;
  amount: number;
  paymentType: string;
}

/**
 * Payments that have not been applied to anything.
 *
 * `account_payment.is_unapplied` is added by `custom_account_reconcile`; when
 * the column is absent (module not installed on this database) the caller gets
 * an empty list rather than an error, the way market.ts degrades in the sales
 * cockpit.
 */
export async function unappliedPayments(scope: {
  asOf: string;
  companies: number[];
}): Promise<UnappliedPayment[]> {
  try {
    const rows = await q<Record<string, string | null>>(
      `SELECT ap.id, am.name AS move_name, COALESCE(rp.name, '') AS partner_name,
              am.date, ap.amount, ap.payment_type
         FROM account_payment ap
         JOIN account_move am ON am.id = ap.move_id
         LEFT JOIN res_partner rp ON rp.id = am.partner_id
        WHERE am.company_id = ANY($1::int[])
          AND am.state = 'posted'
          AND am.date <= $2::date
          AND ap.is_unapplied
        ORDER BY am.date DESC, am.name
        LIMIT 200`,
      [scope.companies, scope.asOf],
    );
    return rows.map((r) => ({
      paymentId: num(r.id),
      moveName: String(r.move_name ?? ""),
      partnerName: String(r.partner_name ?? ""),
      date: String(r.date ?? ""),
      amount: num(r.amount),
      paymentType: String(r.payment_type ?? ""),
    }));
  } catch (error) {
    const code = (error as { code?: string }).code;
    // 42703 undefined_column, 42P01 undefined_table, 42501 insufficient_privilege
    if (code === "42703" || code === "42P01" || code === "42501") return [];
    throw error;
  }
}
