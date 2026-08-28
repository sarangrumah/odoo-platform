// =============================================================================
// The deterministic matcher — the "no LLM" half of the assistant.
//
// Weighted keyword scoring, not a chain of ifs: a question mentions several
// things at once ("produk terlaris di Grand Indonesia bulan lalu") and the
// winner should be whichever skill the question is mostly ABOUT, not whichever
// rule happened to be written first.
//
// The threshold is deliberately strict. Answering the wrong question with a
// confident rupiah figure is far worse than handing the sentence to the
// fallback, so anything ambiguous scores itself out and returns null.
// =============================================================================

import { normalise } from "@/lib/agent/slots";

interface Rule {
  skill: string;
  /** [pattern, weight]. Weight 2 = this phrase alone names the skill. */
  patterns: [RegExp, number][];
}

const RULES: Rule[] = [
  {
    skill: "kpi",
    patterns: [
      [/\b(omzet|omset|penjualan|sales|revenue|pendapatan|jualan)/, 1],
      [/\b(berapa|total|jumlah|angka|nilai)\b/, 1],
      [/\b(atv|upt|asp|rata[\s-]?rata\s+transaksi|nilai\s+transaksi)\b/, 2],
      [/\b(kpi|ringkasan|rangkuman|summary|performa|kinerja)/, 2],
      [/\b(transaksi|struk|bon)\b/, 1],
    ],
  },
  {
    skill: "trend",
    patterns: [
      [/\b(tren|trend|grafik|pergerakan|harian|per\s+hari|day)\b/, 2],
      [/\b(naik|turun|fluktuasi|pola)\b/, 1],
      [/\b(hari)\s+(apa|mana|terbaik|tertinggi|terendah|paling)\b/, 2],
      [/\b(puncak|peak|ramai|sepi)\b/, 1],
    ],
  },
  {
    skill: "store_ranking",
    patterns: [
      [/\b(toko|store|outlet|cabang|gerai)\b/, 1],
      [/\b(peringkat|ranking|urutan|rangking|leaderboard|papan)\b/, 2],
      [/\b(toko|store|outlet|cabang|gerai)\s+(mana|apa|terbaik|tertinggi|terendah|teratas)\b/, 2],
      [/\b(paling|ter)(tinggi|besar|bagus|banyak|rendah|kecil|jelek|buruk)\b/, 1],
      [/\b(bandingkan|perbandingan|banding)\b/, 1],
    ],
  },
  {
    skill: "store_detail",
    patterns: [
      // Only ever wins when a store name was actually resolved; see below.
      [/\b(bagaimana|gimana|kondisi|detail|profil|rincian|performa|kinerja)\b/, 1],
      [/\b(toko|store|outlet|cabang|gerai)\b/, 1],
    ],
  },
  {
    skill: "silent_stores",
    patterns: [
      [/\b(diam|sepi|kosong|nihil|tidak\s+ada\s+(transaksi|penjualan)|nol|zero)\b/, 3],
      [/\b(tidak|belum|tanpa|nggak|gak|ga)\s+(jualan|berjualan|setor|transaksi|laku)\b/, 3],
      [/\b(toko|store|outlet|cabang|gerai)\b/, 1],
      [/\b(silent|idle|mati)\b/, 2],
    ],
  },
  {
    skill: "top_products",
    patterns: [
      [/\b(produk|product|barang|item|sku|artikel|model)\b/, 2],
      [/\b(terlaris|laris|best\s?seller|terjual|paling\s+laku|laku)/, 2],
      [/\b(apa|mana|top|teratas)\b/, 1],
    ],
  },
  {
    skill: "category_mix",
    patterns: [
      [/\b(kategori|category|kategory|lini|divisi|departemen|segmen)/, 2],
      [/\b(mix|komposisi|porsi|kontribusi|share|sebaran|breakdown)\b/, 2],
      [/\b(mens|womens|kids|bottoms|tops|accessories)\b/, 2],
    ],
  },
  {
    skill: "associates",
    patterns: [
      [/\b(spg|kasir|associate|pramuniaga|staff|staf|karyawan|pegawai|sales\s?person)\b/, 2],
      [/\b(siapa|nama)\b/, 1],
      [/\b(terbaik|tertinggi|peringkat|ranking|leaderboard|top)\b/, 1],
    ],
  },
  {
    skill: "recon",
    patterns: [
      [/\b(rekonsiliasi|rekon|cocok|selisih|beda|match|reconcile)\b/, 2],
      [/\b(gl|general\s+ledger|jurnal|buku\s+besar|akuntansi|pembukuan)\b/, 2],
      [/\b(pos)\s+(vs|dengan|terhadap|banding)\b/, 2],
    ],
  },
  {
    skill: "coverage",
    patterns: [
      [/\b(cakupan|coverage|kualitas\s+data|sampai\s+(tanggal|kapan)|data\s+terakhir)\b/, 2],
      [/\b(sejak\s+kapan|mulai\s+kapan|update|terupdate|terbaru|refresh)\b/, 2],
      [/\b(datanya|dataset|database|data)\b/, 1],
      [/\b(lengkap|valid|dipercaya|akurat|bersih)\b/, 1],
    ],
  },
  {
    skill: "briefing",
    patterns: [
      [/\b(rekomendasi|saran|advice|masukan|usul|insight|temuan)/, 2],
      [/\b(perlu|harus|patut)\s+(saya|kita|di)?\s*(perhatikan|waspadai|cermati|lihat)\b/, 2],
      [/\b(masalah|isu|problem|risiko|peluang|opportunity|kesempatan)/, 2],
      [/\b(apa\s+yang\s+(salah|kurang|bisa))\b/, 2],
      [/\b(action|tindakan|langkah|prioritas)\b/, 1],
    ],
  },
];

/**
 * Questions this dataset genuinely cannot answer.
 *
 * Verified limits of prd_levis_begbal: `total_cost` is zero on every line (no
 * margin, no COGS), all POS payments sit on a single SUSPENSE method (no tender
 * split), prices are already net of discount, and `res_users` is not granted to
 * `cockpit_ro` at all. Saying so outright beats sending the question to the
 * fallback, which would spend a model call to arrive at the same "tidak tahu".
 */
const UNANSWERABLE: [RegExp, string][] = [
  [
    /\b(margin|laba|profit|untung|keuntungan|hpp|cogs|harga\s+pokok|gross\s+profit)\b/,
    "Margin dan laba tidak bisa dihitung dari data ini: harga pokok (total_cost) kosong di seluruh baris POS prd_levis_begbal. Yang tersedia hanya nilai penjualan.",
  ],
  [
    /\b(tender|metode\s+pembayaran|cara\s+bayar|tunai|cash|kartu|debit|kredit|qris|gopay|ovo|edc|mdr)\b/,
    "Rincian per metode pembayaran tidak tersedia: seluruh pembayaran POS di database ini masuk ke satu metode SUSPENSE, jadi tunai dan kartu tidak terpisah.",
  ],
  [
    /\b(stok|stock|persediaan|inventory|sisa\s+barang|gudang|warehouse)\b/,
    "Data stok tidak ada di cakupan dashboard ini — yang dibaca hanya transaksi POS, bukan persediaan.",
  ],
  [
    /\b(gaji|salary|upah|payroll|absen|cuti|hr\b|sdm)\b/,
    "Data kepegawaian tidak ada di sini. Nama staff hanya muncul sebagai penanda penjualan, tanpa informasi personalia apa pun.",
  ],
  [
    /\b(target|budget|anggaran|rkap|forecast|proyeksi|prediksi)\b/,
    "Target dan anggaran tidak tersimpan di database ini, jadi pencapaian terhadap target tidak bisa dihitung.",
  ],
];

export function detectUnanswerable(text: string): string | null {
  const t = normalise(text);
  for (const [re, message] of UNANSWERABLE) {
    if (re.test(t)) return message;
  }
  return null;
}

export interface Match {
  skill: string;
  score: number;
  /** The runner-up's score, for the audit log. */
  runnerUp: number;
}

/** Minimum score, and minimum lead over the runner-up, for a confident answer. */
const MIN_SCORE = 2;
const MIN_LEAD = 1;

/**
 * Pick a skill, or null when the sentence is not clearly about one of them.
 *
 * Both flags come from slot extraction. "bagaimana Grand Indonesia?" is a store
 * detail question only because a store name resolved, and the same words
 * without a name are a fleet question.
 */
export function matchIntent(
  text: string,
  opts: { hasStore: boolean; hasRange?: boolean },
): Match | null {
  const t = normalise(text);
  if (!t) return null;

  const scores = new Map<string, number>();
  for (const rule of RULES) {
    let score = 0;
    for (const [re, weight] of rule.patterns) {
      if (re.test(t)) score += weight;
    }
    if (score > 0) scores.set(rule.skill, score);
  }

  // A resolved store name is strong evidence for the single-store view, and its
  // absence disqualifies that skill entirely — it has nothing to scope to.
  if (opts.hasStore) {
    scores.set("store_detail", (scores.get("store_detail") ?? 0) + 2);
    // "toko mana yang tertinggi" while a store is selected is still a ranking
    // question, so ranking keeps its own score and simply competes.
  } else {
    scores.delete("store_detail");
  }

  // KPI is the one skill with no vocabulary of its own — "penjualan juni" is a
  // plain-numbers question and nothing in it names a skill. A recognised period
  // is the missing evidence, and it is weak enough (+1) that "produk terlaris
  // juli" still belongs to products.
  if (opts.hasRange && scores.has("kpi")) {
    scores.set("kpi", scores.get("kpi")! + 1);
  }

  const ranked = [...scores.entries()].sort((a, b) => b[1] - a[1]);
  if (!ranked.length) return null;

  const [skill, score] = ranked[0];
  const runnerUp = ranked[1]?.[1] ?? 0;
  if (score < MIN_SCORE || score - runnerUp < MIN_LEAD) return null;

  return { skill, score, runnerUp };
}
