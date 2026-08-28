// =============================================================================
// The skill catalogue — the ONLY door to the data.
//
// Both paths of the assistant go through this file: the deterministic matcher
// in intent.ts, and the sidecar escalation, which sees these skills as its
// complete tool list and has no other way to reach a database. That is what
// makes "this assistant only knows prd_levis_begbal's ledger" a structural
// property rather than a promise in a prompt — there is no free-form SQL
// anywhere in the assistant, only calls into queries/ that were already
// written, already parameterised, and already restricted to what `finance_ro`
// may SELECT.
//
// A skill answers in one sentence with the number in it. The table is
// supporting evidence, never the answer on its own.
//
// One rule specific to finance: every headline states its cut-off. A balance
// without a date is not an answer, it is a trap.
// =============================================================================

import { catalog } from "@/lib/agent/catalog";
import { count, dayLabel, rupiah } from "@/lib/format";
import { movementFrom } from "@/lib/agent/slots";
import {
  BUCKETS,
  agingAsOfTotals,
  agingByPartner,
  totalsOf,
  unpaidBills,
  upcomingDue,
  type AgingRow,
} from "@/lib/queries/ap";
import { companyRounding } from "@/lib/queries/common";
import {
  AGE_BANDS,
  ageBandsOf,
  grirAccounts,
  nettedForAccount,
  openItemsByAge,
  partnerBreakdown,
  summaryByAccount,
} from "@/lib/queries/openitems";
import { clearingRuns, tenderBalances, unreconciledStatements } from "@/lib/queries/pos";
import { closeAnomalies, draftMoves, lockExceptions, trialBalance } from "@/lib/queries/close";
import { runTieChecks } from "@/lib/queries/tie";
import { briefing } from "@/lib/queries/insights";

/** Everything a skill is allowed to know. No raw strings reach SQL from here. */
export interface SkillContext {
  asOf: string;
  companies: number[];
  accountIds: number[];
  partnerIds: number[];
  /** Rows to return. Clamped by the skill, never passed through verbatim. */
  limit?: number;
  /** How the cut-off was phrased, for the headline. */
  asOfLabel?: string;
  /** Today, so a skill can tell a historical question from a current one. */
  todayIso: string;
}

export interface SkillTable {
  columns: string[];
  rows: (string | number)[][];
}

export interface SkillResult {
  /** One sentence, Indonesian, containing the number that was asked for. */
  headline: string;
  /** At most ten rows of supporting detail. */
  table?: SkillTable;
  /** Path (no basePath) into the dashboard, carrying the same cut-off. */
  href?: string;
  /** Caveat printed under the answer when the data cannot carry the question. */
  note?: string;
}

export interface Skill {
  id: string;
  /** Doubles as the tool description handed to the sidecar. */
  description: string;
  run(ctx: SkillContext): Promise<SkillResult>;
}

// --- helpers -----------------------------------------------------------------

function link(page: string, ctx: SkillContext): string {
  return `${page}?asOf=${ctx.asOf}`;
}

/** The cut-off in words. Always present in a headline. */
function per(ctx: SkillContext): string {
  return `per ${dayLabel(ctx.asOf)}`;
}

const clamp = (n: number | undefined, fallback: number, max: number) =>
  Math.min(Math.max(Math.trunc(n ?? fallback) || fallback, 1), max);

/** Payables are negative in the ledger; a headline reads better in magnitude. */
const abs = (n: number) => Math.abs(n);

/**
 * Is the question about a date in the past?
 *
 * It matters more here than it looks. The aged reports read the CURRENT
 * `amount_residual`, which is what makes them tie to Odoo — and what makes them
 * understate a past date badly. On prd_levis_begbal at 2026-07-31 the parity
 * reading finds 3 open payable lines worth Rp 26 juta, because the other 420
 * have been paid since. Nobody asking "berapa hutang per akhir Juli" wants that
 * number handed to them without being told which of the two it is.
 */
function isPast(ctx: SkillContext): boolean {
  return ctx.asOf < ctx.todayIso;
}

function topPartners(rows: AgingRow[], limit: number, overdueOnly: boolean) {
  return rows
    .map((r) => ({
      name: r.partnerName,
      value: overdueOnly ? abs(r.total - r.buckets.not_due) : abs(r.total),
      items: r.itemCount,
      worst: r.maxOverdueDays,
    }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

// --- the catalogue -----------------------------------------------------------

export const SKILLS: Skill[] = [
  {
    id: "ap_summary",
    description:
      "Posisi hutang usaha pada satu tanggal: total terbuka, berapa yang lewat jatuh tempo, " +
      "jumlah vendor dan item, serta vendor dengan saldo terbesar.",
    async run(ctx) {
      const rows = await agingByPartner("payable", ctx);
      const t = totalsOf(rows);
      if (!t.itemCount) {
        return { headline: `Tidak ada hutang terbuka ${per(ctx)}.`, href: link("/ap", ctx) };
      }
      const overdue = t.total - t.buckets.not_due;
      const top = topPartners(rows, clamp(ctx.limit, 8, 20), false);
      const asOfTotals = isPast(ctx) ? await agingAsOfTotals("payable", ctx) : null;

      return {
        headline: asOfTotals
          ? `Hutang terbuka ${per(ctx)}: ${rupiah(abs(asOfTotals.total))} dari ` +
            `${count(asOfTotals.itemCount)} item, dibangun ulang ke tanggal itu.`
          : `Hutang terbuka ${per(ctx)}: ${rupiah(abs(t.total))} dari ${count(t.itemCount)} item ` +
            `dan ${count(t.partnerCount)} vendor, ${rupiah(abs(overdue))} di antaranya sudah lewat jatuh tempo.`,
        table: {
          columns: ["Vendor", "Saldo", "Item", "Terlama (hari)"],
          rows: top.map((r) => [r.name, rupiah(r.value), count(r.items), count(r.worst)]),
        },
        note: asOfTotals
          ? `Aged Payable di Odoo akan menunjukkan ${rupiah(abs(t.total))} untuk tanggal yang ` +
            `sama, karena report itu membaca residual hari ini — dokumen yang dibayar setelah ` +
            `tanggal potong sudah hilang dari sana. Tabel vendor di bawah memakai angka Odoo itu.`
          : undefined,
        href: link("/ap", ctx),
      };
    },
  },

  {
    id: "ap_overdue",
    description:
      "Umur tunggakan hutang: sebaran per bucket (belum jatuh tempo, 1–30, 31–60, 61–90, " +
      "91–180, 181–365, di atas 365 hari) dan vendor yang paling menunggak.",
    async run(ctx) {
      const rows = await agingByPartner("payable", ctx);
      const t = totalsOf(rows);
      const overdue = t.total - t.buckets.not_due;
      if (!t.itemCount) {
        return { headline: `Tidak ada hutang terbuka ${per(ctx)}.`, href: link("/ap", ctx) };
      }
      const severe = t.buckets.d_91_180 + t.buckets.d_181_365 + t.buckets.d_over_365;
      const top = topPartners(rows, clamp(ctx.limit, 8, 20), true);
      const asOfTotals = isPast(ctx) ? await agingAsOfTotals("payable", ctx) : null;
      const asOfOverdue = asOfTotals ? asOfTotals.total - asOfTotals.buckets.not_due : 0;

      return {
        headline: asOfTotals
          ? `${rupiah(abs(asOfOverdue))} hutang sudah lewat jatuh tempo ${per(ctx)}, dibangun ` +
            `ulang ke tanggal itu.`
          : `${rupiah(abs(overdue))} hutang sudah lewat jatuh tempo ${per(ctx)}, ` +
            `${rupiah(abs(severe))} di antaranya lewat 90 hari.`,
        table: {
          columns: ["Bucket", "Nilai"],
          rows: BUCKETS.map((b) => [b.label, rupiah(abs(t.buckets[b.code]))]),
        },
        note:
          [
            asOfTotals
              ? `Aged Payable Odoo menunjukkan ${rupiah(abs(overdue))} untuk tanggal yang sama, ` +
                `karena membaca residual hari ini.`
              : null,
            top.length
              ? `Penunggak terbesar: ${top
                  .slice(0, 3)
                  .map((r) => `${r.name} ${rupiah(r.value)}`)
                  .join(", ")}.`
              : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined,
        href: link("/ap", ctx),
      };
    },
  },

  {
    id: "ap_upcoming",
    description: "Hutang yang jatuh tempo dalam empat pekan setelah tanggal potong, per pekan.",
    async run(ctx) {
      const weeks = await upcomingDue(ctx);
      if (!weeks.length) {
        return {
          headline: `Tidak ada hutang yang jatuh tempo dalam empat pekan setelah ${dayLabel(ctx.asOf)}.`,
          href: link("/ap", ctx),
        };
      }
      const total = weeks.reduce((s, w) => s + w.amount, 0);
      return {
        headline:
          `${rupiah(abs(total))} jatuh tempo dalam empat pekan setelah ${dayLabel(ctx.asOf)}, ` +
          `tersebar di ${count(weeks.length)} pekan.`,
        table: {
          columns: ["Pekan mulai", "Item", "Nilai"],
          rows: weeks.map((w) => [dayLabel(w.weekStart), count(w.itemCount), rupiah(abs(w.amount))]),
        },
        href: link("/ap", ctx),
      };
    },
  },

  {
    id: "ar_summary",
    description: "Posisi piutang pada satu tanggal, dengan sebaran umurnya.",
    async run(ctx) {
      const rows = await agingByPartner("receivable", ctx);
      const t = totalsOf(rows);
      if (!t.itemCount) {
        return { headline: `Tidak ada piutang terbuka ${per(ctx)}.`, href: link("/ap", ctx) };
      }
      return {
        headline:
          `Piutang terbuka ${per(ctx)}: ${rupiah(abs(t.total))} dari ${count(t.itemCount)} item.`,
        table: {
          columns: ["Bucket", "Nilai"],
          rows: BUCKETS.map((b) => [b.label, rupiah(abs(t.buckets[b.code]))]),
        },
        note:
          "Sebagian besar piutang di database ini adalah piutang POS per tender, yang tidak " +
          "mencatat pelanggan — pergerakannya ditangani lewat kliring POS, bukan penagihan.",
        href: link("/ap", ctx),
      };
    },
  },

  {
    id: "open_items",
    description:
      "Saldo belum tuntas di seluruh akun rekonsiliasi pada satu tanggal, per akun: berapa " +
      "nilainya, berapa barisnya, dan sejak kapan item tertuanya berdiri.",
    async run(ctx) {
      const rows = await summaryByAccount({
        asOf: ctx.asOf,
        companies: ctx.companies,
        accountIds: ctx.accountIds.length ? ctx.accountIds : undefined,
      });
      if (!rows.length) {
        return { headline: `Tidak ada open item ${per(ctx)}.`, href: link("/openitems", ctx) };
      }
      const total = rows.reduce((s, r) => s + r.outstanding, 0);
      const lines = rows.reduce((s, r) => s + r.lineCount, 0);
      const top = [...rows].sort((a, b) => abs(b.outstanding) - abs(a.outstanding)).slice(0, clamp(ctx.limit, 8, 20));

      return {
        headline:
          `${rupiah(total)} open item ${per(ctx)} di ${count(rows.length)} akun rekonsiliasi, ` +
          `dari ${count(lines)} baris.`,
        table: {
          columns: ["Akun", "Baris", "Outstanding", "Terlama"],
          rows: top.map((r) => [
            `${r.code} ${r.name}`,
            count(r.lineCount),
            rupiah(r.outstanding),
            r.oldestDate ? dayLabel(r.oldestDate) : "—",
          ]),
        },
        note:
          "Angka ini dihitung tanpa netting; netting tidak mengubah jumlah bertandanya, hanya " +
          "berapa baris yang tersisa.",
        href: link("/openitems", ctx),
      };
    },
  },

  {
    id: "grir",
    description:
      "Posisi GR/IR — penerimaan barang yang belum bertemu tagihan vendor — pada satu tanggal, " +
      "sebelum dan sesudah netting FIFO.",
    async run(ctx) {
      const accounts = await grirAccounts();
      if (!accounts.length) {
        return { headline: "Tidak ada akun GR/IR yang teridentifikasi di database ini." };
      }
      const rows = await summaryByAccount({
        asOf: ctx.asOf,
        companies: ctx.companies,
        accountIds: accounts,
      });
      const total = rows.reduce((s, r) => s + r.outstanding, 0);
      const lines = rows.reduce((s, r) => s + r.lineCount, 0);

      // Netting the biggest account is what turns the number into something a
      // person can act on; doing all of them would be a page load, not an answer.
      const biggest = [...rows].sort((a, b) => abs(b.outstanding) - abs(a.outstanding))[0];
      const netted = biggest
        ? await nettedForAccount(biggest.accountId, ctx.asOf, ctx.companies)
        : null;

      return {
        headline:
          `GR/IR ${per(ctx)}: ${rupiah(total)} dari ${count(lines)} baris terbuka di ` +
          `${count(rows.length)} akun.` +
          (netted
            ? ` Di ${biggest.code}, netting menyisakan ${count(netted.linesAfter)} baris dari ${count(netted.linesBefore)}.`
            : ""),
        table: {
          columns: ["Akun", "Baris", "Outstanding", "Terlama"],
          rows: rows.map((r) => [
            `${r.code} ${r.name}`,
            count(r.lineCount),
            rupiah(r.outstanding),
            r.oldestDate ? dayLabel(r.oldestDate) : "—",
          ]),
        },
        href: biggest ? `/openitems/${biggest.accountId}?asOf=${ctx.asOf}` : link("/openitems", ctx),
      };
    },
  },

  {
    id: "account_detail",
    description:
      "Isi satu akun rekonsiliasi setelah netting: siapa lawan transaksinya, berapa barisnya " +
      "yang tersisa, dan berapa nilainya. Butuh nama atau kode akun di pertanyaan.",
    async run(ctx) {
      const id = ctx.accountIds[0];
      if (!id) {
        return { headline: "Sebutkan nama atau kode akunnya, misalnya 2103109121 atau GR/IR." };
      }
      const cat = await catalog();
      const account = cat.byAccountId.get(id);
      const netted = await nettedForAccount(id, ctx.asOf, ctx.companies);
      const partners = await partnerBreakdown(netted);

      if (!netted.linesBefore) {
        return {
          headline: `${account?.code ?? id} ${account?.name ?? ""} tidak punya open item ${per(ctx)}.`,
          href: `/openitems/${id}?asOf=${ctx.asOf}`,
        };
      }

      return {
        headline:
          `${account?.code ?? id} ${account?.name ?? ""} ${per(ctx)}: ` +
          `${rupiah(netted.outstandingAfter)} tersisa di ${count(netted.linesAfter)} baris ` +
          `setelah netting, dari ${count(netted.linesBefore)} baris terbuka.`,
        table: {
          columns: ["Lawan transaksi", "Baris", "Outstanding", "Terlama"],
          rows: partners
            .slice(0, clamp(ctx.limit, 8, 20))
            .map((p) => [
              p.partnerName,
              count(p.lineCount),
              rupiah(p.outstanding),
              p.oldestDate ? dayLabel(p.oldestDate) : "—",
            ]),
        },
        href: `/openitems/${id}?asOf=${ctx.asOf}`,
      };
    },
  },

  {
    id: "oldest_items",
    description:
      "Umur open item: sebaran per rentang umur, dan akun mana yang menyimpan item paling lama.",
    async run(ctx) {
      const [bands, rows] = await Promise.all([
        openItemsByAge({
          asOf: ctx.asOf,
          companies: ctx.companies,
          accountIds: ctx.accountIds.length ? ctx.accountIds : undefined,
        }),
        summaryByAccount({
          asOf: ctx.asOf,
          companies: ctx.companies,
          accountIds: ctx.accountIds.length ? ctx.accountIds : undefined,
        }),
      ]);

      const oldest = [...rows].sort((a, b) => b.oldestAgeDays - a.oldestAgeDays).slice(0, 5);
      const stale = bands
        .filter((b) => b.code !== "d_0_30" && b.code !== "d_31_60")
        .reduce((s, b) => s + b.outstanding, 0);

      return {
        headline:
          `Open item berumur di atas 60 hari ${per(ctx)}: ${rupiah(stale)}.` +
          (oldest[0]
            ? ` Yang tertua ada di ${oldest[0].code}, sudah ${count(oldest[0].oldestAgeDays)} hari.`
            : ""),
        table: {
          columns: ["Umur", "Baris", "Outstanding"],
          rows: bands.map((b) => [b.label, count(b.lineCount), rupiah(b.outstanding)]),
        },
        note: oldest.length
          ? `Akun beritem tertua: ${oldest
              .map((a) => `${a.code} (${count(a.oldestAgeDays)} hari)`)
              .join(", ")}.`
          : undefined,
        href: link("/openitems", ctx),
      };
    },
  },

  {
    id: "pos_clearing",
    description:
      "Kesehatan kliring POS: run yang tercatat, berapa yang teralokasi dan berapa yang kurang, " +
      "serta saldo piutang POS per tender yang masih menunggu settlement.",
    async run(ctx) {
      const [runs, tenders] = await Promise.all([
        clearingRuns(ctx.companies),
        tenderBalances(ctx),
      ]);
      const tenderTotal = tenders.reduce((s, t) => s + t.balance, 0);

      if (!runs.length) {
        return {
          headline:
            `Belum ada run kliring POS di database ini. Piutang POS terbuka ${per(ctx)}: ` +
            `${rupiah(tenderTotal)}.`,
          href: link("/pos", ctx),
        };
      }

      const latest = runs[0];
      return {
        headline:
          `Run terakhir ${latest.name} (${latest.periodRef}) berstatus ${latest.state}: ` +
          `bruto ${rupiah(latest.gross)}, teralokasi ${rupiah(latest.allocated)}, ` +
          `kurang ${rupiah(latest.short)} di ${count(latest.shortCount)} baris. ` +
          `Piutang POS terbuka ${per(ctx)}: ${rupiah(tenderTotal)}.`,
        table: {
          columns: ["Tender", "Baris terbuka", "Saldo"],
          rows: tenders
            .filter((t) => t.balance)
            .map((t) => [t.name.replace(/^POS Receivable - /, ""), count(t.openLines), rupiah(t.balance)]),
        },
        href: `/pos/${latest.id}?asOf=${ctx.asOf}`,
      };
    },
  },

  {
    id: "bank_unreconciled",
    description:
      "Baris rekening koran yang belum direkonsiliasi per jurnal bank — yang menghalangi lock date.",
    async run(ctx) {
      const rows = await unreconciledStatements(ctx);
      if (!rows.length) {
        return {
          headline: `Semua baris rekening koran sudah cocok ${per(ctx)}.`,
          href: link("/pos", ctx),
        };
      }
      const total = rows.reduce((s, r) => s + r.lineCount, 0);
      return {
        headline:
          `${count(total)} baris rekening koran belum direkonsiliasi ${per(ctx)}, ` +
          `tersebar di ${count(rows.length)} jurnal bank.`,
        table: {
          columns: ["Jurnal", "Baris", "Nilai", "Terlama"],
          rows: rows.map((r) => [
            r.journalCode,
            count(r.lineCount),
            rupiah(r.amount),
            r.oldest ? dayLabel(r.oldest) : "—",
          ]),
        },
        note:
          "Selama baris ini masih terbuka, Odoo menolak memasang lock date atas periodenya — " +
          "jadi angka ini adalah penghalang tutup buku, bukan sekadar catatan.",
        href: link("/pos", ctx),
      };
    },
  },

  {
    id: "close_readiness",
    description:
      "Kesiapan tutup buku pada satu tanggal: jurnal draft, lock date dan exception yang aktif, " +
      "serta temuan kualitas data yang perlu ditindaklanjuti.",
    async run(ctx) {
      const [drafts, anomalies, exceptions] = await Promise.all([
        draftMoves(ctx),
        closeAnomalies(ctx),
        lockExceptions(ctx.companies),
      ]);
      const draftCount = drafts.reduce((s, d) => s + d.moveCount, 0);
      const problems = anomalies.filter((a) => a.isProblem && a.count > 0);
      const permanent = exceptions.filter((e) => e.permanent);

      return {
        headline:
          `Kesiapan tutup buku ${per(ctx)}: ${count(draftCount)} jurnal draft, ` +
          `${count(problems.length)} temuan kualitas data, ` +
          `${count(permanent.length)} lock exception permanen aktif.`,
        table: {
          columns: ["Pemeriksaan", "Jumlah", "Nilai"],
          rows: anomalies.map((a) => [a.label, count(a.count), a.amount ? rupiah(a.amount) : "—"]),
        },
        note: permanent.length
          ? "Lock exception permanen di database ini memang disengaja — halaman Kesiapan Tutup Buku menyebut berapa yang diharapkan."
          : undefined,
        href: link("/close", ctx),
      };
    },
  },

  {
    id: "trial_balance",
    description:
      "Neraca saldo: apakah debit dan kredit penutup seimbang, dan akun apa yang terbesar.",
    async run(ctx) {
      const rows = await trialBalance({
        from: movementFrom(ctx.asOf),
        to: ctx.asOf,
        companies: ctx.companies,
      });
      const debit = rows.reduce((s, r) => s + r.closingDebit, 0);
      const credit = rows.reduce((s, r) => s + r.closingCredit, 0);
      const rounding = await companyRounding(ctx.companies[0]);
      const balanced = Math.abs(debit - credit) < rounding / 2;

      return {
        headline:
          `Neraca saldo ${per(ctx)} ${balanced ? "seimbang" : "TIDAK seimbang"}: ` +
          `debit penutup ${rupiah(debit)}, kredit penutup ${rupiah(credit)}` +
          (balanced ? "." : `, selisih ${rupiah(debit - credit)}.`),
        table: {
          columns: ["Akun", "Debit penutup", "Kredit penutup"],
          rows: [...rows]
            .sort((a, b) => b.closingDebit + b.closingCredit - (a.closingDebit + a.closingCredit))
            .slice(0, clamp(ctx.limit, 8, 20))
            .map((r) => [`${r.code} ${r.name}`, rupiah(r.closingDebit), rupiah(r.closingCredit)]),
        },
        href: link("/close", ctx),
      };
    },
  },

  {
    id: "tie",
    description:
      "Hasil pembuktian angka: berapa dari empat belas cek yang cocok, dan mana yang tidak.",
    async run(ctx) {
      const checks = await runTieChecks(
        { asOf: ctx.asOf, from: movementFrom(ctx.asOf), companies: ctx.companies },
        ctx.asOf,
      );
      const failed = checks.filter((c) => c.state === "bad");
      const ok = checks.filter((c) => c.state === "ok");

      return {
        headline: failed.length
          ? `${count(failed.length)} dari ${count(checks.length)} cek tidak cocok ${per(ctx)}: nomor ${failed
              .map((c) => c.id)
              .join(", ")}.`
          : `Semua cek cocok atau terjelaskan ${per(ctx)} — ${count(ok.length)} cocok, ` +
            `${count(checks.length - ok.length)} berupa penjelasan.`,
        table: {
          columns: ["Cek", "Status", "Selisih"],
          rows: checks.map((c) => [
            `${c.id}. ${c.title}`,
            c.state === "ok" ? "cocok" : c.state === "bad" ? "TIDAK COCOK" : "penjelasan",
            rupiah(c.difference),
          ]),
        },
        href: link("/tie", ctx),
      };
    },
  },

  {
    id: "briefing",
    description:
      "Apa yang paling perlu dikerjakan sekarang: temuan berperingkat dari seluruh dasbor, " +
      "dengan angka dan tautan ke halamannya.",
    async run(ctx) {
      const findings = await briefing({ asOf: ctx.asOf, companies: ctx.companies });
      if (!findings.length) {
        return {
          headline: `Tidak ada temuan yang menonjol ${per(ctx)}.`,
          href: link("/actions", ctx),
        };
      }
      return {
        headline: `${count(findings.length)} temuan ${per(ctx)}. Yang teratas: ${findings[0].title}.`,
        table: {
          // The panel is 380px wide. A 40-character title pushes the figure off
          // the right edge entirely, which turns a two-column table into a
          // one-column list of half-sentences — so the title is trimmed here
          // rather than left to a scrollbar nobody finds.
          columns: ["Temuan", "Angka"],
          rows: findings
            .slice(0, clamp(ctx.limit, 6, 12))
            .map((f) => [f.title.length > 30 ? `${f.title.slice(0, 29)}…` : f.title, f.figure]),
        },
        href: link("/actions", ctx),
      };
    },
  },
];

export const SKILL_BY_ID = new Map(SKILLS.map((s) => [s.id, s]));

/** Ages a set of netted rows — exposed so the sidecar cannot invent its own. */
export { ageBandsOf, AGE_BANDS };
