// =============================================================================
// GL Open Items — everything unsettled on a reconcilable account, as of a date.
//
// Mirrors `custom.report.gl.open.items`. Covers AR and AP but also the clearing
// accounts neither aged report reaches — GR/IR, advances, POS suspense — which
// is what "open items" means to Finance here.
//
// The work is split deliberately:
//
//   `summaryByAccount` needs NO netting. Netting never changes the signed sum,
//   so the outstanding total per account is a plain aggregate — one cheap query
//   that cannot be broken by a bug in the FIFO port. Every tie check rests on
//   it. Measured against prd_levis_begbal on 2026-08-28: 540 ms for all
//   accounts, and it reproduces `custom_reconcile_account` to the rupiah.
//
//   `nettedForAccount` is the expensive path and is ALWAYS scoped to one
//   account. That is safe because netting never crosses accounts, and it is the
//   same shape as Odoo's own drill-down.
// =============================================================================

import { cache } from "react";

import { q, num } from "@/lib/db";

import { netOffsetting, type NettableRow } from "@/lib/netting";
import {
  accountCodeSql,
  accountNameSql,
  companyRounding,
  openLinesAsOf,
  rootCompanyId,
  type AsOfScope,
} from "@/lib/queries/common";

export interface AccountSummary {
  accountId: number;
  code: string;
  name: string;
  accountType: string;
  /** Rows before netting — the ledger's own count of what is unsettled. */
  lineCount: number;
  outstanding: number;
  oldestDate: string | null;
  /** Whole days from the oldest open item to the cut-off. */
  oldestAgeDays: number;
  partnerCount: number;
  anonymousLines: number;
}

/**
 * Outstanding per reconcilable account, as of the cut-off. No FIFO.
 *
 * `lineCount` here is the pre-netting count on purpose: it says how many
 * entries the ledger still has standing, which is the number Finance uses to
 * judge whether an account needs cleaning. The post-netting count is a
 * different, more expensive question, answered per account by
 * `nettedForAccount`.
 */
export async function summaryByAccount(scope: {
  asOf: string;
  companies: number[];
  accountIds?: number[];
}): Promise<AccountSummary[]> {
  const root = await rootCompanyId();
  const rounding = await companyRounding(scope.companies[0]);

  const rows = await q<Record<string, string | null>>(
    `
    WITH cand AS (
      SELECT aml.id, aml.account_id, aml.partner_id, aml.date, aml.balance
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY($1::int[])
         AND aa.reconcile
         AND aml.parent_state = 'posted'
         AND aml.date <= $2::date
         AND ($3::int[] IS NULL OR aml.account_id = ANY($3::int[]))
    ),
    posted_partial AS (
      SELECT p.debit_move_id, p.credit_move_id, p.amount
        FROM account_partial_reconcile p
        JOIN account_move_line dl ON dl.id = p.debit_move_id
        JOIN account_move_line cl ON cl.id = p.credit_move_id
       WHERE p.max_date <= $2::date
         AND dl.parent_state = 'posted'
         AND cl.parent_state = 'posted'
    ),
    settled AS (
      SELECT line_id, SUM(amt) AS settled
        FROM (
          SELECT debit_move_id, amount FROM posted_partial
          UNION ALL
          SELECT credit_move_id, -amount FROM posted_partial
        ) s(line_id, amt)
       GROUP BY line_id
    ),
    open_lines AS (
      SELECT c.account_id, c.partner_id, c.date,
             c.balance - COALESCE(s.settled, 0.0) AS residual_asof
        FROM cand c
        LEFT JOIN settled s ON s.line_id = c.id
       WHERE ABS(c.balance - COALESCE(s.settled, 0.0)) >= $4::numeric / 2
    )
    SELECT o.account_id,
           ${accountCodeSql("$5")} AS code,
           ${accountNameSql()} AS name,
           aa.account_type,
           COUNT(*) AS line_count,
           SUM(o.residual_asof) AS outstanding,
           MIN(o.date) AS oldest_date,
           COUNT(DISTINCT o.partner_id) AS partner_count,
           COUNT(*) FILTER (WHERE o.partner_id IS NULL) AS anonymous_lines
      FROM open_lines o
      JOIN account_account aa ON aa.id = o.account_id
     GROUP BY o.account_id, aa.code_store, aa.name, aa.account_type
     ORDER BY ABS(SUM(o.residual_asof)) DESC`,
    [
      scope.companies,
      scope.asOf,
      scope.accountIds?.length ? scope.accountIds : null,
      rounding,
      String(root),
    ],
  );

  const cutoff = new Date(`${scope.asOf}T00:00:00Z`).getTime();
  return rows.map((r) => {
    const oldest = r.oldest_date ? String(r.oldest_date) : null;
    return {
      accountId: num(r.account_id),
      code: String(r.code ?? ""),
      name: String(r.name ?? ""),
      accountType: String(r.account_type ?? ""),
      lineCount: num(r.line_count),
      outstanding: num(r.outstanding),
      oldestDate: oldest,
      oldestAgeDays: oldest
        ? Math.round((cutoff - new Date(`${oldest}T00:00:00Z`).getTime()) / 86_400_000)
        : 0,
      partnerCount: num(r.partner_count),
      anonymousLines: num(r.anonymous_lines),
    };
  });
}

export interface NettedAccount {
  accountId: number;
  rows: NettableRow[];
  /** Signed sum before netting; equals the sum after, and the tie page proves it. */
  outstandingBefore: number;
  outstandingAfter: number;
  linesBefore: number;
  linesAfter: number;
}

/**
 * Full netting for ONE account.
 *
 * Never call this for every account at once: GR/IR textile alone carries 58.840
 * open lines. One account at a time keeps the fetch under a second and the
 * netting itself in the tens of milliseconds.
 *
 * `cache` dedupes within a request — the page header, the partner breakdown and
 * the line table all want the same netted set.
 */
export const nettedForAccount = cache(
  async (accountId: number, asOf: string, companies: number[]): Promise<NettedAccount> => {
    const rounding = await companyRounding(companies[0]);
    const scope: AsOfScope = { asOf, companies, accountIds: [accountId], rounding };
    const lines = await openLinesAsOf(scope);

    const rows: NettableRow[] = lines.map((l) => ({
      ...l,
      outstanding: l.residualAsOf,
    }));

    const outstandingBefore = rows.reduce((sum, r) => sum + r.residualAsOf, 0);
    const survivors = netOffsetting(rows, rounding).get(accountId) ?? [];

    return {
      accountId,
      rows: survivors,
      outstandingBefore,
      outstandingAfter: survivors.reduce((sum, r) => sum + r.outstanding, 0),
      linesBefore: rows.length,
      linesAfter: survivors.length,
    };
  },
);

export interface PartnerBreakdown {
  partnerId: number | null;
  partnerName: string;
  lineCount: number;
  outstanding: number;
  oldestDate: string | null;
}

/**
 * Counterparty rollup for one account, computed FROM the netted rows.
 *
 * Not a separate query, and not a filter pushed into SQL: partnerless rows
 * offset across partners in pass 2 of the netting, so narrowing first would
 * leave them out of that pass and print a bigger remainder than the account
 * summary promised.
 */
export async function partnerBreakdown(
  netted: NettedAccount,
): Promise<PartnerBreakdown[]> {
  const ids = Array.from(
    new Set(netted.rows.map((r) => r.partnerId).filter((id): id is number => id !== null)),
  );

  const names = new Map<number, string>();
  if (ids.length) {
    const rows = await q<Record<string, string | null>>(
      `SELECT id, name FROM res_partner WHERE id = ANY($1::int[])`,
      [ids],
    );
    for (const r of rows) names.set(num(r.id), String(r.name ?? ""));
  }

  const grouped = new Map<string, PartnerBreakdown>();
  for (const row of netted.rows) {
    const key = String(row.partnerId ?? "none");
    let entry = grouped.get(key);
    if (!entry) {
      entry = {
        partnerId: row.partnerId,
        partnerName:
          row.partnerId === null
            ? "Tanpa lawan transaksi"
            : names.get(row.partnerId) ?? `Partner #${row.partnerId}`,
        lineCount: 0,
        outstanding: 0,
        oldestDate: null,
      };
      grouped.set(key, entry);
    }
    entry.lineCount += 1;
    entry.outstanding += row.outstanding;
    if (!entry.oldestDate || row.date < entry.oldestDate) entry.oldestDate = row.date;
  }

  return Array.from(grouped.values()).sort((a, b) => Math.abs(b.outstanding) - Math.abs(a.outstanding));
}

export interface ReconcileAccountRow {
  accountId: number;
  lineCount: number;
  residual: number;
  oldestDate: string | null;
}

/**
 * The module's own view of the same thing, for the tie page to argue with.
 *
 * `custom_reconcile_account` (from custom_account_reconcile) reads the CURRENT
 * `amount_residual` of unreconciled posted lines, so it only agrees with the
 * as-of figures when the cut-off is today. That is a property of the view, not
 * a defect, and the tie page says so.
 */
export async function reconcileAccountView(): Promise<ReconcileAccountRow[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT account_id, line_count, residual, oldest_date FROM custom_reconcile_account`,
  );
  return rows.map((r) => ({
    accountId: num(r.account_id),
    lineCount: num(r.line_count),
    residual: num(r.residual),
    oldestDate: r.oldest_date ? String(r.oldest_date) : null,
  }));
}

/**
 * The GR/IR accounts.
 *
 * `levis.purchase.account.map` only names one (`grir_account_id` on the
 * non-trade row), while the balances actually sit on the 2103109121/2103109123
 * pair. So the map is used as a seed and the code prefix finds the rest —
 * checked 2026-08-28: accounts 778 and 780, 63.572 open lines between them.
 */
export const grirAccounts = cache(async (): Promise<AccountSummary["accountId"][]> => {
  const root = await rootCompanyId();
  const rows = await q<Record<string, string | null>>(
    `SELECT DISTINCT aa.id
       FROM account_account aa
      WHERE aa.reconcile
        AND (
              ${accountCodeSql("$1")} LIKE '21031091%'
           OR aa.id IN (SELECT grir_account_id FROM levis_purchase_account_map
                         WHERE grir_account_id IS NOT NULL)
        )`,
    [String(root)],
  );
  return rows.map((r) => num(r.id));
});
