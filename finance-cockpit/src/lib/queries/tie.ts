// =============================================================================
// The checks that decide whether anyone should believe the other four pages.
//
// Every figure here is computed live against prd_levis_begbal. Nothing is
// hard-coded, and each check states its expected value up front — including the
// three whose expected value is NOT zero, because a bridge that is explained is
// evidence and a difference that is hidden is not.
//
// Checks 1–13 prove internal consistency. Only `tests/parity.smoke.ts`, which
// calls the Odoo reports themselves, proves the dashboard agrees with Odoo;
// check 14 is a pointer to it rather than something this page can run, because
// it needs admin credentials this app deliberately does not hold.
// =============================================================================

import { q, num } from "@/lib/db";
import { isZero } from "@/lib/money";
import { netOffsetting, type NettableRow } from "@/lib/netting";
import {
  companyRounding,
  openLinesAsOf,
} from "@/lib/queries/common";
import { agingByPartner, agingAsOfTotals, totalsOf, BUCKETS, type BucketCode } from "@/lib/queries/ap";
import { summaryByAccount, reconcileAccountView, grirAccounts } from "@/lib/queries/openitems";
import { trialBalance, excludedJournals } from "@/lib/queries/close";
import { legBalances } from "@/lib/queries/pos";

export type TieState = "ok" | "bad" | "info";

export interface TieCheck {
  id: number;
  title: string;
  /** What the two sides are, in one sentence. */
  description: string;
  leftLabel: string;
  rightLabel: string;
  left: number;
  right: number;
  difference: number;
  /** What the difference is supposed to be. */
  expectation: string;
  state: TieState;
  /** Shown when the check needs qualifying, or when it is a bridge. */
  note?: string;
  sql?: string;
  rows?: { label: string; left: number; right: number; difference: number }[];
}

export interface TieScope {
  asOf: string;
  companies: number[];
  /** Movement window for the trial balance. */
  from: string;
}

function verdict(difference: number, rounding: number): TieState {
  return isZero(difference, rounding) ? "ok" : "bad";
}

/** Check 1 — the trial balance closes. */
async function checkTrialBalance(scope: TieScope, rounding: number): Promise<TieCheck> {
  const rows = await trialBalance({ from: scope.from, to: scope.asOf, companies: scope.companies });
  const debit = rows.reduce((s, r) => s + r.closingDebit, 0);
  const credit = rows.reduce((s, r) => s + r.closingCredit, 0);
  return {
    id: 1,
    title: "Neraca saldo tutup seimbang",
    description:
      "Total debit penutup dibandingkan total kredit penutup, atas semua akun yang bergerak.",
    leftLabel: "Debit penutup",
    rightLabel: "Kredit penutup",
    left: debit,
    right: credit,
    difference: debit - credit,
    expectation: "Nol",
    state: verdict(debit - credit, rounding),
    note:
      "Total pembuka debit dan kredit sengaja TIDAK sama: seperti report Odoo, " +
      "kolomnya sudah dipisah tanda per akun sebelum dijumlahkan. Yang wajib " +
      "seimbang adalah penutupnya.",
  };
}

/** Check 2 — the whole ledger sums to zero. */
async function checkLedgerZero(scope: TieScope, rounding: number): Promise<TieCheck> {
  const rows = await q<Record<string, string | null>>(
    `SELECT COALESCE(SUM(aml.debit), 0.0) AS debit, COALESCE(SUM(aml.credit), 0.0) AS credit
       FROM account_move_line aml
      WHERE aml.company_id = ANY($1::int[])
        AND aml.parent_state = 'posted'
        AND aml.date <= $2::date`,
    [scope.companies, scope.asOf],
  );
  const debit = num(rows[0]?.debit);
  const credit = num(rows[0]?.credit);
  return {
    id: 2,
    title: "Seluruh buku besar berimbang",
    description: "Semua baris terposting sampai tanggal potong, tanpa pengecualian jurnal apa pun.",
    leftLabel: "Debit",
    rightLabel: "Kredit",
    left: debit,
    right: credit,
    difference: debit - credit,
    expectation: "Nol",
    state: verdict(debit - credit, rounding),
  };
}

/** Checks 3 and 4 — aging total against the GL balance of its own accounts. */
async function checkAgingVsGl(
  scope: TieScope,
  rounding: number,
  side: "payable" | "receivable",
  id: number,
): Promise<TieCheck> {
  const accountType = side === "payable" ? "liability_payable" : "asset_receivable";
  const aging = totalsOf(await agingByPartner(side, scope));
  const rows = await q<Record<string, string | null>>(
    `SELECT COALESCE(SUM(aml.amount_residual), 0.0) AS residual
       FROM account_move_line aml
       JOIN account_account aa ON aa.id = aml.account_id
      WHERE aml.company_id = ANY($1::int[])
        AND aa.account_type = $3
        AND aml.parent_state = 'posted'
        AND aml.date <= $2::date
        AND aml.reconciled = false`,
    [scope.companies, scope.asOf, accountType],
  );
  const gl = num(rows[0]?.residual);
  const label = side === "payable" ? "hutang" : "piutang";
  return {
    id,
    title: `Aging ${label} sama dengan saldo akun ${label} di buku besar`,
    description:
      `Total aging (varian paritas) dibandingkan residual seluruh baris ${label} terbuka ` +
      "yang terposting sampai tanggal potong.",
    leftLabel: "Total aging",
    rightLabel: "Residual buku besar",
    left: aging.total,
    right: gl,
    difference: aging.total - gl,
    expectation: "Nol",
    state: verdict(aging.total - gl, rounding),
  };
}

/** Check 5 — the parity/as-of bridge. Expected NOT to be zero. */
async function checkAgingBridge(scope: TieScope, rounding: number): Promise<TieCheck> {
  const parity = totalsOf(await agingByPartner("payable", scope));
  const asOf = await agingAsOfTotals("payable", scope);
  const difference = parity.total - asOf.total;

  const rows = BUCKETS.map((b) => ({
    label: b.label,
    left: parity.buckets[b.code as BucketCode],
    right: asOf.buckets[b.code as BucketCode],
    difference: parity.buckets[b.code as BucketCode] - asOf.buckets[b.code as BucketCode],
  }));

  return {
    id: 5,
    title: "Jembatan aging: varian paritas vs varian as-of",
    description:
      "Paritas memakai residual saat ini seperti report Odoo. Varian as-of membangun ulang " +
      "residual ke tanggal potong dari rekonsiliasi yang benar-benar sudah terjadi saat itu.",
    leftLabel: "Paritas (seperti Odoo)",
    rightLabel: "As-of tanggal potong",
    left: parity.total,
    right: asOf.total,
    difference,
    expectation:
      "BUKAN nol bila ada dokumen yang direkonsiliasi setelah tanggal potong. Selisihnya " +
      "persis sebesar rekonsiliasi tersebut.",
    state: isZero(difference, rounding) ? "ok" : "info",
    note:
      "Dua-duanya benar, untuk pertanyaan yang berbeda. Angka utama di halaman AP memakai " +
      "paritas supaya cocok dengan Aged Payable Odoo; varian as-of yang cocok dengan buku " +
      "besar di akhir periode.",
    rows,
  };
}

/**
 * Check 6 — as-of open items against the module's own view, with a bridge.
 *
 * `custom_reconcile_account` reads the CURRENT `amount_residual` of every
 * unreconciled posted line, with no date filter at all. Two things therefore
 * make it disagree with an as-of figure even when the cut-off is today, and
 * both are correct behaviour rather than defects:
 *
 *   A. A partial whose `max_date` is AFTER the cut-off. `max_date` is the later
 *      of the two lines' accounting dates, not the moment someone clicked
 *      reconcile — so a payment dated next month applied to this month's bill
 *      lands in the future. The bill was genuinely still open at the cut-off.
 *      Measured 2026-08-28: 29 partials dated 2026-09-01, Rp 719.838.546.
 *   B. A line dated after the cut-off. The view counts it, an as-of reading
 *      cannot. Measured 2026-08-28: 25 lines, Rp 38.775.000.
 *
 * So the check is a reconciliation, not an equality: the difference must be
 * fully accounted for by A and B, and what is left over must be zero. That is a
 * stronger statement than "these two numbers match", and it stays meaningful on
 * a day when they do not.
 */
async function checkOpenItemsVsView(scope: TieScope, rounding: number, today: string): Promise<TieCheck> {
  const [summary, view, bridge] = await Promise.all([
    summaryByAccount({ asOf: scope.asOf, companies: scope.companies }),
    reconcileAccountView(),
    q<Record<string, string | null>>(
      `WITH future_partial AS (
         SELECT p.debit_move_id, p.credit_move_id, p.amount
           FROM account_partial_reconcile p
           JOIN account_move_line dl ON dl.id = p.debit_move_id
           JOIN account_move_line cl ON cl.id = p.credit_move_id
          WHERE p.max_date > $2::date
            AND dl.parent_state = 'posted'
            AND cl.parent_state = 'posted'
       ),
       future_settled AS (
         SELECT line_id, SUM(amt) AS amt
           FROM (
             SELECT debit_move_id, amount FROM future_partial
             UNION ALL
             SELECT credit_move_id, -amount FROM future_partial
           ) s(line_id, amt)
          GROUP BY line_id
       )
       SELECT
         COALESCE((
           SELECT SUM(f.amt)
             FROM future_settled f
             JOIN account_move_line aml ON aml.id = f.line_id
             JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.reconcile
              AND aml.company_id = ANY($1::int[])
              AND aml.parent_state = 'posted'
              AND aml.date <= $2::date
         ), 0.0) AS settled_after_cutoff,
         COALESCE((
           SELECT SUM(aml.amount_residual)
             FROM account_move_line aml
             JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.reconcile
              AND aml.company_id = ANY($1::int[])
              AND aml.parent_state = 'posted'
              AND NOT aml.reconciled
              AND aml.date > $2::date
         ), 0.0) AS lines_after_cutoff`,
      [scope.companies, scope.asOf],
    ),
  ]);

  const left = summary.reduce((s, r) => s + r.outstanding, 0);
  const right = view.reduce((s, r) => s + r.residual, 0);

  const settledAfter = num(bridge[0]?.settled_after_cutoff);
  const linesAfter = num(bridge[0]?.lines_after_cutoff);
  // Dashboard still carries what the future partial will settle; the view has
  // already released it. Dashboard omits lines dated later; the view has them.
  const unexplained = left - right - settledAfter + linesAfter;

  const rows = [
    { label: "Dasbor (as-of)", left, right: 0, difference: left },
    { label: "View custom_reconcile_account", left: right, right: 0, difference: right },
    {
      label: "Selisih mentah",
      left: left - right,
      right: 0,
      difference: left - right,
    },
    {
      label: "A. Dilunasi oleh partial bertanggal setelah tanggal potong",
      left: settledAfter,
      right: 0,
      difference: settledAfter,
    },
    {
      label: "B. Baris terbuka bertanggal setelah tanggal potong",
      left: linesAfter,
      right: 0,
      difference: linesAfter,
    },
    { label: "Sisa yang tidak dijelaskan", left: unexplained, right: 0, difference: unexplained },
  ];

  return {
    id: 6,
    title: "Open item as-of direkonsiliasi dengan view custom_reconcile_account",
    description:
      "View milik modul custom_account_reconcile membaca residual saat ini dan tidak menyaring " +
      "tanggal sama sekali. Dua hal karena itu membuatnya berbeda dari pembacaan as-of, dan " +
      "keduanya benar. Yang diuji di sini adalah apakah seluruh selisihnya bisa dijelaskan.",
    leftLabel: "Sisa tidak dijelaskan",
    rightLabel: "",
    left: unexplained,
    right: 0,
    difference: unexplained,
    expectation: "Nol — setiap rupiah selisih harus terjelaskan oleh A atau B",
    state: verdict(unexplained, rounding),
    note:
      "A adalah pembayaran bertanggal periode berikutnya yang dipakai melunasi tagihan periode " +
      "ini. Kolom max_date pada partial adalah tanggal akuntansi terakhir dari dua barisnya, " +
      "bukan waktu seseorang menekan tombol rekonsiliasi — jadi tagihannya memang masih terbuka " +
      "pada tanggal potong, dan dasbor benar ketika masih menghitungnya. B adalah baris yang " +
      "bertanggal setelah tanggal potong: view menghitungnya karena tidak menyaring tanggal, " +
      "pembacaan as-of tidak bisa." +
      (scope.asOf === today ? "" : " Tanggal potong bukan hari ini, jadi A dan B melebar."),
    rows,
  };
}

/** Check 7 — balance minus as-of residual equals what the partials settled. */
async function checkSettlementIdentity(scope: TieScope, rounding: number): Promise<TieCheck> {
  const rows = await q<Record<string, string | null>>(
    `
    WITH cand AS (
      SELECT aml.id, aml.balance
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
       WHERE aml.company_id = ANY($1::int[])
         AND aa.reconcile
         AND aml.parent_state = 'posted'
         AND aml.date <= $2::date
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
          UNION ALL SELECT credit_move_id, -amount FROM posted_partial
        ) s(line_id, amt)
       GROUP BY line_id
    )
    SELECT COALESCE(SUM(c.balance), 0.0) AS total_balance,
           COALESCE(SUM(c.balance - COALESCE(s.settled, 0.0)), 0.0) AS total_residual,
           COALESCE((SELECT SUM(settled) FROM settled
                      WHERE line_id IN (SELECT id FROM cand)), 0.0) AS total_settled
      FROM cand c
      LEFT JOIN settled s ON s.line_id = c.id`,
    [scope.companies, scope.asOf],
  );

  const balance = num(rows[0]?.total_balance);
  const residual = num(rows[0]?.total_residual);
  const settled = num(rows[0]?.total_settled);
  const difference = balance - residual - settled;

  return {
    id: 7,
    title: "Identitas penyelesaian: saldo − residual as-of = yang direkonsiliasi",
    description:
      "Membuktikan pembangunan ulang residual tidak menambah maupun kehilangan rupiah — " +
      "setiap selisih antara saldo asli dan residual as-of harus ada partial reconcile-nya.",
    leftLabel: "Saldo − residual as-of",
    rightLabel: "Jumlah partial (kedua sisi terposting)",
    left: balance - residual,
    right: settled,
    difference,
    expectation: "Nol",
    state: verdict(difference, rounding),
  };
}

/** Check 8 — netting preserves the signed sum. The invariant. */
async function checkNettingInvariant(scope: TieScope, rounding: number): Promise<TieCheck> {
  const accounts = await grirAccounts();
  const rows: { label: string; left: number; right: number; difference: number }[] = [];
  let left = 0;
  let right = 0;

  for (const accountId of accounts) {
    const lines = await openLinesAsOf({
      asOf: scope.asOf,
      companies: scope.companies,
      accountIds: [accountId],
      rounding,
    });
    const nettable: NettableRow[] = lines.map((l) => ({ ...l, outstanding: l.residualAsOf }));
    const before = nettable.reduce((s, r) => s + r.residualAsOf, 0);
    const survivors = netOffsetting(nettable, rounding).get(accountId) ?? [];
    const after = survivors.reduce((s, r) => s + r.outstanding, 0);
    left += before;
    right += after;
    rows.push({
      label: `Akun #${accountId} — ${nettable.length} baris → ${survivors.length} baris`,
      left: before,
      right: after,
      difference: before - after,
    });
  }

  return {
    id: 8,
    title: "Invarian netting: jumlah bertanda tidak berubah",
    description:
      "Netting FIFO hanya memindahkan rupiah antar baris, tidak pernah menciptakan atau " +
      "menghilangkannya. Dijalankan atas akun GR/IR, tempat netting paling banyak bekerja.",
    leftLabel: "Sebelum netting",
    rightLabel: "Sesudah netting",
    left,
    right,
    difference: left - right,
    expectation: "Nol",
    state: verdict(left - right, rounding),
    note:
      "Inilah alasan angka utama di halaman Open Items dihitung tanpa netting sama sekali: " +
      "totalnya identik, sehingga tidak bisa dirusak oleh bug di port FIFO.",
    rows,
  };
}

/** Check 9 — GR/IR as-of against its GL balance. */
async function checkGrIrVsGl(scope: TieScope, rounding: number): Promise<TieCheck> {
  const accounts = await grirAccounts();
  if (!accounts.length) {
    return {
      id: 9,
      title: "GR/IR sama dengan saldo buku besarnya",
      description: "Tidak ada akun GR/IR yang teridentifikasi.",
      leftLabel: "As-of",
      rightLabel: "Buku besar",
      left: 0,
      right: 0,
      difference: 0,
      expectation: "Nol",
      state: "info",
      note: "Akun GR/IR dicari lewat prefix kode 21031091 dan levis_purchase_account_map.",
    };
  }

  const summary = await summaryByAccount({
    asOf: scope.asOf,
    companies: scope.companies,
    accountIds: accounts,
  });
  const asOf = summary.reduce((s, r) => s + r.outstanding, 0);

  const rows = await q<Record<string, string | null>>(
    `SELECT COALESCE(SUM(aml.balance), 0.0) AS balance
       FROM account_move_line aml
      WHERE aml.company_id = ANY($1::int[])
        AND aml.account_id = ANY($3::int[])
        AND aml.parent_state = 'posted'
        AND aml.date <= $2::date`,
    [scope.companies, scope.asOf, accounts],
  );
  const gl = num(rows[0]?.balance);

  return {
    id: 9,
    title: "GR/IR sama dengan saldo buku besarnya",
    description:
      "Outstanding GR/IR hasil perhitungan as-of dibandingkan saldo mentah akun GR/IR di " +
      "buku besar. Netting tidak mengubah jumlah, jadi keduanya wajib sama.",
    leftLabel: "Outstanding as-of",
    rightLabel: "Saldo buku besar",
    left: asOf,
    right: gl,
    difference: asOf - gl,
    expectation: "Nol",
    state: verdict(asOf - gl, rounding),
  };
}

/** Checks 10 and 12 — the clearing legs are a complete double entry. */
async function checkClearingLegs(scope: TieScope, rounding: number): Promise<TieCheck[]> {
  const legs = await legBalances(scope.companies);
  const byRun = new Map<number, { name: string; balance: number; legs: number; posted: number }>();
  for (const leg of legs) {
    const entry = byRun.get(leg.runId) ?? { name: leg.runName, balance: 0, legs: 0, posted: 0 };
    entry.balance += leg.balance;
    entry.legs += leg.legCount;
    entry.posted += leg.postedLines;
    byRun.set(leg.runId, entry);
  }

  const runs = Array.from(byRun.entries());
  const balanceRows = runs.map(([, r]) => ({
    label: r.name,
    left: r.balance,
    right: 0,
    difference: r.balance,
  }));
  const totalImbalance = runs.reduce((s, [, r]) => s + r.balance, 0);

  const postedRows = runs.map(([, r]) => ({
    label: r.name,
    left: r.legs,
    right: r.posted,
    difference: r.legs - r.posted,
  }));
  const totalLegs = runs.reduce((s, [, r]) => s + r.legs, 0);
  const totalPosted = runs.reduce((s, [, r]) => s + r.posted, 0);

  const noLegs = totalLegs === 0;

  return [
    {
      id: 10,
      title: "Leg clearing POS berjumlah nol per run",
      description: "Leg yang direncanakan adalah satu jurnal berpasangan lengkap.",
      leftLabel: "Jumlah leg",
      rightLabel: "Seharusnya",
      left: totalImbalance,
      right: 0,
      difference: totalImbalance,
      expectation: "Nol",
      state: noLegs ? "info" : verdict(totalImbalance, rounding),
      note: noLegs
        ? "Belum ada run yang mencapai tahap generate, jadi belum ada leg untuk diuji."
        : undefined,
      rows: balanceRows,
    },
    {
      id: 12,
      title: "Setiap leg punya baris jurnal terposting",
      description:
        "Leg tanpa move_line_id berarti rencana yang belum dibukukan — normal untuk run " +
        "yang belum diposting, dan wajib nol untuk run yang sudah.",
      leftLabel: "Leg direncanakan",
      rightLabel: "Leg terbukukan",
      left: totalLegs,
      right: totalPosted,
      difference: totalLegs - totalPosted,
      expectation: "Nol untuk run yang sudah diposting",
      state: noLegs ? "info" : totalLegs === totalPosted ? "ok" : "info",
      note: noLegs ? "Belum ada leg." : undefined,
      rows: postedRows,
    },
  ];
}

/** Check 11 — the shortfall equals what stayed on suspense. */
async function checkSuspenseDelta(scope: TieScope, rounding: number): Promise<TieCheck> {
  const rows = await q<Record<string, string | null>>(
    `SELECT r.id, r.name, r.state,
            COALESCE(SUM(l.short_amount), 0.0) AS short_amount,
            r.bal_suspense_before, r.bal_suspense_after_actual
       FROM levis_pos_clearing r
       LEFT JOIN levis_pos_clearing_line l ON l.run_id = r.id
      WHERE r.company_id = ANY($1::int[])
      GROUP BY r.id
      ORDER BY r.id`,
    [scope.companies],
  );

  const posted = rows.filter((r) => String(r.state) === "posted");
  const detail = posted.map((r) => {
    const short = num(r.short_amount);
    const delta = num(r.bal_suspense_after_actual) - num(r.bal_suspense_before);
    return { label: String(r.name ?? ""), left: short, right: delta, difference: short - delta };
  });

  const left = detail.reduce((s, r) => s + r.left, 0);
  const right = detail.reduce((s, r) => s + r.right, 0);

  return {
    id: 11,
    title: "Kekurangan settlement sama dengan sisa di akun suspense",
    description:
      "Yang tidak bisa dijelaskan oleh satu settlement tetap tinggal di suspense. Jumlahnya " +
      "harus sama dengan pergerakan saldo suspense yang tercatat pada run.",
    leftLabel: "Total short",
    rightLabel: "Perubahan saldo suspense",
    left,
    right,
    difference: left - right,
    expectation: "Nol",
    state: posted.length === 0 ? "info" : verdict(left - right, rounding),
    note:
      posted.length === 0
        ? `Belum ada run berstatus posted (${rows.length} run tercatat), jadi belum ada yang bisa diuji.`
        : undefined,
    rows: detail,
  };
}

/** Check 13 — what the excluded journals are worth. Named, not zero-expected. */
async function checkExcludedJournals(scope: TieScope): Promise<TieCheck> {
  const journals = await excludedJournals(scope);
  const total = journals.reduce((s, j) => s + j.balance, 0);
  return {
    id: 13,
    title: "Nilai jurnal yang dikecualikan dari laporan",
    description:
      "Jurnal bertanda x_custom_report_excluded tidak masuk neraca saldo maupun buku besar " +
      "laporan. Inilah seluruh selisih antara buku besar mentah dan neraca saldo.",
    leftLabel: "Saldo jurnal dikecualikan",
    rightLabel: "",
    left: total,
    right: 0,
    difference: total,
    expectation: "Boleh bukan nol — yang penting bernama, bukan celah tak dijelaskan",
    state: journals.length === 0 ? "ok" : "info",
    note:
      journals.length === 0
        ? "Tidak ada jurnal yang dikecualikan di database ini, jadi buku besar mentah dan neraca saldo memuat himpunan yang sama."
        : undefined,
    rows: journals.map((j) => ({
      label: `${j.code} ${j.name} (${j.lineCount} baris)`,
      left: j.balance,
      right: 0,
      difference: j.balance,
    })),
  };
}

/** Check 14 — a pointer, not a computation. */
function checkParityPointer(): TieCheck {
  return {
    id: 14,
    title: "Paritas terhadap report Odoo yang sesungguhnya",
    description:
      "Cek 1–13 hanya membuktikan konsistensi internal. Satu-satunya bukti bahwa dasbor ini " +
      "sama dengan Odoo adalah memanggil report-nya dan membandingkan totalnya.",
    leftLabel: "Dijalankan oleh",
    rightLabel: "",
    left: 0,
    right: 0,
    difference: 0,
    expectation: "npm run test:parity — butuh kredensial admin, jadi tidak dijalankan dari halaman ini",
    state: "info",
    note:
      "Skrip itu login ke Odoo, memanggil custom.report.trial.balance, custom.report.aged.payable " +
      "dan custom.report.gl.open.items dengan filter yang sama, lalu membandingkan grand total " +
      "dan total per akun. Hasil terakhirnya dicatat di README.",
  };
}

export async function runTieChecks(scope: TieScope, today: string): Promise<TieCheck[]> {
  const rounding = await companyRounding(scope.companies[0]);

  const [tb, ledger, ap, ar, bridge, view, identity, netting, grir, legs, suspense, excluded] =
    await Promise.all([
      checkTrialBalance(scope, rounding),
      checkLedgerZero(scope, rounding),
      checkAgingVsGl(scope, rounding, "payable", 3),
      checkAgingVsGl(scope, rounding, "receivable", 4),
      checkAgingBridge(scope, rounding),
      checkOpenItemsVsView(scope, rounding, today),
      checkSettlementIdentity(scope, rounding),
      checkNettingInvariant(scope, rounding),
      checkGrIrVsGl(scope, rounding),
      checkClearingLegs(scope, rounding),
      checkSuspenseDelta(scope, rounding),
      checkExcludedJournals(scope),
    ]);

  return [
    tb,
    ledger,
    ap,
    ar,
    bridge,
    view,
    identity,
    netting,
    grir,
    legs[0],
    suspense,
    legs[1],
    excluded,
    checkParityPointer(),
  ].sort((a, b) => a.id - b.id);
}
