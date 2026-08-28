// Intent matching. The interesting half of this file is the questions that must
// NOT match: a confident rupiah figure answering the wrong question is the one
// failure mode that would cost the dashboard its credibility.

import assert from "node:assert/strict";
import test from "node:test";

import { detectUnanswerable, matchIntent } from "../src/lib/agent/intent";

const skill = (q: string, hasStore = false, hasRange = false) =>
  matchIntent(q, { hasStore, hasRange })?.skill ?? null;

test("sales figures", () => {
  for (const q of [
    "penjualan bulan lalu berapa?",
    "berapa total omzet minggu ini",
    "berapa jumlah transaksi juli",
    "berapa ATV bulan ini",
    "ringkasan performa juli",
  ]) {
    assert.equal(skill(q), "kpi", q);
  }
});

test("a bare sales noun plus a period is a plain-numbers question", () => {
  // "penjualan juni" names no skill on its own; the recognised period is what
  // tips it, and only far enough that a more specific noun still wins.
  assert.equal(skill("penjualan juni", false, true), "kpi");
  assert.equal(skill("omzet minggu lalu", false, true), "kpi");
  assert.equal(skill("produk terlaris juli", false, true), "top_products");
  assert.equal(skill("tren juli", false, true), "trend");
  // A period with nothing else is still not a question we can place.
  assert.equal(skill("juni", false, true), null);
});

test("daily trend", () => {
  for (const q of [
    "tren harian minggu lalu",
    "grafik penjualan per hari",
    "hari apa yang paling ramai",
    "bagaimana pergerakan penjualan juli",
  ]) {
    assert.equal(skill(q), "trend", q);
  }
});

test("store ranking", () => {
  for (const q of [
    "toko mana yang paling tinggi?",
    "peringkat toko bulan lalu",
    "ranking outlet juli",
    "cabang mana yang terendah",
  ]) {
    assert.equal(skill(q), "store_ranking", q);
  }
});

test("silent stores", () => {
  for (const q of [
    "toko mana yang tidak ada transaksi",
    "outlet mana yang kosong bulan ini",
    "toko yang belum setor",
  ]) {
    assert.equal(skill(q), "silent_stores", q);
  }
});

test("products and categories", () => {
  assert.equal(skill("produk terlaris"), "top_products");
  assert.equal(skill("sku apa yang paling laku juli"), "top_products");
  assert.equal(skill("barang terlaris di bulan lalu"), "top_products");
  assert.equal(skill("kategori apa yang paling besar"), "category_mix");
  assert.equal(skill("komposisi kategori juli"), "category_mix");
  assert.equal(skill("kontribusi mens bottoms"), "category_mix");
});

test("associates", () => {
  assert.equal(skill("spg terbaik siapa"), "associates");
  assert.equal(skill("peringkat kasir bulan lalu"), "associates");
  assert.equal(skill("siapa pramuniaga tertinggi"), "associates");
});

test("trust panel", () => {
  assert.equal(skill("pos vs gl cocok tidak"), "recon");
  assert.equal(skill("berapa selisih rekonsiliasi"), "recon");
  assert.equal(skill("data sampai tanggal berapa"), "coverage");
  assert.equal(skill("datanya terakhir update kapan"), "coverage");
});

test("briefing", () => {
  assert.equal(skill("ada yang perlu saya perhatikan?"), "briefing");
  assert.equal(skill("apa rekomendasinya bulan ini"), "briefing");
  assert.equal(skill("ada masalah atau risiko?"), "briefing");
});

test("a store name turns a vague question into a store question", () => {
  // Without a resolved store name the same words are a fleet question, and
  // store_detail has nothing to scope to, so it is disqualified entirely.
  assert.equal(skill("bagaimana kondisi toko itu", true), "store_detail");
  assert.notEqual(skill("bagaimana kondisi toko itu", false), "store_detail");
});

test("out-of-scope questions return null rather than guessing", () => {
  for (const q of [
    "cuaca hari ini bagaimana",
    "halo",
    "siapa kamu",
    "terima kasih",
    "tolong buatkan laporan",
    "apa kabar",
  ]) {
    assert.equal(skill(q), null, q);
  }
});

test("questions the data cannot answer are refused by name", () => {
  const cases: [string, RegExp][] = [
    ["berapa margin bulan lalu", /harga pokok/i],
    ["laba bersih juli berapa", /harga pokok/i],
    ["berapa penjualan tunai vs kartu", /SUSPENSE/],
    ["breakdown metode pembayaran qris", /SUSPENSE/],
    ["sisa stok produk 501", /stok/i],
    ["berapa gaji spg terbaik", /kepegawaian/i],
    ["pencapaian terhadap target bulan ini", /[Tt]arget/],
  ];
  for (const [q, expected] of cases) {
    const msg = detectUnanswerable(q);
    assert.ok(msg, `expected a refusal for: ${q}`);
    assert.match(msg!, expected, q);
  }
});

test("ordinary questions are not refused", () => {
  for (const q of [
    "penjualan bulan lalu berapa",
    "toko mana yang paling tinggi",
    "produk terlaris minggu ini",
  ]) {
    assert.equal(detectUnanswerable(q), null, q);
  }
});
