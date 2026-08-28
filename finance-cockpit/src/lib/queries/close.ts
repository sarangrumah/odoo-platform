// =============================================================================
// Close readiness — the trial balance, and everything that would stop a close.
//
// The trial balance is the anchor. `custom.report.trial.balance` calls
// `_get_account_balances` twice with predicates that differ only in their date
// range, so one scan with FILTER produces the same numbers at half the cost.
//
// Three details are copied rather than improved:
//
//   * Odoo's opening window starts at 1970-01-01. `date < $from` is a superset;
//     the earliest line in prd_levis_begbal is 2026-01-01, so they coincide.
//   * `closing = opening + movement_debit - movement_credit`, not
//     `opening + movement_balance`. Same value, same rounding path.
//   * The grand total sums columns that were ALREADY split by sign per account,
//     so grand opening debit does not equal grand opening credit. That is not a
//     bug to fix — closing debit and credit are what must balance, and the tie
//     page asserts exactly that.
// =============================================================================

import { q, num } from "@/lib/db";
import { accountCodeSql, accountNameSql, journalNameSql, rootCompanyId } from "@/lib/queries/common";

export interface TrialBalanceRow {
  accountId: number;
  code: string;
  name: string;
  accountType: string;
  openingDebit: number;
  openingCredit: number;
  movementDebit: number;
  movementCredit: number;
  closingDebit: number;
  closingCredit: number;
}

export async function trialBalance(scope: {
  from: string;
  to: string;
  companies: number[];
}): Promise<TrialBalanceRow[]> {
  const root = await rootCompanyId();
  const rows = await q<Record<string, string | null>>(
    `
    WITH agg AS (
      SELECT aml.account_id,
             COALESCE(SUM(aml.balance) FILTER (WHERE aml.date < $2::date), 0.0) AS opening_balance,
             COALESCE(SUM(aml.debit)  FILTER (WHERE aml.date BETWEEN $2::date AND $3::date), 0.0) AS movement_debit,
             COALESCE(SUM(aml.credit) FILTER (WHERE aml.date BETWEEN $2::date AND $3::date), 0.0) AS movement_credit
        FROM account_move_line aml
       WHERE aml.date <= $3::date
         AND aml.company_id = ANY($1::int[])
         AND aml.account_id IS NOT NULL
         AND aml.parent_state = 'posted'
         AND aml.journal_id NOT IN (SELECT id FROM account_journal WHERE x_custom_report_excluded)
       GROUP BY aml.account_id
    )
    SELECT a.account_id,
           ${accountCodeSql("$4")} AS code,
           ${accountNameSql()} AS name,
           aa.account_type,
           GREATEST(a.opening_balance, 0.0)  AS opening_debit,
           GREATEST(-a.opening_balance, 0.0) AS opening_credit,
           a.movement_debit,
           a.movement_credit,
           GREATEST(a.opening_balance + a.movement_debit - a.movement_credit, 0.0)  AS closing_debit,
           GREATEST(-(a.opening_balance + a.movement_debit - a.movement_credit), 0.0) AS closing_credit
      FROM agg a
      JOIN account_account aa ON aa.id = a.account_id
     WHERE a.opening_balance <> 0 OR a.movement_debit <> 0 OR a.movement_credit <> 0
     ORDER BY code`,
    [scope.companies, scope.from, scope.to, String(root)],
  );

  return rows.map((r) => ({
    accountId: num(r.account_id),
    code: String(r.code ?? ""),
    name: String(r.name ?? ""),
    accountType: String(r.account_type ?? ""),
    openingDebit: num(r.opening_debit),
    openingCredit: num(r.opening_credit),
    movementDebit: num(r.movement_debit),
    movementCredit: num(r.movement_credit),
    closingDebit: num(r.closing_debit),
    closingCredit: num(r.closing_credit),
  }));
}

export interface LockException {
  id: number;
  active: boolean;
  lockDateField: string;
  lockDate: string | null;
  companyLockDate: string | null;
  endDatetime: string | null;
  userId: number | null;
  reason: string;
  /** No end date and still active: it never expires on its own. */
  permanent: boolean;
}

/**
 * Lock exceptions, with the permanent ones marked rather than alarmed about.
 *
 * prd_levis_begbal carries six active exceptions with no `end_datetime`
 * (ids 49–54, checked 2026-08-28). They are deliberate — June 2026 postings
 * were opened on purpose and left open — so the page names them as known
 * rather than flagging them. What deserves attention is a NEW permanent
 * exception, which is why the ids are not hard-coded: the page shows all of
 * them and says how many were expected.
 */
export async function lockExceptions(companies: number[]): Promise<LockException[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT id, active, lock_date_field, lock_date, company_lock_date,
            end_datetime, user_id, COALESCE(reason, '') AS reason
       FROM account_lock_exception
      WHERE company_id = ANY($1::int[])
      ORDER BY active DESC, id`,
    [companies],
  );
  return rows.map((r) => {
    const active = String(r.active) === "true";
    return {
      id: num(r.id),
      active,
      lockDateField: String(r.lock_date_field ?? ""),
      lockDate: r.lock_date ? String(r.lock_date) : null,
      companyLockDate: r.company_lock_date ? String(r.company_lock_date) : null,
      endDatetime: r.end_datetime ? String(r.end_datetime) : null,
      userId: r.user_id === null ? null : num(r.user_id),
      reason: String(r.reason ?? ""),
      permanent: active && !r.end_datetime,
    };
  });
}

export interface DraftBucket {
  journalId: number;
  journalCode: string;
  journalName: string;
  period: string;
  moveCount: number;
  amount: number;
}

/** Draft entries, grouped by journal and month — the first thing a close hits. */
export async function draftMoves(scope: {
  asOf: string;
  companies: number[];
}): Promise<DraftBucket[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT am.journal_id, aj.code AS journal_code, ${journalNameSql()} AS journal_name,
            to_char(am.date, 'YYYY-MM') AS period,
            COUNT(*) AS move_count,
            COALESCE(SUM(ABS(am.amount_total_signed)), 0.0) AS amount
       FROM account_move am
       JOIN account_journal aj ON aj.id = am.journal_id
      WHERE am.company_id = ANY($1::int[])
        AND am.state = 'draft'
        AND am.date <= $2::date
      GROUP BY am.journal_id, aj.code, aj.name, to_char(am.date, 'YYYY-MM')
      ORDER BY period DESC, move_count DESC`,
    [scope.companies, scope.asOf],
  );
  return rows.map((r) => ({
    journalId: num(r.journal_id),
    journalCode: String(r.journal_code ?? ""),
    journalName: String(r.journal_name ?? ""),
    period: String(r.period ?? ""),
    moveCount: num(r.move_count),
    amount: num(r.amount),
  }));
}

export interface AnomalyCount {
  key: string;
  label: string;
  detail: string;
  count: number;
  amount: number;
  /** True when a non-zero count is a problem rather than an observation. */
  isProblem: boolean;
}

/**
 * The close checklist, as one round trip.
 *
 * Each entry is a count plus the money behind it, because "42 lines" and
 * "42 lines worth Rp 3" are different conversations. `isProblem` decides
 * whether the page paints it, and a few of these are deliberately observations:
 * a future-dated entry is normal in a business that books accruals forward.
 */
export async function closeAnomalies(scope: {
  asOf: string;
  companies: number[];
}): Promise<AnomalyCount[]> {
  const rows = await q<Record<string, string | null>>(
    `
    WITH scoped AS (
      SELECT aml.*, aa.account_type, aa.reconcile,
             -- POS books no customer: every receipt lands on a per-tender
             -- receivable with no partner and no due date, by design. Counting
             -- those as data-quality defects would bury the handful that are.
             (aa.code_store ->> $3) LIKE '1106%' AS is_pos_receivable
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY($1::int[])
         AND aml.parent_state = 'posted'
         AND aml.date <= $2::date
    ),
    unbalanced AS (
      SELECT move_id, SUM(balance) AS diff
        FROM scoped GROUP BY move_id HAVING ABS(SUM(balance)) >= 0.005
    )
    SELECT
      (SELECT COUNT(*) FROM unbalanced)                                  AS unbalanced_count,
      (SELECT COALESCE(SUM(ABS(diff)), 0.0) FROM unbalanced)             AS unbalanced_amount,
      COUNT(*) FILTER (
        WHERE account_type IN ('asset_receivable', 'liability_payable')
          AND partner_id IS NULL AND NOT is_pos_receivable
      ) AS no_partner_count,
      COALESCE(SUM(ABS(balance)) FILTER (
        WHERE account_type IN ('asset_receivable', 'liability_payable')
          AND partner_id IS NULL AND NOT is_pos_receivable
      ), 0.0) AS no_partner_amount,
      COUNT(*) FILTER (
        WHERE account_type IN ('asset_receivable', 'liability_payable')
          AND partner_id IS NULL AND is_pos_receivable
      ) AS pos_no_partner_count,
      COUNT(*) FILTER (
        WHERE account_type IN ('asset_receivable', 'liability_payable')
          AND date_maturity IS NULL AND NOT reconciled AND NOT is_pos_receivable
      ) AS no_due_count,
      COALESCE(SUM(ABS(amount_residual)) FILTER (
        WHERE account_type IN ('asset_receivable', 'liability_payable')
          AND date_maturity IS NULL AND NOT reconciled AND NOT is_pos_receivable
      ), 0.0) AS no_due_amount,
      COUNT(*) FILTER (
        WHERE account_type IN ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost')
          AND (analytic_distribution IS NULL OR analytic_distribution = '{}'::jsonb)
      ) AS no_analytic_count,
      COALESCE(SUM(ABS(balance)) FILTER (
        WHERE account_type IN ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost')
          AND (analytic_distribution IS NULL OR analytic_distribution = '{}'::jsonb)
      ), 0.0) AS no_analytic_amount,
      COUNT(*) FILTER (WHERE reconcile AND reconciled AND ABS(amount_residual) >= 0.005) AS residual_on_reconciled_count,
      COALESCE(SUM(ABS(amount_residual)) FILTER (
        WHERE reconcile AND reconciled AND ABS(amount_residual) >= 0.005
      ), 0.0) AS residual_on_reconciled_amount
    FROM scoped`,
    [scope.companies, scope.asOf, String(await rootCompanyId())],
  );

  const future = await q<Record<string, string | null>>(
    `SELECT COUNT(*) AS c, COALESCE(SUM(ABS(aml.balance)), 0.0) AS a
       FROM account_move_line aml
      WHERE aml.company_id = ANY($1::int[])
        AND aml.parent_state = 'posted'
        AND aml.date > $2::date`,
    [scope.companies, scope.asOf],
  );

  const r = rows[0] ?? {};
  const f = future[0] ?? {};

  return [
    {
      key: "unbalanced",
      label: "Jurnal tidak seimbang",
      detail: "Jumlah balance per entry bukan nol. Tidak boleh ada satu pun.",
      count: num(r.unbalanced_count),
      amount: num(r.unbalanced_amount),
      isProblem: num(r.unbalanced_count) > 0,
    },
    {
      key: "no_partner",
      label: "Baris AR/AP tanpa lawan transaksi (di luar piutang POS)",
      detail:
        "Tidak bisa masuk aging per vendor/pelanggan mana pun. Piutang POS " +
        `(akun 1106…) dikecualikan: ${num(r.pos_no_partner_count).toLocaleString("id-ID")} ` +
        "barisnya memang tanpa partner karena POS tidak mencatat pelanggan.",
      count: num(r.no_partner_count),
      amount: num(r.no_partner_amount),
      isProblem: num(r.no_partner_count) > 0,
    },
    {
      key: "no_due",
      label: "Baris AR/AP terbuka tanpa tanggal jatuh tempo (di luar piutang POS)",
      detail: "Jatuh ke bucket 'belum jatuh tempo' selamanya.",
      count: num(r.no_due_count),
      amount: num(r.no_due_amount),
      isProblem: num(r.no_due_count) > 0,
    },
    {
      key: "no_analytic",
      label: "Baris laba-rugi tanpa distribusi analitik",
      detail: "Tidak terbaca di laporan per Operating Unit.",
      count: num(r.no_analytic_count),
      amount: num(r.no_analytic_amount),
      isProblem: num(r.no_analytic_count) > 0,
    },
    {
      key: "residual_on_reconciled",
      label: "Baris tertandai lunas tapi residual bukan nol",
      detail: "Rekonsiliasi dan residual saling bertentangan.",
      count: num(r.residual_on_reconciled_count),
      amount: num(r.residual_on_reconciled_amount),
      isProblem: num(r.residual_on_reconciled_count) > 0,
    },
    {
      key: "future_dated",
      label: "Baris terposting setelah tanggal potong",
      detail: "Wajar untuk akrual ke depan; ditampilkan sebagai pengamatan.",
      count: num(f.c),
      amount: num(f.a),
      isProblem: false,
    },
  ];
}

export interface ExcludedJournal {
  journalId: number;
  code: string;
  name: string;
  lineCount: number;
  balance: number;
}

/**
 * The journals the reports leave out, and what they are worth.
 *
 * This is the whole difference between the raw ledger and the trial balance, so
 * it gets a name and a number instead of being an unexplained gap. No journal
 * carries the flag in prd_levis_begbal today.
 */
export async function excludedJournals(scope: {
  asOf: string;
  companies: number[];
}): Promise<ExcludedJournal[]> {
  const rows = await q<Record<string, string | null>>(
    `SELECT aj.id, aj.code, ${journalNameSql()} AS name,
            COUNT(aml.id) AS line_count,
            COALESCE(SUM(aml.balance), 0.0) AS balance
       FROM account_journal aj
       LEFT JOIN account_move_line aml
              ON aml.journal_id = aj.id
             AND aml.parent_state = 'posted'
             AND aml.date <= $2::date
             AND aml.company_id = ANY($1::int[])
      WHERE aj.x_custom_report_excluded
      GROUP BY aj.id, aj.code, aj.name
      ORDER BY aj.code`,
    [scope.companies, scope.asOf],
  );
  return rows.map((r) => ({
    journalId: num(r.id),
    code: String(r.code ?? ""),
    name: String(r.name ?? ""),
    lineCount: num(r.line_count),
    balance: num(r.balance),
  }));
}

export interface SequenceGap {
  journalCode: string;
  journalName: string;
  period: string;
  after: string;
  before: string;
  missing: number;
}

/**
 * Holes in a journal's numbering, per month.
 *
 * Odoo numbers `PREFIX/YYYY/NNNNN`; a gap means an entry was deleted or never
 * posted, and an auditor will ask about it. Only entries that carry a numeric
 * tail are considered, so `/` placeholders on drafts do not register as gaps.
 */
export async function sequenceGaps(scope: {
  asOf: string;
  companies: number[];
}): Promise<SequenceGap[]> {
  const rows = await q<Record<string, string | null>>(
    `
    WITH numbered AS (
      SELECT aj.code AS journal_code,
             ${journalNameSql()} AS journal_name,
             to_char(am.date, 'YYYY-MM') AS period,
             am.name,
             substring(am.name from '(\\d+)$')::bigint AS seq,
             regexp_replace(am.name, '\\d+$', '') AS prefix
        FROM account_move am
        JOIN account_journal aj ON aj.id = am.journal_id
       WHERE am.company_id = ANY($1::int[])
         AND am.state = 'posted'
         AND am.date <= $2::date
         AND am.name ~ '\\d+$'
    ),
    ordered AS (
      SELECT n.*,
             LAG(seq) OVER (PARTITION BY prefix ORDER BY seq) AS prev_seq,
             LAG(name) OVER (PARTITION BY prefix ORDER BY seq) AS prev_name
        FROM numbered n
    )
    SELECT journal_code, journal_name, period, prev_name AS after, name AS before,
           (seq - prev_seq - 1) AS missing
      FROM ordered
     WHERE prev_seq IS NOT NULL AND seq - prev_seq > 1
     ORDER BY missing DESC, journal_code, period
     LIMIT 100`,
    [scope.companies, scope.asOf],
  );
  return rows.map((r) => ({
    journalCode: String(r.journal_code ?? ""),
    journalName: String(r.journal_name ?? ""),
    period: String(r.period ?? ""),
    after: String(r.after ?? ""),
    before: String(r.before ?? ""),
    missing: num(r.missing),
  }));
}
