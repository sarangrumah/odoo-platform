// =============================================================================
// The deterministic matcher — the "no model" half of the assistant.
//
// Weighted keyword scoring, not a chain of ifs: a finance question mentions
// several things at once ("berapa hutang GR/IR yang lewat 90 hari per akhir
// Juli") and the winner should be whichever skill the question is mostly ABOUT.
//
// The threshold is deliberately strict, and more so here than on the sales
// side. Answering the wrong question with a confident rupiah figure is bad on a
// sales dashboard and unacceptable on an accounting one — somebody may pay
// against it. Anything ambiguous scores itself out and returns null.
// =============================================================================

import { normalise } from "@/lib/agent/slots";

interface Rule {
  skill: string;
  /** [pattern, weight]. Weight 2 = this phrase alone names the skill. */
  patterns: [RegExp, number][];
}

const RULES: Rule[] = [
  {
    skill: "ap_summary",
    patterns: [
      [/\b(hutang|utang|payable|ap|tagihan|bill)\b/, 2],
      [/\b(berapa|total|jumlah|posisi|saldo)\b/, 1],
      [/\b(vendor|supplier|pemasok|rekanan)\b/, 1],
    ],
  },
  {
    skill: "ap_overdue",
    patterns: [
      [/\b(jatuh\s+tempo|overdue|tunggakan|telat|terlambat|lewat|menunggak)\b/, 3],
      [/\b(aging|umur|bucket)\b/, 2],
      [/\b(hutang|utang|payable|vendor|supplier)\b/, 1],
      [/\b\d{2,3}\s*hari\b/, 1],
    ],
  },
  {
    skill: "ap_upcoming",
    patterns: [
      [/\b(akan|segera|mendatang|ke\s+depan|minggu\s+depan|pekan\s+depan|besok)\b/, 2],
      [/\b(jatuh\s+tempo|bayar|pembayaran|cash\s*out|rencana)\b/, 2],
      [/\b(kapan|berapa)\b/, 1],
    ],
  },
  {
    skill: "ar_summary",
    patterns: [
      [/\b(piutang|receivable|ar)\b/, 3],
      [/\b(pelanggan|customer|tertagih)\b/, 1],
      [/\b(berapa|total|posisi|saldo)\b/, 1],
    ],
  },
  {
    skill: "open_items",
    patterns: [
      [/\b(open\s*item|outstanding|belum\s+(tuntas|selesai|lunas|direkonsiliasi)|menggantung)\b/, 3],
      [/\b(rekonsiliasi|reconcile|kliring|clearing|suspense|uang\s+muka|advance)\b/, 2],
      [/\b(akun|account)\b/, 1],
    ],
  },
  {
    skill: "grir",
    patterns: [
      [/\b(gr\s*\/?\s*ir|grir|goods\s+receipt|penerimaan\s+barang)\b/, 3],
      [/\b(netting|net|saling\s+hapus)\b/, 2],
    ],
  },
  {
    skill: "account_detail",
    patterns: [
      // Only ever wins when an account was actually resolved; see below.
      [/\b(akun|account|kode\s+akun)\b/, 1],
      [/\b(rincian|detail|isi|apa\s+saja|siapa)\b/, 1],
    ],
  },
  {
    skill: "oldest_items",
    patterns: [
      [/\b(tertua|terlama|paling\s+lama|paling\s+tua|mengendap|basi|lama)\b/, 3],
      [/\b(umur|usia|age|berapa\s+lama)\b/, 2],
      // "open item mana yang paling tua" scores 3 for open_items and 3 here, and
      // a tie is refused by design. The interrogative is what makes it an age
      // question rather than a balance question, so it breaks the tie.
      [/\b(mana|apa|akun\s+mana)\b[^.]*\b(tertua|terlama|paling\s+(lama|tua))\b/, 2],
    ],
  },
  {
    skill: "pos_clearing",
    patterns: [
      [/\b(clearing|kliring|settlement|settle|mdr|acquirer)\b/, 2],
      [/\b(pos|kasir|tender|edc|qris)\b/, 2],
      [/\b(kurang|short|selisih|nyangkut)\b/, 1],
    ],
  },
  {
    skill: "bank_unreconciled",
    patterns: [
      [/\b(rekening\s+koran|statement|mutasi\s+bank|bank\s+statement)\b/, 3],
      [/\b(belum\s+(cocok|direkonsiliasi|match)|unreconciled)\b/, 2],
      [/\b(bank)\b/, 1],
    ],
  },
  {
    skill: "close_readiness",
    patterns: [
      [/\b(tutup\s+buku|closing|close|kunci|lock\s*date|periode)\b/, 2],
      [/\b(draft|belum\s+diposting|siap|kesiapan|penghalang|blokir)\b/, 2],
      [/\b(bisa|boleh)\s+(di)?tutup\b/, 3],
    ],
  },
  {
    skill: "trial_balance",
    patterns: [
      [/\b(neraca\s+saldo|trial\s+balance|tb)\b/, 3],
      [/\b(debit|kredit|seimbang|balance)\b/, 1],
      [/\b(buku\s+besar|general\s+ledger|gl)\b/, 1],
    ],
  },
  {
    skill: "tie",
    patterns: [
      [/\b(tie|cocok|selisih|beda|akurat|benar|valid|percaya|dipercaya|bukti)\b/, 2],
      [/\b(dibanding|banding|vs|terhadap)\s*(odoo|report|laporan)\b/, 3],
      [/\b(kualitas\s+data|pembuktian)\b/, 3],
    ],
  },
  {
    skill: "briefing",
    patterns: [
      [/\b(rekomendasi|saran|advice|masukan|usul|insight|temuan)/, 2],
      [/\b(perlu|harus|patut)\s+(saya|kita|di)?\s*(perhatikan|waspadai|cermati|lihat|kerjakan)\b/, 2],
      [/\b(masalah|isu|problem|risiko|prioritas)/, 2],
      [/\b(apa\s+yang\s+(salah|kurang|bisa|mendesak))\b/, 2],
      [/\b(action|tindakan|langkah)\b/, 1],
    ],
  },
];

/**
 * Questions this database genuinely cannot answer.
 *
 * Every entry is a measured limit of prd_levis_begbal, not a guess, and saying
 * so outright beats letting the matcher half-match the sentence onto a skill
 * and return a confident number about something else.
 */
const UNANSWERABLE: [RegExp, string][] = [
  [
    /\b(anggaran|budget|rkap|target|forecast|proyeksi|prediksi|ramalan)\b/,
    "Anggaran dan target tidak tersimpan di database ini, jadi pencapaian terhadap anggaran tidak bisa dihitung dari sini.",
  ],
  [
    /\b(arus\s+kas|cash\s*flow|proyeksi\s+kas|likuiditas)\b/,
    "Laporan arus kas tidak dihitung di dasbor ini. Yang tersedia adalah jatuh tempo hutang empat pekan ke depan di halaman Hutang & Pembayaran — itu rencana pembayaran, bukan arus kas.",
  ],
  [
    /\b(margin|laba|profit|untung|keuntungan|hpp|cogs|harga\s+pokok|rugi)\b/,
    "Laba rugi bukan cakupan dasbor ini — yang dibaca hanya posisi terbuka, kliring dan kesiapan tutup buku. Untuk laba rugi, pakai report Profit & Loss di Odoo.",
  ],
  [
    /\b(pajak|ppn|pph|faktur\s+pajak|spt|bupot|coretax|efaktur|e-faktur)\b/,
    "Perhitungan pajak tidak ada di dasbor ini. Report SPT Masa PPN, PPh dan e-Faktur ada di modul akuntansi Odoo, dan angkanya tidak boleh diambil dari sini.",
  ],
  [
    /\b(stok|stock|persediaan|inventory|gudang|warehouse|mutasi\s+barang)\b/,
    "Data persediaan tidak dibaca di sini. Dasbor ini hanya menyentuh buku besar, rekening koran dan run kliring POS.",
  ],
  [
    /\b(gaji|salary|upah|payroll|absen|cuti|karyawan|pegawai|hr\b|sdm)\b/,
    "Data kepegawaian tidak ada di sini, dan tabel pengguna Odoo memang sengaja tidak diberikan ke peran baca dasbor ini.",
  ],
  [
    /\b(siapa\s+yang\s+(input|posting|buat|mengubah|edit)|user\s+mana|oleh\s+siapa)\b/,
    "Nama pengguna tidak bisa ditampilkan: tabel res_users sengaja tidak diberikan ke peran finance_ro, jadi yang tersedia hanya nomor id pembuat jurnal.",
  ],
  [
    /\b(penjualan|omzet|omset|sales|revenue|produk\s+terlaris|toko\s+mana)\b/,
    "Pertanyaan penjualan dijawab oleh Sales Cockpit di /cockpit, bukan di sini. Dasbor ini membaca sisi buku besarnya.",
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
 * `hasAccount` comes from slot extraction: "apa isi 2103109121" is an account
 * question only because an account resolved, and the same words without one are
 * not answerable at all.
 */
export function matchIntent(
  text: string,
  opts: { hasAccount: boolean; hasPartner: boolean },
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

  // A resolved account is strong evidence for the single-account view, and its
  // absence disqualifies that skill entirely — it has nothing to scope to.
  if (opts.hasAccount) {
    scores.set("account_detail", (scores.get("account_detail") ?? 0) + 3);
  } else {
    scores.delete("account_detail");
  }

  // A named vendor turns a general payables question into a specific one.
  if (opts.hasPartner && scores.has("ap_summary")) {
    scores.set("ap_summary", scores.get("ap_summary")! + 1);
  }

  const ranked = [...scores.entries()].sort((a, b) => b[1] - a[1]);
  if (!ranked.length) return null;

  const [skill, score] = ranked[0];
  const runnerUp = ranked[1]?.[1] ?? 0;
  if (score < MIN_SCORE || score - runnerUp < MIN_LEAD) return null;

  return { skill, score, runnerUp };
}
