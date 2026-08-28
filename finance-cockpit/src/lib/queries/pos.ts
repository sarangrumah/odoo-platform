// =============================================================================
// POS clearing and bank — the health of the settlement machinery.
//
// A Levi's store sells on cards, QRIS and cash. The POS session books one
// receivable per tender; days later the acquirer pays, net of its fee, and the
// bank statement lands on the suspense account. `levis.pos.clearing` matches
// the two, in three hard-separated stages (compute → generate → post).
//
// The single most important fact about querying it: the run-level totals
// (`total_gross`, `total_short`, `short_count`, …) are COMPUTED FIELDS WITHOUT
// `store=True`. There is no column for them. Every headline here is therefore
// re-aggregated from `levis_pos_clearing_line`, where `allocated`,
// `short_amount`, `mismatch_amount` and `cash_in` genuinely are stored.
// The columns that DO exist on the run are the before/after balance snapshots.
//
// Second trap: `account_bank_statement_line` `_inherits` account.move, so
// `date`, `company_id` and `currency_id` are not on its table. Always join.
// =============================================================================

import { q, num } from "@/lib/db";
import { accountCodeSql, accountNameSql, rootCompanyId } from "@/lib/queries/common";

export interface ClearingRun {
  id: number;
  name: string;
  periodRef: string;
  state: string;
  dateFrom: string;
  dateTo: string;
  /** Re-aggregated from the lines; the run has no column for these. */
  gross: number;
  mdr: number;
  cashIn: number;
  allocated: number;
  short: number;
  mismatch: number;
  lineCount: number;
  shortCount: number;
  mismatchCount: number;
  unmappedCount: number;
  unparsedCount: number;
  skippedCount: number;
  okCount: number;
  /** Real columns on the run. */
  suspenseBefore: number;
  suspenseAfterActual: number;
  mdrBefore: number;
  mdrAfterActual: number;
  posrecOpenBefore: number;
  posrecOpenAfterActual: number;
  posrecLinesBefore: number;
  posrecLinesAfterActual: number;
  warningText: string;
}

export async function clearingRuns(companies: number[]): Promise<ClearingRun[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT r.id, r.name, r.period_ref, r.state, r.date_from, r.date_to,
            COALESCE(r.warning_text, '') AS warning_text,
            r.bal_suspense_before, r.bal_suspense_after_actual,
            r.bal_mdr_before, r.bal_mdr_after_actual,
            r.posrec_open_before, r.posrec_open_after_actual,
            r.posrec_lines_before, r.posrec_lines_after_actual,
            COALESCE(SUM(l.gross), 0.0)           AS gross,
            COALESCE(SUM(l.mdr), 0.0)             AS mdr,
            COALESCE(SUM(l.cash_in), 0.0)         AS cash_in,
            COALESCE(SUM(l.allocated), 0.0)       AS allocated,
            COALESCE(SUM(l.short_amount), 0.0)    AS short_amount,
            COALESCE(SUM(l.mismatch_amount), 0.0) AS mismatch_amount,
            COUNT(l.id)                                       AS line_count,
            COUNT(l.id) FILTER (WHERE l.state = 'short')      AS short_count,
            COUNT(l.id) FILTER (WHERE l.state = 'mismatch')   AS mismatch_count,
            COUNT(l.id) FILTER (WHERE l.state = 'unmapped')   AS unmapped_count,
            COUNT(l.id) FILTER (WHERE l.state = 'unparsed')   AS unparsed_count,
            COUNT(l.id) FILTER (WHERE l.state = 'skipped')    AS skipped_count,
            COUNT(l.id) FILTER (WHERE l.state = 'ok')         AS ok_count
       FROM levis_pos_clearing r
       LEFT JOIN levis_pos_clearing_line l ON l.run_id = r.id
      WHERE r.company_id = ANY($1::int[])
      GROUP BY r.id
      ORDER BY r.date_from DESC, r.id DESC`,
    [companies],
  );

  return rows.map((r) => ({
    id: num(r.id),
    name: String(r.name ?? ""),
    periodRef: String(r.period_ref ?? ""),
    state: String(r.state ?? ""),
    dateFrom: String(r.date_from ?? ""),
    dateTo: String(r.date_to ?? ""),
    gross: num(r.gross),
    mdr: num(r.mdr),
    cashIn: num(r.cash_in),
    allocated: num(r.allocated),
    short: num(r.short_amount),
    mismatch: num(r.mismatch_amount),
    lineCount: num(r.line_count),
    shortCount: num(r.short_count),
    mismatchCount: num(r.mismatch_count),
    unmappedCount: num(r.unmapped_count),
    unparsedCount: num(r.unparsed_count),
    skippedCount: num(r.skipped_count),
    okCount: num(r.ok_count),
    suspenseBefore: num(r.bal_suspense_before),
    suspenseAfterActual: num(r.bal_suspense_after_actual),
    mdrBefore: num(r.bal_mdr_before),
    mdrAfterActual: num(r.bal_mdr_after_actual),
    posrecOpenBefore: num(r.posrec_open_before),
    posrecOpenAfterActual: num(r.posrec_open_after_actual),
    posrecLinesBefore: num(r.posrec_lines_before),
    posrecLinesAfterActual: num(r.posrec_lines_after_actual),
    warningText: String(r.warning_text ?? ""),
  }));
}

export interface DiagnosticRow {
  kind: string;
  severity: string;
  count: number;
  amount: number;
  occurrences: number;
}

/** The diagnostics board: 13 kinds, three severities, blocking first. */
export async function diagnostics(runId: number): Promise<DiagnosticRow[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT d.kind, d.severity,
            COALESCE(SUM(d.count), 0) AS total_count,
            COALESCE(SUM(d.amount), 0.0) AS amount,
            COUNT(*) AS occurrences
       FROM levis_pos_clearing_diag d
      WHERE d.run_id = $1
      GROUP BY d.kind, d.severity
      ORDER BY CASE d.severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
               amount DESC`,
    [runId],
  );
  return rows.map((r) => ({
    kind: String(r.kind ?? ""),
    severity: String(r.severity ?? "info"),
    count: num(r.total_count),
    amount: num(r.amount),
    occurrences: num(r.occurrences),
  }));
}

export interface ShortByDimension {
  key: string;
  label: string;
  lineCount: number;
  gross: number;
  short: number;
  mismatch: number;
}

/**
 * Where the shortfall sits — by store (analytic), by bank journal, or by day.
 *
 * One query shape, three groupings, because the question "who is short" is the
 * same question asked from three sides and the answers must add up to the same
 * total.
 */
export async function shortBy(
  runId: number,
  dimension: "store" | "journal" | "day",
): Promise<ShortByDimension[]> {
  const groupings = {
    store: {
      key: "COALESCE(l.analytic_account_id::text, 'none')",
      // account_analytic_account.name is translatable, so it is JSONB — a bare
      // COALESCE against a text literal fails with "invalid input syntax for
      // type json" rather than falling back.
      label: "COALESCE(aa.name ->> 'en_US', aa.name ->> 'id_ID', 'Tanpa Operating Unit')",
      join: "LEFT JOIN account_analytic_account aa ON aa.id = l.analytic_account_id",
    },
    journal: {
      key: "COALESCE(l.bank_journal_id::text, 'none')",
      label: "COALESCE(aj.code, 'Tanpa jurnal')",
      join: "LEFT JOIN account_journal aj ON aj.id = l.bank_journal_id",
    },
    day: {
      key: "COALESCE(l.settlement_date::text, 'none')",
      label: "COALESCE(l.settlement_date::text, 'Tanpa tanggal')",
      join: "",
    },
  } as const;

  const g = groupings[dimension];
  const rows = await q<Record<string, string | null>>(
    `SELECT ${g.key} AS key, ${g.label} AS label,
            COUNT(*) AS line_count,
            COALESCE(SUM(l.gross), 0.0) AS gross,
            COALESCE(SUM(l.short_amount), 0.0) AS short_amount,
            COALESCE(SUM(l.mismatch_amount), 0.0) AS mismatch_amount
       FROM levis_pos_clearing_line l
       ${g.join}
      WHERE l.run_id = $1
      GROUP BY 1, 2
      ORDER BY short_amount DESC, gross DESC`,
    [runId],
  );
  return rows.map((r) => ({
    key: String(r.key ?? ""),
    label: String(r.label ?? ""),
    lineCount: num(r.line_count),
    gross: num(r.gross),
    short: num(r.short_amount),
    mismatch: num(r.mismatch_amount),
  }));
}

export interface X24Match {
  match: string;
  lineCount: number;
  gross: number;
  matchedTotal: number;
  gap: number;
  tenderMismatch: number;
}

/** How well the bank settlements line up with the X24 receipts. */
export async function x24Matching(runId: number): Promise<X24Match[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT COALESCE(NULLIF(l.x24_match, ''), 'none') AS match,
            COUNT(*) AS line_count,
            COALESCE(SUM(l.gross), 0.0) AS gross,
            COALESCE(SUM(l.matched_total), 0.0) AS matched_total,
            COALESCE(SUM(l.match_gap), 0.0) AS gap,
            COUNT(*) FILTER (WHERE l.x24_tender_mismatch) AS tender_mismatch
       FROM levis_pos_clearing_line l
      WHERE l.run_id = $1
      GROUP BY 1
      ORDER BY line_count DESC`,
    [runId],
  );
  return rows.map((r) => ({
    match: String(r.match ?? ""),
    lineCount: num(r.line_count),
    gross: num(r.gross),
    matchedTotal: num(r.matched_total),
    gap: num(r.gap),
    tenderMismatch: num(r.tender_mismatch),
  }));
}

export interface LegBalance {
  runId: number;
  runName: string;
  role: string;
  legCount: number;
  balance: number;
  postedLines: number;
}

/**
 * The planned legs, and whether they made it into the ledger.
 *
 * `SUM(balance)` across all roles of one run must be zero — the legs are a
 * complete double entry. `postedLines` counts the legs that actually carry a
 * `move_line_id`, which is what separates a computed run from a posted one.
 */
export async function legBalances(companies: number[]): Promise<LegBalance[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT r.id AS run_id, r.name AS run_name, g.role,
            COUNT(*) AS leg_count,
            COALESCE(SUM(g.balance), 0.0) AS balance,
            COUNT(g.move_line_id) AS posted_lines
       FROM levis_pos_clearing_leg g
       JOIN levis_pos_clearing_line l ON l.id = g.line_id
       JOIN levis_pos_clearing r ON r.id = l.run_id
      WHERE r.company_id = ANY($1::int[])
      GROUP BY r.id, r.name, g.role
      ORDER BY r.id DESC, g.role`,
    [companies],
  );
  return rows.map((r) => ({
    runId: num(r.run_id),
    runName: String(r.run_name ?? ""),
    role: String(r.role ?? ""),
    legCount: num(r.leg_count),
    balance: num(r.balance),
    postedLines: num(r.posted_lines),
  }));
}

export interface UnreconciledStatement {
  journalId: number;
  journalCode: string;
  lineCount: number;
  amount: number;
  oldest: string | null;
  unparsed: number;
  unmappedMid: number;
}

/**
 * Bank statement lines still waiting to be explained.
 *
 * The suspense account ships with `reconcile = False` and can never be matched,
 * which is why the clearing writes its counterpart onto the statement line's
 * own move: leaving the suspense leg standing keeps `is_reconciled = false`
 * forever and Odoo then refuses to set a lock date over the period. So this
 * count is not cosmetic — it is what blocks a close.
 */
export async function unreconciledStatements(scope: {
  asOf: string;
  companies: number[];
}): Promise<UnreconciledStatement[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT absl.journal_id, aj.code AS journal_code,
            COUNT(*) AS line_count,
            COALESCE(SUM(absl.amount), 0.0) AS amount,
            MIN(am.date) AS oldest,
            COUNT(*) FILTER (WHERE absl.levis_narrative_kind IS NULL) AS unparsed,
            COUNT(*) FILTER (
              WHERE absl.levis_mid IS NOT NULL AND absl.levis_mid_map_id IS NULL
            ) AS unmapped_mid
       FROM account_bank_statement_line absl
       JOIN account_move am ON am.id = absl.move_id
       JOIN account_journal aj ON aj.id = absl.journal_id
      WHERE am.company_id = ANY($1::int[])
        AND am.date <= $2::date
        AND NOT absl.is_reconciled
      GROUP BY absl.journal_id, aj.code
      ORDER BY line_count DESC`,
    [scope.companies, scope.asOf],
  );
  return rows.map((r) => ({
    journalId: num(r.journal_id),
    journalCode: String(r.journal_code ?? ""),
    lineCount: num(r.line_count),
    amount: num(r.amount),
    oldest: r.oldest ? String(r.oldest) : null,
    unparsed: num(r.unparsed),
    unmappedMid: num(r.unmapped_mid),
  }));
}

export interface TenderBalance {
  accountId: number;
  code: string;
  name: string;
  openLines: number;
  balance: number;
  oldest: string | null;
}

/**
 * The per-tender POS receivables that clearing is supposed to drain.
 *
 * Found by code prefix rather than through `levis_clearing_config`: the
 * config's `pos_receivable_account_ids` relation is empty in prd_levis_begbal
 * (checked 2026-08-28), so relying on it alone would show nothing at all.
 */
export async function tenderBalances(scope: {
  asOf: string;
  companies: number[];
}): Promise<TenderBalance[]> {
  const root = await rootCompanyId();
  const rows = await q<Record<string, string | null>>(
    `SELECT aa.id,
            ${accountCodeSql("$3")} AS code,
            ${accountNameSql()} AS name,
            COUNT(aml.id) FILTER (WHERE NOT aml.reconciled) AS open_lines,
            COALESCE(SUM(aml.amount_residual) FILTER (WHERE NOT aml.reconciled), 0.0) AS balance,
            MIN(aml.date) FILTER (WHERE NOT aml.reconciled) AS oldest
       FROM account_account aa
       LEFT JOIN account_move_line aml
              ON aml.account_id = aa.id
             AND aml.parent_state = 'posted'
             AND aml.company_id = ANY($1::int[])
             AND aml.date <= $2::date
      WHERE (${accountCodeSql("$3")} LIKE '11060001%'
             OR aa.id IN (SELECT account_id FROM levis_clearing_config_posrec_rel))
      GROUP BY aa.id, aa.code_store, aa.name
      ORDER BY code`,
    [scope.companies, scope.asOf, String(root)],
  );
  return rows.map((r) => ({
    accountId: num(r.id),
    code: String(r.code ?? ""),
    name: String(r.name ?? ""),
    openLines: num(r.open_lines),
    balance: num(r.balance),
    oldest: r.oldest ? String(r.oldest) : null,
  }));
}

export interface ClearingConfig {
  suspenseAccountId: number | null;
  mdrAccountId: number | null;
  arAccountId: number | null;
  sweepAccountId: number | null;
  bankChargeAccountId: number | null;
  settlementLagDays: number;
  lookbackDays: number;
}

export async function clearingConfig(companies: number[]): Promise<ClearingConfig | null> {
  const rows = await q<Record<string, string | null>>(
    `SELECT suspense_account_id, mdr_account_id, ar_account_id, sweep_account_id,
            bank_charge_account_id, settlement_lag_days, lookback_days
       FROM levis_clearing_config
      WHERE company_id = ANY($1::int[])
      ORDER BY id
      LIMIT 1`,
    [companies],
  );
  const r = rows[0];
  if (!r) return null;
  return {
    suspenseAccountId: r.suspense_account_id === null ? null : num(r.suspense_account_id),
    mdrAccountId: r.mdr_account_id === null ? null : num(r.mdr_account_id),
    arAccountId: r.ar_account_id === null ? null : num(r.ar_account_id),
    sweepAccountId: r.sweep_account_id === null ? null : num(r.sweep_account_id),
    bankChargeAccountId: r.bank_charge_account_id === null ? null : num(r.bank_charge_account_id),
    settlementLagDays: num(r.settlement_lag_days),
    lookbackDays: num(r.lookback_days),
  };
}
