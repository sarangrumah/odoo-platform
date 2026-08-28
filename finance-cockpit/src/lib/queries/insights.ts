// =============================================================================
// The recommendation engine.
//
// Deterministic: no model call anywhere in this file. Every finding is a
// threshold applied to a figure the dashboard already computes, and the
// narrative is a template with those figures substituted in. That is a
// deliberate limit — an accountant acting on a recommendation needs to be able
// to check the arithmetic, and a sentence a model wrote cannot be checked.
//
// Because the thresholds ARE the judgement, they are declared in one block at
// the top and printed on the page. A reader who disagrees with "90 days is old"
// can see that is what the engine believes, rather than discovering it by
// noticing an item missing.
//
// Ranking is by severity first and money second. A tie check that failed
// outranks a large overdue balance, because if the numbers do not reconcile
// then every other finding on the page is suspect.
// =============================================================================

import { num, q } from "@/lib/db";
import { count, dayLabel, rupiah } from "@/lib/format";
import { agingByPartner, totalsOf, upcomingDue } from "@/lib/queries/ap";
import { companyRounding } from "@/lib/queries/common";
import { grirAccounts, nettedForAccount, summaryByAccount } from "@/lib/queries/openitems";
import { clearingRuns, unreconciledStatements } from "@/lib/queries/pos";
import { closeAnomalies, draftMoves, lockExceptions } from "@/lib/queries/close";

/**
 * Every judgement this engine makes, in one place, printed on the page.
 *
 * These are not tuned constants — they are opinions, and the page says so.
 */
export const ASSUME = {
  /** An open item older than this is worth naming, whatever its size. */
  staleDays: 90,
  /** Below this, an amount is not worth a line on a briefing page. */
  materialAmount: 50_000_000,
  /** Overdue concentrated in this share of vendors is a concentration finding. */
  concentrationShare: 0.8,
  /** A vendor overdue by more than this is called out by name. */
  vendorOverdueDays: 60,
  /** Cash needed within this many days is "imminent". */
  imminentDays: 14,
  /** A netting ratio above this means the account is mostly noise. */
  nettingNoiseRatio: 10,
} as const;

export type Severity = "critical" | "warning" | "info";

export interface Finding {
  id: string;
  severity: Severity;
  title: string;
  /** The number, formatted, that the title is about. */
  figure: string;
  /** Two or three sentences: what it is, and what to do about it. */
  detail: string;
  href: string;
  /** Sorting weight within a severity — bigger money first. */
  weight: number;
}

const RANK: Record<Severity, number> = { critical: 0, warning: 1, info: 2 };

export interface InsightScope {
  asOf: string;
  companies: number[];
}

export async function briefing(scope: InsightScope): Promise<Finding[]> {
  const rounding = await companyRounding(scope.companies[0]);
  const link = (page: string) => `${page}?asOf=${scope.asOf}`;
  const findings: Finding[] = [];

  const [payable, openItems, grir, runs, statements, drafts, anomalies, exceptions, due] =
    await Promise.all([
      agingByPartner("payable", scope),
      summaryByAccount(scope),
      grirAccounts(),
      clearingRuns(scope.companies),
      unreconciledStatements(scope),
      draftMoves(scope),
      closeAnomalies(scope),
      lockExceptions(scope.companies),
      upcomingDue(scope),
    ]);

  // --- The ledger itself --------------------------------------------------
  const unbalanced = anomalies.find((a) => a.key === "unbalanced");
  if (unbalanced && unbalanced.count > 0) {
    findings.push({
      id: "unbalanced",
      severity: "critical",
      title: "Ada jurnal yang tidak seimbang",
      figure: `${count(unbalanced.count)} entry`,
      detail:
        `${count(unbalanced.count)} jurnal terposting punya jumlah balance bukan nol, senilai ` +
        `${rupiah(unbalanced.amount)}. Selama ini ada, tidak ada satu pun angka di dasbor yang ` +
        `boleh dipakai — perbaiki dulu sebelum apa pun yang lain.`,
      href: link("/close"),
      weight: unbalanced.amount,
    });
  }

  // --- Payables -----------------------------------------------------------
  const apTotals = totalsOf(payable);
  const overdue = Math.abs(apTotals.total - apTotals.buckets.not_due);
  const severe = Math.abs(
    apTotals.buckets.d_91_180 + apTotals.buckets.d_181_365 + apTotals.buckets.d_over_365,
  );

  if (severe >= ASSUME.materialAmount) {
    findings.push({
      id: "ap_severe",
      severity: "warning",
      title: `Hutang lewat ${ASSUME.staleDays} hari perlu dijelaskan`,
      figure: rupiah(severe),
      detail:
        `${rupiah(severe)} hutang sudah lewat 90 hari per ${dayLabel(scope.asOf)}. Pada umur ` +
        `sekian, biasanya bukan soal kas melainkan dokumen — tagihan yang disengketakan, ` +
        `penerimaan yang belum dicocokkan, atau vendor yang sudah tidak aktif.`,
      href: link("/ap"),
      weight: severe,
    });
  }

  // `partnerId === 0` is the no-partner bucket, not a counterparty. Calling it
  // "a vendor waiting 239 days" would be a sentence about nobody — the lines
  // are real, but there is no one to call about them, and they belong to the
  // data-quality finding instead.
  const overdueVendors = payable
    .filter((r) => r.partnerId !== 0)
    .map((r) => ({ name: r.partnerName, value: Math.abs(r.total - r.buckets.not_due), worst: r.maxOverdueDays }))
    .filter((v) => v.value > 0)
    .sort((a, b) => b.value - a.value);

  if (overdue >= ASSUME.materialAmount && overdueVendors.length > 1) {
    let running = 0;
    let n = 0;
    for (const v of overdueVendors) {
      running += v.value;
      n += 1;
      if (running / overdue >= ASSUME.concentrationShare) break;
    }
    if (n <= 5 && n < overdueVendors.length) {
      findings.push({
        id: "ap_concentration",
        severity: "info",
        title: `${count(n)} vendor memegang ${Math.round((running / overdue) * 100)}% tunggakan`,
        figure: rupiah(running),
        detail:
          `Dari ${rupiah(overdue)} tunggakan, ${rupiah(running)} ada di ${count(n)} vendor: ` +
          `${overdueVendors.slice(0, n).map((v) => v.name).join(", ")}. Menyelesaikan yang ` +
          `sedikit itu menyelesaikan hampir seluruh angkanya.`,
        href: link("/ap"),
        weight: running,
      });
    }
  }

  const longOverdue = overdueVendors.filter((v) => v.worst > ASSUME.vendorOverdueDays);
  if (longOverdue.length) {
    findings.push({
      id: "ap_long_overdue",
      severity: "info",
      title: `${count(longOverdue.length)} vendor menunggu lebih dari ${ASSUME.vendorOverdueDays} hari`,
      figure: rupiah(longOverdue.reduce((s, v) => s + v.value, 0)),
      detail:
        `Yang terlama: ${longOverdue
          .slice(0, 3)
          .map((v) => `${v.name} (${count(v.worst)} hari)`)
          .join(", ")}. Umur setua ini biasanya berarti dokumennya tersangkut, bukan kasnya.`,
      href: link("/ap"),
      weight: longOverdue.reduce((s, v) => s + v.value, 0),
    });
  }

  const imminent = due
    .filter((w) => {
      const days = Math.round(
        (new Date(`${w.weekStart}T00:00:00Z`).getTime() -
          new Date(`${scope.asOf}T00:00:00Z`).getTime()) /
          86_400_000,
      );
      return days <= ASSUME.imminentDays;
    })
    .reduce((s, w) => s + Math.abs(w.amount), 0);

  if (imminent >= ASSUME.materialAmount) {
    findings.push({
      id: "cash_imminent",
      severity: "warning",
      title: `Kas dibutuhkan dalam ${ASSUME.imminentDays} hari`,
      figure: rupiah(imminent),
      detail:
        `${rupiah(imminent)} hutang jatuh tempo dalam dua pekan setelah ${dayLabel(scope.asOf)}. ` +
        `Ini kebutuhan kas terdekat yang bisa dibaca dari buku, bukan proyeksi arus kas.`,
      href: link("/ap"),
      weight: imminent,
    });
  }

  // --- Open items and GR/IR ------------------------------------------------
  const stale = openItems.filter((a) => a.oldestAgeDays > ASSUME.staleDays);
  if (stale.length) {
    const worst = [...stale].sort((a, b) => b.oldestAgeDays - a.oldestAgeDays)[0];
    findings.push({
      id: "stale_open_items",
      severity: "info",
      title: `${count(stale.length)} akun menyimpan item lebih tua dari ${ASSUME.staleDays} hari`,
      figure: `${count(worst.oldestAgeDays)} hari`,
      detail:
        `Yang tertua ada di ${worst.code} ${worst.name}, berdiri sejak ` +
        `${worst.oldestDate ? dayLabel(worst.oldestDate) : "—"}. Item selama itu di akun ` +
        `rekonsiliasi jarang menjadi bersih dengan sendirinya.`,
      href: link("/openitems"),
      weight: stale.reduce((s, a) => s + Math.abs(a.outstanding), 0),
    });
  }

  if (grir.length) {
    const grirRows = openItems.filter((a) => grir.includes(a.accountId));
    const biggest = [...grirRows].sort((a, b) => b.lineCount - a.lineCount)[0];
    if (biggest && biggest.lineCount > 500) {
      const netted = await nettedForAccount(biggest.accountId, scope.asOf, scope.companies);
      const ratio = netted.linesAfter ? netted.linesBefore / netted.linesAfter : 0;
      if (ratio >= ASSUME.nettingNoiseRatio) {
        findings.push({
          id: "grir_noise",
          severity: "info",
          title: `GR/IR ${biggest.code} hampir seluruhnya saling menghapus`,
          figure: `${count(netted.linesBefore)} → ${count(netted.linesAfter)} baris`,
          detail:
            `Dari ${count(netted.linesBefore)} baris terbuka, hanya ${count(netted.linesAfter)} ` +
            `yang benar-benar tersisa setelah netting, senilai ${rupiah(netted.outstandingAfter)}. ` +
            `Sisanya adalah kredit penerimaan barang dan debit tagihan yang sudah berpasangan ` +
            `tapi tidak pernah direkonsiliasi di Odoo — layak dibereskan agar akunnya terbaca.`,
          href: `/openitems/${biggest.accountId}?asOf=${scope.asOf}`,
          weight: Math.abs(netted.outstandingAfter),
        });
      }
    }
  }

  // --- Bank and clearing ---------------------------------------------------
  const stmtLines = statements.reduce((s, r) => s + r.lineCount, 0);
  if (stmtLines > 0) {
    findings.push({
      id: "bank_unreconciled",
      severity: "warning",
      title: "Rekening koran belum cocok menghalangi lock date",
      figure: `${count(stmtLines)} baris`,
      detail:
        `${count(stmtLines)} baris rekening koran masih terbuka di ` +
        `${count(statements.length)} jurnal bank. Selama ada satu pun, Odoo menolak memasang ` +
        `lock date atas periodenya — jadi ini penghalang tutup buku, bukan sekadar catatan.`,
      href: link("/pos"),
      weight: Math.abs(statements.reduce((s, r) => s + r.amount, 0)),
    });
  }

  const unposted = runs.filter((r) => r.state !== "posted" && r.state !== "cancel");
  for (const run of unposted) {
    if (Math.abs(run.short) < rounding / 2 && !run.shortCount) continue;
    findings.push({
      id: `clearing_short_${run.id}`,
      severity: run.shortCount > 0 ? "warning" : "info",
      title: `Run kliring ${run.name} belum diposting`,
      figure: rupiah(run.short),
      detail:
        `Run ${run.periodRef} berstatus ${run.state} dengan ${count(run.shortCount)} baris kurang ` +
        `senilai ${rupiah(run.short)} dari ${count(run.lineCount)} baris. Selama belum diposting, ` +
        `piutang POS-nya tetap berdiri dan suspense-nya tetap terisi.`,
      href: `/pos/${run.id}?asOf=${scope.asOf}`,
      weight: Math.abs(run.short),
    });
  }

  // --- Close ---------------------------------------------------------------
  const draftCount = drafts.reduce((s, d) => s + d.moveCount, 0);
  if (draftCount > 0) {
    const oldest = [...drafts].sort((a, b) => a.period.localeCompare(b.period))[0];
    findings.push({
      id: "drafts",
      severity: "info",
      title: `${count(draftCount)} jurnal masih draft`,
      figure: rupiah(drafts.reduce((s, d) => s + d.amount, 0)),
      detail:
        `Yang tertua di periode ${oldest.period}, jurnal ${oldest.journalCode}. Draft di periode ` +
        `yang sudah lewat biasanya berarti entry yang ditinggalkan, bukan pekerjaan yang berjalan.`,
      href: link("/close"),
      weight: drafts.reduce((s, d) => s + d.amount, 0),
    });
  }

  for (const anomaly of anomalies) {
    if (!anomaly.isProblem || anomaly.count === 0 || anomaly.key === "unbalanced") continue;
    findings.push({
      id: `anomaly_${anomaly.key}`,
      severity: "info",
      title: anomaly.label,
      figure: `${count(anomaly.count)} baris`,
      detail: `${anomaly.detail} Nilainya ${rupiah(anomaly.amount)}.`,
      href: link("/close"),
      weight: anomaly.amount,
    });
  }

  const permanent = exceptions.filter((e) => e.permanent);
  if (permanent.length) {
    findings.push({
      id: "lock_exceptions",
      severity: "info",
      title: `${count(permanent.length)} lock exception permanen aktif`,
      figure: `id ${permanent.map((e) => e.id).join(", ")}`,
      detail:
        `Selama exception ini aktif, periode yang terlihat terkunci sebenarnya masih bisa ` +
        `ditulis. Yang ada di database ini memang disengaja — yang perlu diperhatikan adalah ` +
        `kalau jumlahnya bertambah.`,
      href: link("/close"),
      weight: 0,
    });
  }

  return findings.sort(
    (a, b) => RANK[a.severity] - RANK[b.severity] || b.weight - a.weight,
  );
}

/** Total unreconciled ledger movement, used by the page header. */
export async function ledgerPulse(scope: InsightScope): Promise<{ moves: number; lines: number }> {
  const rows = await q<Record<string, string | null>>(
    `SELECT COUNT(DISTINCT aml.move_id) AS moves, COUNT(*) AS lines
       FROM account_move_line aml
      WHERE aml.company_id = ANY($1::int[])
        AND aml.parent_state = 'posted'
        AND aml.date BETWEEN ($2::date - interval '30 days') AND $2::date`,
    [scope.companies, scope.asOf],
  );
  return { moves: num(rows[0]?.moves), lines: num(rows[0]?.lines) };
}
