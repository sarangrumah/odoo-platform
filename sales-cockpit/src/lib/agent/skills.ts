// =============================================================================
// The skill catalogue — the ONLY door to the data.
//
// Both paths of the assistant go through this file: the deterministic matcher
// in intent.ts, and (later) the Claude Code sidecar, which sees these skills as
// its complete tool list and has no other way to reach a database. That is what
// makes "knowledge limited to prd_levis_begbal" a structural property rather
// than a promise in a prompt: there is no free-form SQL anywhere in the
// assistant, only these calls into queries/ which were already written, already
// parameterised, and already restricted to what `cockpit_ro` may SELECT.
//
// A skill answers in one sentence with the number in it. The table is
// supporting evidence, never the answer on its own — somebody reading this on a
// phone should be able to stop after the headline.
// =============================================================================

import { catalog } from "@/lib/agent/catalog";
import { serialiseFilters, type Extent, type Filters } from "@/lib/filters";
import { count, dayLabel, decimal, monthLabel, percent, rupiah, rupiahShort } from "@/lib/format";
import {
  associateLeaderboard,
  categoryMix,
  coverage,
  dailyTrend,
  kpis,
  reconciliation,
  silentStores,
  storeRanking,
  topCategories,
  topProducts,
} from "@/lib/queries/sales";
import { briefing } from "@/lib/queries/insights";

/** Everything a skill is allowed to know. No raw strings reach SQL from here. */
export interface SkillContext {
  filters: Filters;
  extent: Extent;
  /** Rows to return. Clamped by the skill, never passed through verbatim. */
  limit?: number;
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
  /** Path (no basePath) into the cockpit with the same filters applied. */
  href?: string;
  /** Caveat printed under the answer when the data cannot carry the question. */
  note?: string;
}

export interface Skill {
  id: string;
  /** Doubles as the tool description handed to the sidecar. */
  description: string;
  /** Slots this skill can use; drives both the matcher and the tool schema. */
  slots: ("range" | "stores" | "categories" | "membership" | "limit")[];
  run(ctx: SkillContext): Promise<SkillResult>;
}

// --- helpers -----------------------------------------------------------------

/** Deep link back into the dashboard carrying the filters that produced it. */
function link(page: string, ctx: SkillContext): string {
  const sp = serialiseFilters(ctx.filters, ctx.extent);
  const qs = sp.toString();
  return qs ? `${page}?${qs}` : page;
}

/** The period in words, for the headline. "1 Jun 2026 – 9 Agu 2026". */
function periodLabel(f: Filters): string {
  return f.from === f.to ? dayLabel(f.from) : `${dayLabel(f.from)} – ${dayLabel(f.to)}`;
}

/** The scope in words, so the reader can see which slice was measured. */
function scopeLabel(ctx: SkillContext, storeNames: Map<number, string>): string {
  const f = ctx.filters;
  const parts: string[] = [];
  if (f.stores.length === 1) parts.push(storeNames.get(f.stores[0]) ?? "toko terpilih");
  else if (f.stores.length > 1) parts.push(`${f.stores.length} toko terpilih`);
  if (f.categories.length === 1) parts.push(f.categories[0]);
  else if (f.categories.length > 1) parts.push(`${f.categories.length} kategori`);
  if (f.membership) parts.push(f.membership === "member" ? "member saja" : "non-member saja");
  return parts.length ? ` (${parts.join(", ")})` : "";
}

const clamp = (n: number | undefined, fallback: number, max: number) =>
  Math.min(Math.max(Math.trunc(n ?? fallback) || fallback, 1), max);

/** Zero rows is a real answer, not an error — say so plainly. */
function empty(ctx: SkillContext, what: string): SkillResult {
  return {
    headline: `Tidak ada ${what} pada ${periodLabel(ctx.filters)}.`,
    note:
      `Data POS tersedia ${dayLabel(ctx.extent.start)} sampai ${dayLabel(ctx.extent.end)}; ` +
      `di luar rentang itu memang kosong.`,
  };
}

// --- the catalogue -----------------------------------------------------------

export const SKILLS: Skill[] = [
  {
    id: "kpi",
    description:
      "Angka penjualan pokok untuk sebuah periode: omzet kotor, jumlah transaksi, unit terjual, " +
      "ATV (nilai transaksi rata-rata), UPT, ASP, porsi transaksi berdiskon, porsi transaksi member.",
    slots: ["range", "stores", "categories", "membership"],
    async run(ctx) {
      const k = await kpis(ctx.filters);
      if (!k.transactions) return empty(ctx, "transaksi");

      const names = (await catalog()).byStoreId;
      return {
        headline:
          `Penjualan ${periodLabel(ctx.filters)}${scopeLabel(ctx, names)}: ` +
          `${rupiah(k.gross)} dari ${count(k.transactions)} transaksi ` +
          `(ATV ${rupiah(k.atv)}).`,
        table: {
          columns: ["Metrik", "Nilai"],
          rows: [
            ["Omzet kotor", rupiah(k.gross)],
            ["Transaksi", count(k.transactions)],
            ["Unit terjual", count(k.units)],
            ["ATV", rupiah(k.atv)],
            ["UPT", decimal(k.upt)],
            ["ASP", rupiah(k.asp)],
            ["Transaksi berdiskon", percent(k.discountShare)],
            ["Transaksi member", percent(k.memberShare)],
          ],
        },
        href: link("/overview", ctx),
      };
    },
  },

  {
    id: "trend",
    description:
      "Tren penjualan harian dalam periode: hari tertinggi, hari terendah, rata-rata per hari, " +
      "dan daftar hari terakhir beserta omzet dan transaksinya.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const days = await dailyTrend(ctx.filters);
      if (!days.length) return empty(ctx, "hari dengan penjualan");

      const best = days.reduce((a, b) => (b.gross > a.gross ? b : a));
      const worst = days.reduce((a, b) => (b.gross < a.gross ? b : a));
      const total = days.reduce((s, d) => s + d.gross, 0);
      const shown = days.slice(-clamp(ctx.limit, 10, 10));

      return {
        headline:
          `Selama ${periodLabel(ctx.filters)} ada ${count(days.length)} hari berjualan, ` +
          `rata-rata ${rupiah(total / days.length)} per hari. ` +
          `Tertinggi ${dayLabel(best.day)} (${rupiah(best.gross)}), ` +
          `terendah ${dayLabel(worst.day)} (${rupiah(worst.gross)}).`,
        table: {
          columns: ["Hari", "Omzet", "Transaksi"],
          rows: shown.map((d) => [dayLabel(d.day), rupiah(d.gross), count(d.transactions)]),
        },
        href: link("/overview", ctx),
      };
    },
  },

  {
    id: "store_ranking",
    description:
      "Peringkat toko berdasarkan omzet dalam periode, lengkap dengan transaksi, ATV, dan porsi " +
      "member per toko. Dipakai untuk 'toko mana yang paling tinggi/rendah'.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const rows = await storeRanking(ctx.filters);
      if (!rows.length) return empty(ctx, "toko dengan penjualan");

      const top = rows[0];
      const total = rows.reduce((s, r) => s + r.gross, 0);
      const limit = clamp(ctx.limit, 10, 10);

      return {
        headline:
          `${top.name} memimpin ${periodLabel(ctx.filters)} dengan ${rupiah(top.gross)} ` +
          `(${percent(total ? top.gross / total : 0)} dari ${count(rows.length)} toko aktif).`,
        table: {
          columns: ["Toko", "Omzet", "Transaksi", "ATV"],
          rows: rows
            .slice(0, limit)
            .map((r) => [r.name, rupiah(r.gross), count(r.transactions), rupiah(r.atv)]),
        },
        href: link("/stores", ctx),
      };
    },
  },

  {
    id: "store_detail",
    description:
      "Ringkasan satu toko tertentu dalam periode: omzet, transaksi, ATV, UPT, porsi member, " +
      "dan peringkatnya di antara toko lain. Butuh nama toko disebut.",
    slots: ["range", "stores", "categories", "membership"],
    async run(ctx) {
      const picked = new Set(ctx.filters.stores);
      // Ranking must be computed across the whole fleet, otherwise "peringkat 3"
      // would be measured against a one-store list and always read "peringkat 1".
      const fleet = await storeRanking({ ...ctx.filters, stores: [] });
      const rows = fleet.filter((r) => picked.has(r.id));
      if (!rows.length) return empty(ctx, "transaksi di toko itu");

      const r = rows[0];
      const rank = fleet.findIndex((x) => x.id === r.id) + 1;

      return {
        headline:
          `${r.name} membukukan ${rupiah(r.gross)} dari ${count(r.transactions)} transaksi ` +
          `pada ${periodLabel(ctx.filters)} — peringkat ${rank} dari ${count(fleet.length)} toko.`,
        table: {
          columns: ["Metrik", "Nilai"],
          rows: [
            ["Omzet", rupiah(r.gross)],
            ["Transaksi", count(r.transactions)],
            ["Unit", count(r.units)],
            ["ATV", rupiah(r.atv)],
            ["UPT", decimal(r.upt)],
            ["Porsi member", percent(r.memberShare)],
            ["Peringkat", `${rank} dari ${count(fleet.length)}`],
          ],
        },
        href: link("/stores", ctx),
      };
    },
  },

  {
    id: "silent_stores",
    description:
      "Toko yang sama sekali tidak punya transaksi dalam periode — toko diam. Dipakai untuk " +
      "'toko mana yang tidak ada penjualan / kosong / tidak setor'.",
    slots: ["range", "stores", "categories", "membership"],
    async run(ctx) {
      const rows = await silentStores(ctx.filters);
      if (!rows.length) {
        return {
          headline: `Semua toko membukukan transaksi pada ${periodLabel(ctx.filters)} — tidak ada yang diam.`,
          href: link("/stores", ctx),
        };
      }
      return {
        headline:
          `${count(rows.length)} toko tanpa satu pun transaksi pada ${periodLabel(ctx.filters)}: ` +
          `${rows.slice(0, 3).map((r) => r.name).join(", ")}${rows.length > 3 ? ", dan lainnya" : ""}.`,
        table: {
          columns: ["Toko diam"],
          rows: rows.slice(0, 10).map((r) => [r.name]),
        },
        href: link("/stores", ctx),
        note:
          "Toko diam bisa berarti tutup, belum onboarding, atau feed-nya belum masuk — " +
          "data ini tidak bisa membedakan ketiganya.",
      };
    },
  },

  {
    id: "top_products",
    description:
      "Produk terlaris berdasarkan omzet dalam periode, dengan kode SKU, kategori, unit terjual, " +
      "dan di berapa toko produk itu terjual.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const limit = clamp(ctx.limit, 10, 10);
      const rows = await topProducts(ctx.filters, limit);
      if (!rows.length) return empty(ctx, "produk terjual");

      const top = rows[0];
      return {
        headline:
          `Produk terlaris ${periodLabel(ctx.filters)} adalah ${top.name} (${top.code}) ` +
          `dengan ${rupiah(top.gross)} dari ${count(top.units)} unit.`,
        table: {
          columns: ["Kode", "Produk", "Omzet", "Unit"],
          rows: rows.map((r) => [r.code, r.name, rupiah(r.gross), count(r.units)]),
        },
        href: link("/products", ctx),
      };
    },
  },

  {
    id: "category_mix",
    description:
      "Kategori produk yang paling besar kontribusinya dalam periode, dengan omzet, unit, dan " +
      "porsi terhadap total.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const limit = clamp(ctx.limit, 10, 10);
      const [rows, all] = await Promise.all([
        topCategories(ctx.filters, limit),
        categoryMix(ctx.filters),
      ]);
      if (!rows.length) return empty(ctx, "kategori dengan penjualan");

      const total = all.reduce((s, r) => s + r.gross, 0);
      const top = rows[0];
      return {
        headline:
          `Kategori terbesar ${periodLabel(ctx.filters)} adalah ${top.name} ` +
          `dengan ${rupiah(top.gross)} (${percent(total ? top.gross / total : 0)} dari total).`,
        table: {
          columns: ["Kategori", "Omzet", "Unit", "Porsi"],
          rows: rows.map((r) => [
            r.name,
            rupiah(r.gross),
            count(r.units),
            percent(total ? r.gross / total : 0),
          ]),
        },
        href: link("/products", ctx),
      };
    },
  },

  {
    id: "associates",
    description:
      "Peringkat SPG / kasir (staff) berdasarkan omzet dalam periode, dengan toko asal, transaksi, " +
      "ATV, dan porsi transaksi berdiskon.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const rows = await associateLeaderboard(ctx.filters);
      if (!rows.length) return empty(ctx, "penjualan atas nama staff");

      const limit = clamp(ctx.limit, 10, 10);
      const named = rows.filter((r) => r.name !== "(tanpa nama)");
      const top = named[0] ?? rows[0];
      return {
        headline:
          `${top.name} (${top.store}) memimpin ${periodLabel(ctx.filters)} dengan ${rupiah(top.gross)} ` +
          `dari ${count(top.transactions)} transaksi.`,
        table: {
          columns: ["Nama", "Toko", "Omzet", "Transaksi", "ATV"],
          rows: rows
            .slice(0, limit)
            .map((r) => [r.name, r.store, rupiah(r.gross), count(r.transactions), rupiah(r.atv)]),
        },
        href: link("/associates", ctx),
        note: rows.some((r) => r.name === "(tanpa nama)")
          ? "Sebagian baris tidak membawa nama staff, jadi peringkat ini tidak mencakup seluruh penjualan."
          : undefined,
      };
    },
  },

  {
    id: "recon",
    description:
      "Rekonsiliasi POS terhadap General Ledger per bulan: penjualan POS di luar pajak dibanding " +
      "pendapatan yang sudah diposting di GL, beserta selisihnya. Selalu seluruh dataset, tidak " +
      "mengikuti filter.",
    slots: [],
    async run(ctx) {
      const rows = await reconciliation();
      if (!rows.length) return empty(ctx, "bulan untuk direkonsiliasi");

      const off = rows.filter((r) => Math.round(r.diff) !== 0);
      return {
        headline: off.length
          ? `${count(off.length)} dari ${count(rows.length)} bulan belum nol: selisih terbesar ` +
            `${rupiah(Math.max(...off.map((r) => Math.abs(r.diff))))}.`
          : `Seluruh ${count(rows.length)} bulan rekonsiliasi POS terhadap GL nol rupiah.`,
        table: {
          columns: ["Bulan", "POS (ex pajak)", "GL pendapatan", "Selisih"],
          rows: rows
            .slice(-10)
            .map((r) => [monthLabel(r.month), rupiah(r.posExTax), rupiah(r.glIncome), rupiah(r.diff)]),
        },
        href: "/trust",
      };
    },
  },

  {
    id: "coverage",
    description:
      "Cakupan dan kualitas data: tanggal pertama dan terakhir yang ada datanya, jumlah order dan " +
      "baris, baris retur, baris tanpa nama staff, dan apakah harga pokok tersedia.",
    slots: [],
    async run() {
      const c = await coverage();
      return {
        headline:
          `Data POS mencakup ${dayLabel(c.firstOrder)} sampai ${dayLabel(c.lastOrder)}: ` +
          `${count(c.orders)} order, ${count(c.lines)} baris.`,
        table: {
          columns: ["Aspek", "Nilai"],
          rows: [
            ["Hari pertama", dayLabel(c.firstOrder)],
            ["Hari terakhir", dayLabel(c.lastOrder)],
            ["Order", count(c.orders)],
            ["Baris", count(c.lines)],
            ["Baris retur", count(c.returnLines)],
            ["Baris tanpa nama staff", count(c.linesWithoutStaff)],
            ["Metode pembayaran", count(c.distinctPaymentMethods)],
            ["Baris ber-harga pokok", count(c.linesWithCost)],
          ],
        },
        href: "/trust",
        note:
          c.linesWithCost === 0
            ? "Harga pokok kosong di seluruh dataset, jadi margin dan laba tidak bisa dihitung di sini."
            : undefined,
      };
    },
  },

  {
    id: "briefing",
    description:
      "Rekomendasi dan temuan yang perlu diperhatikan pada periode ini — peluang, perhatian, dan " +
      "risiko beserta perkiraan dampak rupiah per bulan. Dipakai untuk 'ada yang perlu saya " +
      "perhatikan / apa saran / apa masalahnya'.",
    slots: ["range", "stores", "categories", "membership", "limit"],
    async run(ctx) {
      const b = await briefing(ctx.filters, ctx.extent);
      if (!b.findings.length) {
        return { headline: b.headline, href: link("/actions", ctx) };
      }
      const limit = clamp(ctx.limit, 5, 5);
      return {
        headline: b.headline,
        table: {
          columns: ["Temuan", "Sifat", "Potensi / bulan"],
          rows: b.findings
            .slice(0, limit)
            .map((f) => [
              f.title,
              f.severity,
              f.impactPerMonth ? rupiahShort(f.impactPerMonth) : "—",
            ]),
        },
        href: link("/actions", ctx),
        note: b.caveats[0],
      };
    },
  },
];

export const SKILL_BY_ID = new Map(SKILLS.map((s) => [s.id, s]));
