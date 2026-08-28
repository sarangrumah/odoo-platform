// =============================================================================
// The foundations every other query stands on.
//
// Three things live here because getting any of them wrong makes the whole
// dashboard disagree with Odoo:
//
//   1. `rootCompanyId` — Odoo 19 stores `account_account.code` in a JSONB
//      column `code_store` keyed by the ROOT company id. There is no `code`
//      column to read.
//   2. `LEDGER_SCOPE` — the predicate `custom.report.engine._get_move_lines_query`
//      applies to everything that imitates the trial balance or the general
//      ledger. Notably NOT applied by the aged reports; see ap.ts.
//   3. `openLinesAsOf` — the as-of residual, rebuilt from the reconciliations
//      that had actually happened by the cut-off. This is what makes a figure
//      tie to the ledger at period end instead of to today.
//
// Verified against prd_levis_begbal on 2026-08-28: 173.608 move lines, 29.329
// partial reconciliations, one company (id 1, root 1), IDR rounding 0.01.
// =============================================================================

import { cache } from "react";

import { q, num } from "@/lib/db";
import { IDR_ROUNDING } from "@/lib/money";

export interface Company {
  id: number;
  name: string;
  rootId: number;
  currencyId: number;
  fiscalyearLockDate: string | null;
  taxLockDate: string | null;
  saleLockDate: string | null;
  purchaseLockDate: string | null;
  hardLockDate: string | null;
}

/**
 * Every active company, with its root resolved from `parent_path`.
 *
 * `parent_path` is materialised by Odoo's `_parent_store` as "1/", "1/3/" and
 * so on, so the first segment is the root. prd_levis_begbal has exactly one
 * company today, but reading it rather than hard-coding 1 is what keeps the
 * account-code expression correct if a second is ever added.
 */
export const companies = cache(async (): Promise<Company[]> => {
  const rows = await q<Record<string, string | null>>(
    `SELECT c.id,
            c.name,
            NULLIF(split_part(COALESCE(c.parent_path, c.id || '/'), '/', 1), '')::int AS root_id,
            c.currency_id,
            c.fiscalyear_lock_date,
            c.tax_lock_date,
            c.sale_lock_date,
            c.purchase_lock_date,
            c.hard_lock_date
       FROM res_company c
      WHERE c.active
      ORDER BY c.id`,
  );

  return rows.map((r) => ({
    id: num(r.id),
    name: String(r.name ?? ""),
    // Fall back to the company itself: a row with no parent_path is its own root.
    rootId: num(r.root_id) || num(r.id),
    currencyId: num(r.currency_id),
    fiscalyearLockDate: r.fiscalyear_lock_date ? String(r.fiscalyear_lock_date) : null,
    taxLockDate: r.tax_lock_date ? String(r.tax_lock_date) : null,
    saleLockDate: r.sale_lock_date ? String(r.sale_lock_date) : null,
    purchaseLockDate: r.purchase_lock_date ? String(r.purchase_lock_date) : null,
    hardLockDate: r.hard_lock_date ? String(r.hard_lock_date) : null,
  }));
});

/** The company the dashboard defaults to when the URL names none. */
export const defaultCompanyIds = cache(async (): Promise<number[]> => {
  return (await companies()).map((c) => c.id);
});

/**
 * The root company whose key unlocks `code_store`.
 *
 * With several companies in scope Odoo resolves the code per account, in the
 * company that owns it (`custom.report.engine._account_code`). Every account in
 * this database belongs to the single root, so one key is enough — but the
 * moment a second root appears this must become a per-account lookup, and the
 * assertion below is what will say so out loud instead of silently blanking
 * every account code.
 */
export const rootCompanyId = cache(async (): Promise<number> => {
  const roots = new Set((await companies()).map((c) => c.rootId));
  if (roots.size > 1) {
    console.warn(
      `[finance] ${roots.size} root companies present; account codes resolve against the lowest. ` +
        `Move to a per-account code lookup before trusting the Code column.`,
    );
  }
  return Math.min(...roots);
});

/**
 * The account code, read out of the company-dependent JSONB column.
 *
 * Pass the placeholder that carries the root company id, bound as TEXT — JSONB
 * keys are strings, and `code_store ->> 1` is a different operator that would
 * index the object as an array and return null for every account.
 */
export function accountCodeSql(rootParam: string, alias = "aa"): string {
  return `${alias}.code_store ->> ${rootParam}`;
}

/** Account and journal names are translatable, so they are JSONB too. */
export function accountNameSql(alias = "aa"): string {
  return `COALESCE(${alias}.name ->> 'en_US', ${alias}.name ->> 'id_ID', '')`;
}
export function journalNameSql(alias = "aj"): string {
  return `COALESCE(${alias}.name ->> 'en_US', ${alias}.name ->> 'id_ID', '')`;
}

/**
 * The predicate the accounting engine applies to the general ledger.
 *
 * Mirrors `custom.report.engine._get_move_lines_query`, including the journal
 * exclusion — a journal flagged `x_custom_report_excluded` is deliberately kept
 * out of the trial balance and the ledger. No journal carries the flag in
 * prd_levis_begbal today; the filter stays so that the day one does, the
 * dashboard moves with the reports instead of drifting from them.
 *
 * Do NOT reuse this for aged receivable/payable. Those reports read
 * `account.move.line` directly and apply no journal exclusion, and adding one
 * here would make the aging disagree with Odoo. See ap.ts.
 */
export const LEDGER_SCOPE = `
      aml.parent_state = 'posted'
  AND aml.company_id = ANY($COMPANIES$::int[])
  AND aml.account_id IS NOT NULL
  AND aml.journal_id NOT IN (SELECT id FROM account_journal WHERE x_custom_report_excluded)`;

export interface OpenLine {
  id: number;
  accountId: number;
  partnerId: number | null;
  currencyId: number | null;
  date: string;
  dateMaturity: string | null;
  balance: number;
  /** Balance less everything reconciled against it on or before the cut-off. */
  residualAsOf: number;
  moveId: number;
  moveName: string;
  ref: string;
}

export interface AsOfScope {
  asOf: string;
  companies: number[];
  /** Restrict to these accounts. Always set for detail — see the note below. */
  accountIds?: number[];
  /** Restrict to accounts of these types instead of by id. */
  accountTypes?: string[];
  rounding: number;
}

/**
 * The as-of residual query, shared by every open-items figure.
 *
 * Two decisions carry the whole thing, both taken from
 * `custom.report.gl.open.items`:
 *
 * `reconciled` is NOT filtered out. A line settled after the cut-off was still
 * open at the cut-off, and dropping it would understate the balance — that is
 * the entire reason the report exists.
 *
 * A partial only counts when BOTH of its sides are posted. Crediting the posted
 * side of a partial whose counterpart is still a draft would report the line as
 * settled against something that is not in the books. prd_levis_begbal has none
 * of these today (checked 2026-08-28), which is precisely why the guard has to
 * be written now rather than after one appears.
 *
 * The counterpart is judged on the ledger, not on the report filters: a line
 * narrowed away by an account or partner filter is still a real settlement.
 * That is why `posted_partial` is not correlated to `cand`.
 *
 * Shape note: the settlement is gathered with UNION ALL and then aggregated,
 * never as `LEFT JOIN account_partial_reconcile ON (debit_move_id = c.id OR
 * credit_move_id = c.id)`. Postgres cannot use an index for an OR across two
 * columns and that form degrades to a nested loop over 173k lines.
 */
export function openLinesAsOfSql(scope: AsOfScope): { text: string; params: unknown[] } {
  const params: unknown[] = [];
  const p = (v: unknown) => {
    params.push(v);
    return `$${params.length}`;
  };

  const companiesP = p(scope.companies);
  const asOfP = p(scope.asOf);
  const accountsP = p(scope.accountIds?.length ? scope.accountIds : null);
  const typesP = p(scope.accountTypes?.length ? scope.accountTypes : null);
  const roundingP = p(scope.rounding);

  const text = `
    WITH cand AS (
      SELECT aml.id, aml.account_id, aml.partner_id, aml.currency_id, aml.date,
             aml.date_maturity, aml.balance, aml.move_id, aml.move_name,
             COALESCE(aml.ref, '') AS ref
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY(${companiesP}::int[])
         AND aa.reconcile
         AND aml.parent_state = 'posted'
         AND aml.date <= ${asOfP}::date
         AND (${accountsP}::int[] IS NULL OR aml.account_id = ANY(${accountsP}::int[]))
         AND (${typesP}::text[] IS NULL OR aa.account_type = ANY(${typesP}::text[]))
    ),
    posted_partial AS (
      SELECT p.debit_move_id, p.credit_move_id, p.amount
        FROM account_partial_reconcile p
        JOIN account_move_line dl ON dl.id = p.debit_move_id
        JOIN account_move_line cl ON cl.id = p.credit_move_id
       WHERE p.max_date <= ${asOfP}::date
         AND dl.parent_state = 'posted'
         AND cl.parent_state = 'posted'
    ),
    settled AS (
      -- Signed like the balance column so it subtracts directly: a line on the
      -- debit side of a partial had that much of its debit cleared, and the
      -- credit side that much of its credit.
      SELECT line_id, SUM(amt) AS settled
        FROM (
          SELECT debit_move_id, amount FROM posted_partial
          UNION ALL
          SELECT credit_move_id, -amount FROM posted_partial
        ) s(line_id, amt)
       GROUP BY line_id
    )
    SELECT c.id, c.account_id, c.partner_id, c.currency_id, c.date, c.date_maturity,
           c.balance, c.move_id, c.move_name, c.ref,
           c.balance - COALESCE(s.settled, 0.0) AS residual_asof
      FROM cand c
      LEFT JOIN settled s ON s.line_id = c.id
     WHERE ABS(c.balance - COALESCE(s.settled, 0.0)) >= ${roundingP}::numeric / 2
     ORDER BY c.account_id, c.date, c.id`;

  return { text, params };
}

export function toOpenLine(r: Record<string, string | null>): OpenLine {
  return {
    id: num(r.id),
    accountId: num(r.account_id),
    partnerId: r.partner_id === null ? null : num(r.partner_id),
    currencyId: r.currency_id === null ? null : num(r.currency_id),
    date: String(r.date ?? ""),
    dateMaturity: r.date_maturity ? String(r.date_maturity) : null,
    balance: num(r.balance),
    residualAsOf: num(r.residual_asof),
    moveId: num(r.move_id),
    moveName: String(r.move_name ?? ""),
    ref: String(r.ref ?? ""),
  };
}

/** Run the as-of query and hand back typed rows. */
export async function openLinesAsOf(scope: AsOfScope): Promise<OpenLine[]> {
  const { text, params } = openLinesAsOfSql(scope);
  const rows = await q<Record<string, string | null>>(text, params);
  return rows.map(toOpenLine);
}

/**
 * The company currency's rounding, as Odoo stores it (IDR: 0.01).
 *
 * Lives here rather than in money.ts so that module stays pure and the netting
 * can be unit-tested without a database or a React runtime. `cache` dedupes
 * within one request — every query module asks for it.
 */
export const companyRounding = cache(async (companyId: number): Promise<number> => {
  const rows = await q<Record<string, string>>(
    `SELECT rc.rounding
       FROM res_company c
       JOIN res_currency rc ON rc.id = c.currency_id
      WHERE c.id = $1`,
    [companyId],
  );
  const rounding = num(rows[0]?.rounding);
  return rounding > 0 ? rounding : IDR_ROUNDING;
});
