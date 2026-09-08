// =============================================================================
// The recommendation engine.
//
// Every finding on /actions is produced here: SQL for the evidence, plain
// TypeScript for the arithmetic, and a template for the sentence. There is no
// model call anywhere in this file and there must not be one — the narrative is
// deterministic, so the same data always yields the same wording, the same
// rupiah, and no per-pull inference cost.
//
// Two rules the whole file obeys:
//
//  1. Never assert a cause. The data has no cost, no traffic and no tender
//     split, so a finding states a GAP against a peer benchmark (fleet trend,
//     store median, member vs guest) and calls the action a test, not a cure.
//  2. Every rupiah of "potensi" is an arithmetic consequence of ASSUME below,
//     and the assumption travels with the number into the UI. A director who
//     disagrees with 30% carry-over can divide by three in their head; a bare
//     number they cannot audit gets the whole dashboard distrusted.
// =============================================================================

import { q, num } from "@/lib/db";
import {
  buildScope,
  CATEGORY_LABEL,
  daysInRange,
  previousPeriod,
  type Extent,
  type Filters,
} from "@/lib/filters";
import { count, decimal, percent, rupiahShort } from "@/lib/format";
import { marketContext, type MarketContext } from "@/lib/queries/market";
import { base, kpis, silentStores, type Kpis } from "@/lib/queries/sales";

// --- The knobs ---------------------------------------------------------------
//
// Deliberately conservative and deliberately in one place. Each is quoted
// verbatim in the finding it feeds, so nothing here can inflate a headline
// without also printing the reason it is inflated.

const ASSUME = {
  /** Member capture a store network can realistically reach. */
  memberTarget: 0.9,
  /** Share of the member/guest ATV gap treated as real uplift, not selection. */
  memberCarry: 0.3,
  /** A member is dormant after this many days without a purchase. */
  dormantDays: 45,
  /** Share of dormant repeat members a campaign brings back. */
  dormantWinBack: 0.1,
  /** Share of a bad promo's discount recoverable by tightening the mechanic. */
  promoClawback: 0.2,
  /** Share of a gap to the peer benchmark treated as closable. */
  gapClosure: 0.5,
  /** Share of a missing hero SKU's per-store average a store would capture. */
  heroCapture: 0.5,
  /** A store trailing the fleet by more than this is called out. */
  fleetLagPoints: 0.1,
  /** Findings worth less than this per month are noise; drop them. */
  materialPerMonth: 25_000_000,
  /** Rules that extrapolate a coverage gap need at least this many days. */
  minWindowDays: 14,
  /** A peer group smaller than this is not a benchmark, it is an anecdote. */
  minPeerGroup: 3,
  /** Below this share of its expected market share a store is under-indexed. */
  fairShareFloor: 0.8,
};

export type Severity = "peluang" | "perhatian" | "risiko";

export interface Evidence {
  label: string;
  value: string;
}

export interface Finding {
  id: string;
  title: string;
  severity: Severity;
  /** Who moves it. Named by function, because the cockpit has no org chart. */
  owner: string;
  /** Rupiah per 30 days, 0 when the finding is real but not quantifiable. */
  impactPerMonth: number;
  /** The paragraph a director reads. Built from templates, never generated. */
  narrative: string;
  /** The arithmetic behind impactPerMonth, in words. */
  assumption: string;
  actions: string[];
  evidence: Evidence[];
}

export interface MarketStatus {
  /** Which benchmark the ATV rule ended up using. */
  benchmark: "aglomerasi" | "jaringan";
  mapped: boolean;
  figuresComplete: boolean;
  /** "belanja" = markets weighted by Susenas spend; "populasi" = headcount only. */
  basis: "belanja" | "populasi";
  missingSpend: string[];
  missingFigures: string[];
  needsVerification: string[];
  /** One row per store: address as Odoo holds it, plus the area it maps to. */
  stores: {
    store: string;
    address: string | null;
    city: string | null;
    area: string | null;
    agglomeration: string | null;
  }[];
  /** Stores whose address is still empty in Odoo. */
  withoutAddress: number;
}

export interface Briefing {
  /** Two or three sentences framing the period before any finding. */
  headline: string;
  findings: Finding[];
  /** Questions this dataset cannot answer, so nobody asks them of a finding. */
  caveats: string[];
  /** State of the market-context tables, shown so an empty one is not a mystery. */
  market: MarketStatus;
  generatedFor: { from: string; to: string; days: number };
}

/** Scale a figure measured over the window to a 30-day month. */
function perMonth(value: number, days: number): number {
  return days > 0 ? (value / days) * 30 : 0;
}

/**
 * Promotion names arrive as pipe-joined lists when a basket carries several
 * programmes, and they run past 90 characters. Trim for the sentence; the full
 * string stays in the database for anyone who queries it.
 */
function shortPromo(name: string): string {
  return name.length <= 52 ? name : `${name.slice(0, 51).trimEnd()}…`;
}

/** "turun 15,1%" / "naik 3,4%" / "praktis datar" */
function movePhrase(current: number, previous: number): string {
  if (!previous) return "tanpa pembanding";
  const change = (current - previous) / Math.abs(previous);
  if (Math.abs(change) < 0.005) return "praktis datar";
  return `${change > 0 ? "naik" : "turun"} ${percent(Math.abs(change))}`;
}

// --- Rules -------------------------------------------------------------------
// Each returns one Finding, or null when the data does not support it. A rule
// that cannot clear its own materiality threshold stays silent rather than
// padding the page.

async function memberCapture(f: Filters, days: number): Promise<Finding | null> {
  // Pointless while the user is already filtered to one side of the split.
  if (f.membership) return null;

  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT
       COUNT(DISTINCT o.id) AS txn,
       COUNT(DISTINCT o.id) FILTER (WHERE COALESCE(o.ri_member_id, '') <> '') AS member_txn,
       COALESCE(SUM(l.price_subtotal_incl) FILTER (WHERE COALESCE(o.ri_member_id, '') <> ''), 0) AS member_gross,
       COALESCE(SUM(l.price_subtotal_incl) FILTER (WHERE COALESCE(o.ri_member_id, '') = ''), 0) AS guest_gross
     ${base(scope)}
     WHERE ${scope.where}`,
    scope.params,
  );

  const r = rows[0] ?? {};
  const txn = num(r.txn);
  const memberTxn = num(r.member_txn);
  const guestTxn = txn - memberTxn;
  if (!txn || !guestTxn) return null;

  const memberAtv = memberTxn ? num(r.member_gross) / memberTxn : 0;
  const guestAtv = guestTxn ? num(r.guest_gross) / guestTxn : 0;
  const share = memberTxn / txn;
  const atvGap = memberAtv - guestAtv;
  if (atvGap <= 0 || share >= ASSUME.memberTarget) return null;

  const convertible = txn * (ASSUME.memberTarget - share);
  const impact = perMonth(convertible * atvGap * ASSUME.memberCarry, days);
  if (impact < ASSUME.materialPerMonth) return null;

  return {
    id: "member-capture",
    title: "Naikkan capture member di kasir",
    severity: "peluang",
    owner: "Store Operations + CRM",
    impactPerMonth: impact,
    narrative:
      `${percent(share)} transaksi tercatat atas nama member (${count(memberTxn)} dari ${count(txn)}). ` +
      `Transaksi member rata-rata ${rupiahShort(memberAtv)}, sedangkan tanpa member ${rupiahShort(guestAtv)} — ` +
      `selisih ${rupiahShort(atvGap)} per transaksi. Menaikkan capture ke ${percent(ASSUME.memberTarget, 0)} ` +
      `menyentuh ${count(Math.round(convertible))} transaksi pada volume periode ini.`,
    assumption:
      `Hanya ${percent(ASSUME.memberCarry, 0)} dari selisih ATV dihitung sebagai kenaikan nyata; sisanya ` +
      `diasumsikan efek seleksi (pembeli besar memang lebih mau mendaftar). Angka disetahunkan ke 30 hari.`,
    actions: [
      "Jadikan penawaran member sebagai langkah wajib di layar kasir sebelum pembayaran, bukan pertanyaan opsional.",
      "Ukur capture member per kasir mingguan; tiga kasir terbawah dapat pendampingan, bukan teguran.",
      "Uji satu insentif pendaftaran di tiga toko selama dua minggu dan bandingkan dengan toko sejenis.",
    ],
    evidence: [
      { label: "Transaksi member", value: `${count(memberTxn)} (${percent(share)})` },
      { label: "ATV member", value: rupiahShort(memberAtv) },
      { label: "ATV non-member", value: rupiahShort(guestAtv) },
      { label: "Transaksi yang bisa dikonversi", value: count(Math.round(convertible)) },
    ],
  };
}

async function dormantMembers(f: Filters, extent: Extent): Promise<Finding | null> {
  // Recency needs the full purchase history, not the selected window — but it
  // is measured AS OF the window end so the page stays reproducible. The store
  // filter still applies: "dormant" while looking at one store has to mean
  // dormant at that store, not somewhere in the network.
  const storeJoin = f.stores.length
    ? `JOIN pos_session s ON s.id = o.session_id JOIN pos_config c ON c.id = s.config_id`
    : "";
  const storeWhere = f.stores.length ? `AND c.id = ANY($3::int[])` : "";
  const rows = await q<Record<string, string>>(
    `WITH m AS (
       SELECT o.ri_member_id AS mid,
              MAX(o.date_order)::date AS last_buy,
              COUNT(*) AS trx,
              SUM(o.amount_total) AS spend
       FROM pos_order o
       ${storeJoin}
       WHERE COALESCE(o.ri_member_id, '') <> ''
         AND o.date_order < ($1::date + interval '1 day')
         ${storeWhere}
       GROUP BY 1
     )
     SELECT COUNT(*) FILTER (WHERE trx >= 2 AND last_buy < $1::date - $2::int) AS dormant,
            COUNT(*) FILTER (WHERE trx >= 2) AS repeaters,
            COUNT(*) AS members,
            COALESCE(AVG(spend / NULLIF(trx, 0)) FILTER (WHERE trx >= 2), 0) AS repeat_atv
     FROM m`,
    f.stores.length ? [f.to, ASSUME.dormantDays, f.stores] : [f.to, ASSUME.dormantDays],
  );

  const r = rows[0] ?? {};
  const dormant = num(r.dormant);
  const repeaters = num(r.repeaters);
  const members = num(r.members);
  const repeatAtv = num(r.repeat_atv);
  if (!dormant || !repeatAtv) return null;

  // A win-back lands once, not every month; it is charged to a single month.
  const impact = dormant * ASSUME.dormantWinBack * repeatAtv;
  if (impact < ASSUME.materialPerMonth) return null;

  return {
    id: "dormant-members",
    title: "Aktifkan kembali member yang berhenti belanja",
    severity: "peluang",
    owner: "CRM",
    impactPerMonth: impact,
    narrative:
      `Dari ${count(members)} member, ${count(repeaters)} pernah belanja lebih dari sekali dan ` +
      `${count(dormant)} di antaranya tidak muncul lagi dalam ${count(ASSUME.dormantDays)} hari terakhir ` +
      `sampai ${f.to}. Belanja rata-rata kelompok repeat ${rupiahShort(repeatAtv)} per transaksi. ` +
      `Ini kelompok yang paling murah dihubungi karena identitasnya sudah ada di sistem.`,
    assumption:
      `Tingkat kembali ${percent(ASSUME.dormantWinBack, 0)} — konservatif untuk kampanye tanpa insentif besar — ` +
      `dikali belanja rata-rata repeat. Nilainya sekali jalan, bukan berulang tiap bulan. ` +
      `Rentang data baru ${count(daysInRange({ from: extent.start, to: f.to }))} hari, jadi "dormant" di sini berarti ` +
      `jeda dalam rentang itu, bukan hilang setahun.`,
    actions: [
      "Tarik daftar member dormant lengkap dengan toko terakhir, lalu bagi per toko untuk dihubungi manual.",
      "Kirim satu penawaran terbatas waktu; ukur redemption per toko, bukan total, supaya efeknya bisa dilacak.",
      "Bandingkan hasilnya dengan kelompok kontrol yang tidak dihubungi sebelum diperbesar.",
    ],
    evidence: [
      { label: "Member dormant (repeat)", value: count(dormant) },
      { label: "Member repeat", value: count(repeaters) },
      { label: "Total member", value: count(members) },
      { label: "ATV member repeat", value: rupiahShort(repeatAtv) },
    ],
  };
}

async function promoEfficiency(f: Filters, days: number): Promise<Finding | null> {
  const scope = buildScope(f);
  // Attribution is at the ORDER grain on purpose. A buy-one-get-one writes the
  // free item as a line whose net is zero and whose discount is the full price,
  // so grouping revenue by the discounted LINE reported BOGOF as "Rp 876 juta
  // of discount for Rp 0 of sales" — arithmetically true, commercially absurd.
  // What a promotion buys is the whole basket it appears in.
  const rows = await q<Record<string, string>>(
    `WITH scoped AS (
       SELECT o.id AS order_id,
              COALESCE(NULLIF(l.ri_discount_description, ''), '(tanpa nama program)') AS promo,
              COALESCE(l.ri_src_discount, 0) AS discount,
              l.price_subtotal_incl AS net
       ${base(scope)}
       WHERE ${scope.where}
     ),
     orders AS (SELECT order_id, SUM(net) AS net FROM scoped GROUP BY 1),
     tagged AS (SELECT DISTINCT promo, order_id FROM scoped WHERE discount <> 0),
     disc AS (SELECT promo, SUM(discount) AS discount FROM scoped WHERE discount <> 0 GROUP BY 1)
     SELECT d.promo, d.discount, COUNT(*) AS txn, COALESCE(SUM(o.net), 0) AS net
     FROM disc d
     JOIN tagged t USING (promo)
     JOIN orders o ON o.order_id = t.order_id
     WHERE d.discount > 0
     GROUP BY d.promo, d.discount
     ORDER BY d.discount DESC
     LIMIT 40`,
    scope.params,
  );
  if (rows.length < 2) return null;

  const promos = rows.map((r) => {
    const discount = num(r.discount);
    const net = num(r.net);
    return {
      promo: String(r.promo),
      txn: num(r.txn),
      discount,
      net,
      // Rupiah of basket sales carried by each rupiah of discount given.
      yield: discount ? net / discount : 0,
    };
  });

  const totalDiscount = promos.reduce((sum, p) => sum + p.discount, 0);
  const totalNet = promos.reduce((sum, p) => sum + p.net, 0);
  const blendedYield = totalDiscount ? totalNet / totalDiscount : 0;

  // Among the programmes below the blended yield, pick the one holding the most
  // money — not the single lowest ratio. The worst ratio here is a staff
  // discount at 1,0 whose whole budget is Rp 104 juta: real, and far too small
  // to be the headline while a Rp 876 juta mechanic sits underneath it.
  const worst = promos
    .filter((p) => p.yield < blendedYield)
    .sort((a, b) => b.discount - a.discount)[0];
  const best = [...promos].sort((a, b) => b.yield - a.yield)[0];
  if (!worst || !best || worst.promo === best.promo) return null;

  const impact = perMonth(worst.discount * ASSUME.promoClawback, days);
  if (impact < ASSUME.materialPerMonth) return null;

  return {
    id: "promo-efficiency",
    title: `Perketat program "${shortPromo(worst.promo)}"`,
    severity: "perhatian",
    owner: "Merchandising / Trade Marketing",
    impactPerMonth: impact,
    narrative:
      `Program "${shortPromo(worst.promo)}" memberi diskon ${rupiahShort(worst.discount)} dan muncul di ` +
      `${count(worst.txn)} transaksi senilai ${rupiahShort(worst.net)} — ${decimal(worst.yield)} rupiah ` +
      `penjualan per rupiah diskon, di bawah rata-rata seluruh program ${decimal(blendedYield)}. ` +
      `Pembandingnya ada di periode yang sama: "${shortPromo(best.promo)}" menghasilkan ` +
      `${decimal(best.yield)} rupiah per rupiah diskon dari ${rupiahShort(best.discount)} diskon.`,
    assumption:
      `Penjualan dihitung per transaksi yang memuat program, bukan per baris yang didiskon — mekanik ` +
      `beli-satu-gratis-satu menaruh nol rupiah di baris hadiahnya. Transaksi yang memakai dua program ` +
      `ikut dihitung di keduanya. Potensi = ${percent(ASSUME.promoClawback, 0)} dari diskon program ` +
      `terburuk yang bisa ditahan tanpa kehilangan transaksi. Tanpa harga pokok, yang dibandingkan ` +
      `adalah penjualan per rupiah diskon — bukan laba.`,
    actions: [
      `Ganti mekanik "${shortPromo(worst.promo)}" menjadi bersyarat (minimum belanja atau bundling), jalankan dua minggu, lalu bandingkan.`,
      `Perluas mekanik "${shortPromo(best.promo)}" ke lebih banyak toko sebelum menambah kedalaman diskon di mana pun.`,
      "Tetapkan ambang efisiensi minimum sebelum program baru disetujui, memakai angka periode ini sebagai dasar.",
    ],
    evidence: [
      { label: "Diskon program", value: rupiahShort(worst.discount) },
      { label: "Nilai transaksi yang memuatnya", value: rupiahShort(worst.net) },
      { label: "Efisiensi program", value: `${decimal(worst.yield)} : 1` },
      { label: "Efisiensi rata-rata", value: `${decimal(blendedYield)} : 1` },
    ],
  };
}

interface StoreMove {
  id: number;
  name: string;
  gross: number;
  txn: number;
  atv: number;
  prevGross: number;
}

async function storeMoves(f: Filters): Promise<StoreMove[]> {
  const prev = previousPeriod(f);
  const scope = buildScope(f);
  const prevScope = buildScope({ ...f, from: prev.from, to: prev.to });

  const [cur, before] = await Promise.all([
    q<Record<string, string>>(
      `SELECT c.id, c.name,
              COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
              COUNT(DISTINCT o.id) AS txn
       ${base(scope)}
       WHERE ${scope.where}
       GROUP BY c.id, c.name`,
      scope.params,
    ),
    q<Record<string, string>>(
      `SELECT c.id, COALESCE(SUM(l.price_subtotal_incl), 0) AS gross
       ${base(prevScope)}
       WHERE ${prevScope.where}
       GROUP BY c.id`,
      prevScope.params,
    ),
  ]);

  const prevById = new Map(before.map((r) => [num(r.id), num(r.gross)]));
  return cur.map((r) => {
    const gross = num(r.gross);
    const txn = num(r.txn);
    return {
      id: num(r.id),
      name: String(r.name),
      gross,
      txn,
      atv: txn ? gross / txn : 0,
      prevGross: prevById.get(num(r.id)) ?? 0,
    };
  });
}

/**
 * A store falling faster than the fleet.
 *
 * Absolute decline is the wrong trigger here: when a sale period drops out of
 * the comparison window every store falls at once, and a rule on raw percentage
 * would flag all twenty-two of them. What is actionable is the store that falls
 * further than its peers over the same days.
 */
function laggingStore(stores: StoreMove[], now: Kpis, before: Kpis, days: number): Finding | null {
  if (!before.gross || stores.length < 3) return null;
  const fleetChange = (now.gross - before.gross) / before.gross;

  const ranked = stores
    .filter((s) => s.prevGross > 0)
    .map((s) => ({ ...s, change: (s.gross - s.prevGross) / s.prevGross }))
    .filter((s) => s.change < fleetChange - ASSUME.fleetLagPoints)
    .map((s) => ({ ...s, shortfall: s.prevGross * (fleetChange - s.change) }))
    .sort((a, b) => b.shortfall - a.shortfall);

  const worst = ranked[0];
  if (!worst) return null;

  const impact = perMonth(worst.shortfall * ASSUME.gapClosure, days);
  if (impact < ASSUME.materialPerMonth) return null;

  const others = ranked.slice(1, 4).map((s) => s.name);
  return {
    id: "lagging-store",
    title: `${worst.name} tertinggal dari tren jaringan`,
    severity: "risiko",
    owner: "Area Manager",
    impactPerMonth: impact,
    narrative:
      `Seluruh jaringan ${movePhrase(now.gross, before.gross)} dibanding periode sebelumnya yang sama panjang. ` +
      `${worst.name} ${movePhrase(worst.gross, worst.prevGross)} — tertinggal ` +
      `${percent(Math.abs(fleetChange - worst.change))} dari tren jaringan, setara ${rupiahShort(worst.shortfall)} ` +
      `pada periode ini. ATV toko ini ${rupiahShort(worst.atv)} atas ${count(worst.txn)} transaksi.` +
      (others.length
        ? ` Pola yang sama, lebih kecil, terlihat di ${others.join(", ")}.`
        : ""),
    assumption:
      `Potensi = ${percent(ASSUME.gapClosure, 0)} dari selisih terhadap tren jaringan, yaitu separuh jarak ` +
      `dikejar. Perbandingan memakai rentang yang sama panjang persis sebelumnya, sehingga efek musiman ` +
      `program diskon masih bisa mempengaruhi kedua sisi.`,
    actions: [
      `Kunjungi ${worst.name} dan bandingkan jam operasional, jumlah staf, dan tanggal penerimaan barang dengan toko sejenis.`,
      "Cek apakah kategori yang turun di toko ini sama dengan yang turun di jaringan; kalau berbeda, penyebabnya lokal.",
      "Tetapkan target pemulihan mingguan yang eksplisit dan tinjau di forum yang sama tiap minggu.",
    ],
    evidence: [
      { label: "Tren toko", value: movePhrase(worst.gross, worst.prevGross) },
      { label: "Tren jaringan", value: movePhrase(now.gross, before.gross) },
      { label: "Selisih terhadap jaringan", value: rupiahShort(worst.shortfall) },
      { label: "ATV toko", value: rupiahShort(worst.atv) },
    ],
  };
}

/**
 * Stores below their PEER median ATV, sized as the gap to that median.
 *
 * The peer group is the agglomeration when the store-to-city mapping is loaded
 * and the group is big enough — comparing a Bandung store against Plaza Senayan
 * measures the catchment, not the store. Without the mapping it falls back to
 * the whole network, which is what this rule did before.
 */
function atvGapStores(stores: StoreMove[], days: number, market: MarketContext): Finding | null {
  const withTxn = stores.filter((s) => s.txn >= 50);
  if (withTxn.length < 5) return null;

  const median = (values: number[]): number => {
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  };

  const fleetMedian = median(withTxn.map((s) => s.atv));
  const groupOf = (s: StoreMove) => market.byStore.get(s.id)?.agglomeration ?? null;

  const peerMedians = new Map<string, number>();
  if (market.mapped) {
    const buckets = new Map<string, number[]>();
    for (const s of withTxn) {
      const g = groupOf(s);
      if (!g) continue;
      buckets.set(g, [...(buckets.get(g) ?? []), s.atv]);
    }
    for (const [g, values] of buckets) {
      if (values.length >= ASSUME.minPeerGroup) peerMedians.set(g, median(values));
    }
  }
  const usingPeers = peerMedians.size > 0;

  const laggards = withTxn
    .map((s) => {
      const g = groupOf(s);
      const benchmark = (g ? peerMedians.get(g) : undefined) ?? fleetMedian;
      return { ...s, benchmark, group: g, gap: (benchmark - s.atv) * s.txn };
    })
    .filter((s) => s.gap > 0)
    .sort((a, b) => b.gap - a.gap);
  if (!laggards.length) return null;

  const total = laggards.reduce((sum, s) => sum + s.gap, 0);
  const impact = perMonth(total * ASSUME.gapClosure, days);
  if (impact < ASSUME.materialPerMonth) return null;

  const named = laggards.slice(0, 3);
  return {
    id: "atv-gap",
    title: usingPeers
      ? "Angkat ATV toko di bawah median wilayahnya"
      : "Angkat ATV toko di bawah median jaringan",
    severity: "peluang",
    owner: "Store Operations",
    impactPerMonth: impact,
    narrative:
      (usingPeers
        ? `Pembandingnya sesama toko dalam satu aglomerasi, bukan seluruh jaringan, sehingga perbedaan ` +
          `daya beli antar kota tidak ikut menghukum toko. `
        : `Pembandingnya median seluruh jaringan (${rupiahShort(fleetMedian)}) karena pemetaan wilayah ` +
          `toko belum tersedia. `) +
      `${count(laggards.length)} toko berada di bawah median pembandingnya, dan jika semuanya menyentuh ` +
      `median itu pada volume transaksi periode ini selisihnya ${rupiahShort(total)}. Penyumbang terbesar: ` +
      named
        .map(
          (s) =>
            `${s.name} (${rupiahShort(s.atv)} vs ${rupiahShort(s.benchmark)}` +
            `${usingPeers && s.group ? ` di ${s.group}` : ""}, ${count(s.txn)} transaksi)`,
        )
        .join("; ") +
      `. Karena UPT dan ATV sama-sama ada di data, arah perbaikannya bisa dipilih: menambah item per ` +
      `transaksi atau menaikkan harga rata-rata per item.`,
    assumption:
      `Potensi = ${percent(ASSUME.gapClosure, 0)} dari jarak ke median pembanding, bukan seluruhnya — ` +
      `sebagian selisih ATV berasal dari lokasi dan bauran produk yang tidak bisa diubah oleh toko. ` +
      (usingPeers
        ? `Kelompok pembanding dengan kurang dari ${count(ASSUME.minPeerGroup)} toko dikembalikan ke ` +
          `median jaringan.`
        : `Isi tabel cockpit_store_area untuk mengganti pembanding ini menjadi per wilayah.`),
    actions: [
      "Bandingkan bauran kategori toko di bawah median dengan toko pembandingnya; fokus pada kategori bernilai tinggi yang porsinya kecil.",
      "Latih attachment (ikat pinggang, kaus, aksesori) di tiga toko terbawah dan ukur UPT mingguan.",
      "Pastikan ukuran dan model terlaris benar-benar ada di toko-toko ini sebelum menyalahkan eksekusi.",
    ],
    evidence: [
      { label: usingPeers ? "Pembanding" : "Median ATV jaringan", value: usingPeers ? "median aglomerasi" : rupiahShort(fleetMedian) },
      { label: "Toko di bawah pembanding", value: count(laggards.length) },
      { label: "Selisih ke pembanding (periode ini)", value: rupiahShort(total) },
      { label: "Terbesar", value: named[0]?.name ?? "—" },
    ],
  };
}

/**
 * Fair share: actual sales share against the share of market the store's
 * catchment represents.
 *
 * This is the one question internal data cannot answer at all — "which store
 * still has room to grow" — and the only rule here that needs the BPS figures.
 * It stays silent unless EVERY mapped area carries them, because a market total
 * missing three cities ranks the remaining stores against a benchmark that
 * excludes them.
 */
function fairShare(stores: StoreMove[], market: MarketContext, days: number): Finding | null {
  if (!market.mapped || !market.figuresComplete) return null;

  const scoped = stores
    .map((s) => ({ store: s, area: market.byStore.get(s.id) }))
    .filter((x): x is { store: StoreMove; area: NonNullable<typeof x.area> } => !!x.area?.marketValue);
  if (scoped.length < 5) return null;

  // Stores sharing a city split that city's market between them; two Levi's in
  // Kelapa Gading do not each face the whole of Jakarta Utara.
  const perArea = new Map<string, number>();
  for (const x of scoped) perArea.set(x.area.areaCode, (perArea.get(x.area.areaCode) ?? 0) + 1);

  const rows = scoped.map((x) => ({
    name: x.store.name,
    gross: x.store.gross,
    area: x.area.areaName,
    potential: (x.area.marketValue ?? 0) / (perArea.get(x.area.areaCode) ?? 1),
  }));

  const totalGross = rows.reduce((sum, r) => sum + r.gross, 0);
  const totalPotential = rows.reduce((sum, r) => sum + r.potential, 0);
  if (!totalGross || !totalPotential) return null;

  const indexed = rows
    .map((r) => {
      const expectedShare = r.potential / totalPotential;
      const actualShare = r.gross / totalGross;
      // Cap the modelled gap at the store's own current sales. Weighted by
      // residents alone, Kabupaten Tangerang carries 1,7 juta people aged 15-44
      // against a single store, and the raw arithmetic asked AEON BSD to be six
      // times its size — a regency is not a catchment. Capping says "this store
      // could plausibly double", which is a claim worth acting on.
      const raw = (expectedShare - actualShare) * totalGross;
      return {
        ...r,
        index: expectedShare ? actualShare / expectedShare : 0,
        shortfall: Math.min(raw, r.gross),
        cappedAt: raw > r.gross,
      };
    })
    .filter((r) => r.index < ASSUME.fairShareFloor && r.shortfall > 0)
    .sort((a, b) => b.shortfall - a.shortfall);
  if (!indexed.length) return null;

  const impact = perMonth(indexed[0].shortfall * ASSUME.gapClosure, days);
  if (impact < ASSUME.materialPerMonth) return null;

  const worst = indexed[0];
  const basisPhrase =
    market.basis === "belanja"
      ? "penduduk 15–44 tahun x belanja pakaian per kapita"
      : "jumlah penduduk 15–44 tahun";
  return {
    id: "fair-share",
    title: `${worst.name} belum mengambil porsi pasarnya`,
    severity: "peluang",
    owner: "Area Manager + Merchandising",
    impactPerMonth: impact,
    narrative:
      `Diukur dari besar pasar wilayahnya (${basisPhrase}, dibagi rata ` +
      `dengan toko lain di kota yang sama), ${worst.name} di ${worst.area} seharusnya menyumbang ` +
      `${percent(worst.potential / totalPotential)} penjualan jaringan tetapi baru menyumbang ` +
      `${percent(worst.gross / totalGross)} — indeks ${decimal(worst.index)}. Selisihnya ` +
      `${rupiahShort(worst.shortfall)} pada periode ini` +
      (worst.cappedAt
        ? `, dibatasi pada besar penjualan toko itu sendiri karena hitungan mentahnya menuntut toko ` +
          `ini berlipat jauh lebih besar daripada yang masuk akal untuk satu gerai. `
        : `. `) +
      (indexed.length > 1
        ? `Pola yang sama terlihat di ${indexed.slice(1, 3).map((r) => r.name).join(" dan ")}.`
        : ""),
    assumption:
      `Potensi = ${percent(ASSUME.gapClosure, 0)} dari selisih terhadap porsi pasar. Pasar dihitung dari ` +
      `angka BPS di tabel cockpit_area (${basisPhrase}) dan dibagi rata antar toko sekota, bukan dari ` +
      `katchment mal yang sebenarnya — sebuah mal menarik pembeli lintas kota, dan toko di Jakarta Pusat ` +
      `melayani jauh lebih banyak orang daripada jumlah penduduknya. ` +
      (market.basis === "populasi"
        ? `Daya beli belum ditimbang: satu penduduk Jakarta Selatan dihitung setara satu penduduk Bekasi. ` +
          `Isi expenditure_apparel_capita untuk memperbaikinya. `
        : "") +
      `Selisih dibatasi maksimum sebesar penjualan toko itu sendiri, sehingga temuan ini paling jauh ` +
      `hanya menyarankan "toko ini bisa berlipat dua", bukan berlipat enam. ` +
      `Dengan ${count(stores.length)} toko, angka ini adalah patokan prioritas, bukan bukti statistik.`,
    actions: [
      `Tinjau ukuran toko, jam operasional, dan jumlah staf ${worst.name} terhadap toko dengan indeks di atas 1.`,
      "Cek apakah bauran produk di toko ini mewakili kategori yang laku di kota tersebut, bukan salinan bauran Jakarta.",
      "Kalau indeks tetap rendah setelah dua kuartal, pertanyaannya menjadi soal lokasi di dalam mal, bukan soal eksekusi harian.",
    ],
    evidence: [
      { label: "Porsi pasar (potensi)", value: percent(worst.potential / totalPotential) },
      { label: "Porsi penjualan (aktual)", value: percent(worst.gross / totalGross) },
      { label: "Indeks fair-share", value: decimal(worst.index) },
      { label: "Selisih periode ini", value: rupiahShort(worst.shortfall) },
    ],
  };
}

async function categoryShift(f: Filters, days: number): Promise<Finding | null> {
  const prev = previousPeriod(f);
  const scope = buildScope(f);
  const prevScope = buildScope({ ...f, from: prev.from, to: prev.to });

  const [cur, before] = await Promise.all([
    q<Record<string, string>>(
      `SELECT ${CATEGORY_LABEL} AS cat,
              COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
              COALESCE(SUM(l.qty), 0) AS units
       ${base(scope, true)}
       WHERE ${scope.where}
       GROUP BY 1`,
      scope.params,
    ),
    q<Record<string, string>>(
      `SELECT ${CATEGORY_LABEL} AS cat,
              COALESCE(SUM(l.price_subtotal_incl), 0) AS gross
       ${base(prevScope, true)}
       WHERE ${prevScope.where}
       GROUP BY 1`,
      prevScope.params,
    ),
  ]);

  const prevByCat = new Map(before.map((r) => [String(r.cat), num(r.gross)]));
  const curTotal = cur.reduce((sum, r) => sum + num(r.gross), 0);
  const prevTotal = before.reduce((sum, r) => sum + num(r.gross), 0);
  if (!curTotal || !prevTotal) return null;

  const fleetChange = (curTotal - prevTotal) / prevTotal;
  const moves = cur
    .map((r) => {
      const gross = num(r.gross);
      const prevGross = prevByCat.get(String(r.cat)) ?? 0;
      return {
        cat: String(r.cat),
        gross,
        prevGross,
        change: prevGross ? (gross - prevGross) / prevGross : 0,
        shortfall: prevGross ? prevGross * (fleetChange - (gross - prevGross) / prevGross) : 0,
      };
    })
    .filter((m) => m.prevGross > 0);

  const worst = moves.filter((m) => m.shortfall > 0).sort((a, b) => b.shortfall - a.shortfall)[0];
  const bestMover = moves.sort((a, b) => a.shortfall - b.shortfall)[0];
  if (!worst) return null;

  const impact = perMonth(worst.shortfall * ASSUME.gapClosure, days);
  if (impact < ASSUME.materialPerMonth) return null;

  return {
    id: "category-shift",
    title: `Kategori ${worst.cat} kehilangan porsi`,
    severity: "perhatian",
    owner: "Merchandising",
    impactPerMonth: impact,
    narrative:
      `${worst.cat} ${movePhrase(worst.gross, worst.prevGross)} sementara total penjualan ` +
      `${movePhrase(curTotal, prevTotal)} — selisih ${rupiahShort(worst.shortfall)} dibanding kalau ` +
      `kategori ini bergerak seirama jaringan. Porsinya kini ${percent(worst.gross / curTotal)} dari penjualan. ` +
      (bestMover && bestMover.cat !== worst.cat
        ? `Di periode yang sama ${bestMover.cat} justru ${movePhrase(bestMover.gross, bestMover.prevGross)}, ` +
          `jadi pergeserannya antar kategori, bukan pelemahan menyeluruh.`
        : ""),
    assumption:
      `Potensi = ${percent(ASSUME.gapClosure, 0)} dari selisih terhadap tren jaringan. Tanpa data stok, ` +
      `tidak bisa dibedakan apakah penurunan berasal dari permintaan atau dari barang yang tidak tersedia — ` +
      `itu pertanyaan pertama yang harus dijawab manual.`,
    actions: [
      `Cek ketersediaan ukuran dan model inti ${worst.cat} di toko-toko utama sebelum mengambil kesimpulan permintaan.`,
      `Bandingkan porsi ${worst.cat} antar toko; kalau hanya turun di sebagian toko, masalahnya distribusi.`,
      "Tinjau ruang display dan posisi kategori ini di lantai toko terhadap kategori yang sedang naik.",
    ],
    evidence: [
      { label: "Penjualan kategori", value: rupiahShort(worst.gross) },
      { label: "Periode sebelumnya", value: rupiahShort(worst.prevGross) },
      { label: "Porsi terhadap total", value: percent(worst.gross / curTotal) },
      { label: "Selisih terhadap tren", value: rupiahShort(worst.shortfall) },
    ],
  };
}

/**
 * Best-selling SKUs that a store never sold in the window.
 *
 * With no stock table granted to cockpit_ro this cannot distinguish "never
 * shipped there" from "sold out" from "not offered" — so the finding is phrased
 * as a list to check, and the impact is deliberately halved.
 */
async function heroSkuGaps(f: Filters, days: number): Promise<Finding | null> {
  // Below a fortnight the list stops meaning anything: over five days most
  // stores legitimately miss most of the top thirty SKUs, and scaling that gap
  // to a month produced a headline four times larger than the same rule over
  // the full dataset.
  if (days < ASSUME.minWindowDays) return null;

  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `WITH scoped AS (
       SELECT l.product_id, c.id AS store_id, c.name AS store, l.price_subtotal_incl AS amt
       ${base(scope, true)}
       WHERE ${scope.where}
     ),
     hero AS (
       SELECT product_id, SUM(amt) AS gross, COUNT(DISTINCT store_id) AS stores
       FROM scoped GROUP BY 1 ORDER BY gross DESC LIMIT 30
     ),
     sold AS (SELECT DISTINCT product_id, store_id FROM scoped),
     st AS (SELECT DISTINCT store_id, store FROM scoped)
     SELECT st.store,
            COUNT(*) AS missing,
            COALESCE(SUM(hero.gross / NULLIF(hero.stores, 0)), 0) AS est_gap
     FROM st
     CROSS JOIN hero
     LEFT JOIN sold ON sold.store_id = st.store_id AND sold.product_id = hero.product_id
     WHERE sold.product_id IS NULL
     GROUP BY 1
     ORDER BY est_gap DESC
     LIMIT 5`,
    scope.params,
  );
  if (!rows.length) return null;

  const gaps = rows.map((r) => ({
    store: String(r.store),
    missing: num(r.missing),
    estGap: num(r.est_gap),
  }));
  const total = gaps.reduce((sum, g) => sum + g.estGap, 0);
  const impact = perMonth(total * ASSUME.heroCapture, days);
  if (impact < ASSUME.materialPerMonth) return null;

  const top = gaps[0];
  return {
    id: "hero-sku-gap",
    title: "Produk terlaris tidak terjual di sebagian toko",
    severity: "peluang",
    owner: "Merchandising + Supply",
    impactPerMonth: impact,
    narrative:
      `Dari 30 produk terlaris jaringan pada periode ini, ${top.store} tidak menjual ${count(top.missing)} ` +
      `di antaranya sama sekali. Lima toko teratas dengan pola yang sama menyisakan ` +
      `${rupiahShort(total)} penjualan setara rata-rata per toko. Data ini tidak memuat stok, jadi yang ` +
      `terlihat adalah "tidak pernah terjual" — bisa berarti tidak dikirim, habis, atau tidak dipajang.`,
    assumption:
      `Setiap SKU yang hilang dinilai sebesar rata-rata penjualannya per toko yang menjualnya, lalu diambil ` +
      `${percent(ASSUME.heroCapture, 0)} saja karena permintaan tidak otomatis pindah ke toko lain.`,
    actions: [
      `Cocokkan daftar SKU terlaris dengan stok fisik ${top.store} — ini pemeriksaan setengah hari, bukan proyek.`,
      "Kalau barangnya ada tapi tidak terjual, periksa penempatan display; kalau tidak ada, ini masalah alokasi.",
      "Jadikan 30 SKU terlaris sebagai daftar wajib-ada yang direview mingguan per toko.",
    ],
    evidence: gaps.slice(0, 4).map((g) => ({
      label: g.store,
      value: `${count(g.missing)} SKU · ${rupiahShort(g.estGap)}`,
    })),
  };
}

async function associateSpread(f: Filters, days: number): Promise<Finding | null> {
  if (f.associate) return null;

  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `WITH a AS (
       SELECT c.id AS store_id, c.name AS store, NULLIF(l.ri_staff_name, '') AS staff,
              COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
              COUNT(DISTINCT o.id) AS txn
       ${base(scope)}
       WHERE ${scope.where} AND NULLIF(l.ri_staff_name, '') IS NOT NULL
       GROUP BY 1, 2, 3
       HAVING COUNT(DISTINCT o.id) >= 20
     ),
     med AS (
       SELECT store_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY gross / txn) AS median_atv
       FROM a GROUP BY 1
     )
     SELECT a.store, a.staff, a.txn,
            a.gross / a.txn AS atv,
            med.median_atv,
            (med.median_atv - a.gross / a.txn) * a.txn AS gap
     FROM a JOIN med USING (store_id)
     WHERE a.gross / a.txn < med.median_atv
     ORDER BY gap DESC
     LIMIT 10`,
    scope.params,
  );
  if (rows.length < 3) return null;

  const laggards = rows.map((r) => ({
    store: String(r.store),
    staff: String(r.staff),
    txn: num(r.txn),
    atv: num(r.atv),
    median: num(r.median_atv),
    gap: num(r.gap),
  }));
  const total = laggards.reduce((sum, l) => sum + l.gap, 0);
  const impact = perMonth(total * ASSUME.gapClosure, days);
  if (impact < ASSUME.materialPerMonth) return null;

  const top = laggards[0];
  return {
    id: "associate-spread",
    title: "Sebaran ATV antar kasir di toko yang sama",
    severity: "peluang",
    owner: "Store Manager",
    impactPerMonth: impact,
    narrative:
      `Pembandingnya rekan satu toko, bukan jaringan, sehingga perbedaan lokasi dan trafik tidak ikut terhitung. ` +
      `${count(laggards.length)} kasir dengan minimal 20 transaksi berada di bawah median tokonya; ` +
      `contoh terbesar ${top.staff} di ${top.store} dengan ATV ${rupiahShort(top.atv)} berbanding median toko ` +
      `${rupiahShort(top.median)} atas ${count(top.txn)} transaksi. Total jarak ke median ${rupiahShort(total)} ` +
      `pada periode ini.`,
    assumption:
      `Potensi = ${percent(ASSUME.gapClosure, 0)} dari jarak ke median toko. Kasir dengan kurang dari 20 ` +
      `transaksi dikecualikan agar sampel kecil tidak muncul sebagai temuan.`,
    actions: [
      "Pasangkan kasir di bawah median dengan rekan di atas median pada shift yang sama selama dua minggu.",
      "Tinjau ulang apakah pembagian shift membuat sebagian kasir selalu kebagian jam sepi — itu memelintir angkanya.",
      "Bahas ATV dan UPT per kasir dalam briefing mingguan toko, bukan dalam laporan bulanan area.",
    ],
    evidence: laggards.slice(0, 4).map((l) => ({
      label: `${l.staff} · ${l.store}`,
      value: `${rupiahShort(l.atv)} vs median ${rupiahShort(l.median)}`,
    })),
  };
}

function silentStoreFinding(silent: { id: number; name: string }[]): Finding | null {
  if (!silent.length) return null;
  return {
    id: "silent-stores",
    title: `${count(silent.length)} titik penjualan tanpa transaksi`,
    severity: "perhatian",
    owner: "Store Operations + IT",
    impactPerMonth: 0,
    narrative:
      `${silent.map((s) => s.name).join(", ")} tidak memiliki satu pun transaksi pada rentang ini. ` +
      `Sebelum diperlakukan sebagai masalah penjualan, pastikan dulu titik ini memang beroperasi: ` +
      `konfigurasi kasir yang tidak terpakai dan toko yang benar-benar tutup terlihat sama persis di data.`,
    assumption:
      "Tidak dinilai dalam rupiah — nol transaksi bisa berarti tutup, belum dibuka, atau feed yang tidak masuk.",
    actions: [
      "Konfirmasi status setiap titik ke Area Manager: beroperasi, tutup, atau konfigurasi lama.",
      "Kalau beroperasi tapi tidak ada data, periksa feed retail-import untuk toko tersebut hari itu.",
      "Arsipkan konfigurasi kasir yang tidak dipakai supaya tidak ikut memperberat pembagi di laporan.",
    ],
    evidence: silent.slice(0, 5).map((s) => ({ label: s.name, value: "0 transaksi" })),
  };
}

// --- Assembly ----------------------------------------------------------------

function headlineFor(now: Kpis, before: Kpis, days: number, topFinding?: Finding): string {
  const parts: string[] = [];
  // The window can reach back past the first day of data, in which case there
  // is nothing to compare against and saying "turun 0%" would be a lie.
  const comparable = before.gross > 0;
  parts.push(
    `Rentang ${count(days)} hari yang dipilih membukukan penjualan bruto ${rupiahShort(now.gross)} dari ` +
      `${count(now.transactions)} transaksi` +
      (comparable
        ? `, ${movePhrase(now.gross, before.gross)} dibanding rentang sama panjang sebelumnya.`
        : `. Rentang sebelum ini berada di luar data yang termuat, jadi tidak ada pembanding periode.`),
  );
  parts.push(
    `ATV ${rupiahShort(now.atv)}${comparable ? ` (${movePhrase(now.atv, before.atv)})` : ""}, ` +
      `UPT ${decimal(now.upt)}, dan ${percent(now.discountShare)} transaksi memakai diskon` +
      (comparable ? ` (sebelumnya ${percent(before.discountShare)}).` : "."),
  );
  if (topFinding && topFinding.impactPerMonth > 0) {
    parts.push(
      `Prioritas terbesar periode ini: ${topFinding.title}, dengan potensi ` +
        `${rupiahShort(topFinding.impactPerMonth)} per bulan menurut asumsi yang tercantum di kartunya.`,
    );
  }
  return parts.join(" ");
}

/**
 * Everything /actions renders, in one round trip's worth of parallel queries.
 *
 * Rules that need the same store aggregate share it rather than each running
 * their own; the whole page is nine queries and lands well inside the 30s
 * statement timeout on cockpit_ro.
 */
export async function briefing(f: Filters, extent: Extent): Promise<Briefing> {
  const days = daysInRange(f);
  const prev = previousPeriod(f);
  const prevFilters: Filters = { ...f, from: prev.from, to: prev.to };

  const [now, before, stores, silent, market, member, dormant, promo, category, hero, associate] =
    await Promise.all([
      kpis(f),
      kpis(prevFilters),
      storeMoves(f),
      silentStores(f),
      marketContext(),
      memberCapture(f, days),
      dormantMembers(f, extent),
      promoEfficiency(f, days),
      categoryShift(f, days),
      heroSkuGaps(f, days),
      associateSpread(f, days),
    ]);

  const findings = [
    member,
    dormant,
    promo,
    laggingStore(stores, now, before, days),
    atvGapStores(stores, days, market),
    fairShare(stores, market, days),
    category,
    hero,
    associate,
    silentStoreFinding(silent),
  ]
    .filter((x): x is Finding => x !== null)
    // Quantified findings first, biggest rupiah at the top; the unquantifiable
    // ones keep their place at the bottom rather than being dropped.
    .sort((a, b) => b.impactPerMonth - a.impactPerMonth);

  return {
    headline: headlineFor(now, before, days, findings[0]),
    findings,
    caveats: [
      "Tidak ada harga pokok di data POS ini, sehingga semua angka bicara omzet dan diskon — bukan laba.",
      "Tidak ada data pengunjung, jadi tidak ada rekomendasi soal tingkat konversi.",
      "Seluruh pembayaran masuk sebagai satu metode (SUSPENSE); pemisahan tunai dan kartu ada di rekonsiliasi bank.",
      "Stempel waktu transaksi berasal dari proses impor, sehingga analisa jam sibuk tidak dapat dipercaya.",
      "Stok tidak termasuk dalam akses dashboard ini; temuan ketersediaan barang berhenti pada 'tidak terjual'.",
    ],
    market: {
      benchmark: market.mapped ? "aglomerasi" : "jaringan",
      mapped: market.mapped,
      figuresComplete: market.figuresComplete,
      basis: market.basis,
      missingSpend: market.missingSpend,
      missingFigures: market.missingFigures,
      needsVerification: market.needsVerification,
      stores: market.addresses.map((a) => {
        const area = market.byStore.get(a.configId);
        const line = [a.street, a.street2].filter(Boolean).join(", ");
        return {
          store: a.store,
          address: line || null,
          city: [a.city, a.zip].filter(Boolean).join(" ") || null,
          area: area?.areaName ?? null,
          agglomeration: area?.agglomeration ?? null,
        };
      }),
      withoutAddress: market.addresses.filter((a) => !a.street && !a.city).length,
    },
    generatedFor: { from: f.from, to: f.to, days },
  };
}
