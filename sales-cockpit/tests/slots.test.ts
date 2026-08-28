// Date-phrase parsing. Everything is anchored to the DATA's last day, so the
// expectations below are written against a fixed extent and stay true forever —
// which is the point: these must not drift with the wall clock.

import assert from "node:assert/strict";
import test from "node:test";

import { extractRange, extractSlots, normalise } from "../src/lib/agent/slots";
import type { Extent } from "../src/lib/filters";

// A Wednesday, chosen so week boundaries are visible in the expectations.
const EXTENT: Extent = { start: "2026-06-12", end: "2026-08-09" };

function range(text: string) {
  const r = extractRange(text, EXTENT);
  return r ? `${r.from}..${r.to}` : null;
}

test("normalise strips punctuation and case", () => {
  assert.equal(normalise("Penjualan BULAN lalu, berapa?"), "penjualan bulan lalu berapa");
});

test("relative phrases anchor to the last day with data, not to today", () => {
  assert.equal(range("penjualan hari ini"), "2026-08-09..2026-08-09");
  assert.equal(range("omzet kemarin"), "2026-08-08..2026-08-08");
});

test("week phrases run Monday to Sunday, clipped to the data", () => {
  // 2026-08-09 is a Sunday, so "minggu ini" is 3–9 August.
  assert.equal(range("tren minggu ini"), "2026-08-03..2026-08-09");
  assert.equal(range("tren minggu lalu"), "2026-07-27..2026-08-02");
});

test("month phrases", () => {
  assert.equal(range("penjualan bulan ini"), "2026-08-01..2026-08-09");
  assert.equal(range("penjualan bulan lalu"), "2026-07-01..2026-07-31");
  assert.equal(range("omzet juli"), "2026-07-01..2026-07-31");
  assert.equal(range("omzet juli 2026"), "2026-07-01..2026-07-31");
  assert.equal(range("omzet bulan agustus"), "2026-08-01..2026-08-09");
});

test("June is clipped to the first day with data", () => {
  // The dataset starts mid-June; asking for "juni" must not imply 1–11 June.
  assert.equal(range("penjualan juni"), "2026-06-12..2026-06-30");
});

test("explicit days and ISO dates", () => {
  assert.equal(range("penjualan 15 juli"), "2026-07-15..2026-07-15");
  assert.equal(range("penjualan 15 juli 2026"), "2026-07-15..2026-07-15");
  assert.equal(range("dari 2026-07-01 sampai 2026-07-31"), "2026-07-01..2026-07-31");
  assert.equal(range("tanggal 2026-07-15"), "2026-07-15..2026-07-15");
});

test("rolling windows", () => {
  assert.equal(range("7 hari terakhir"), "2026-08-03..2026-08-09");
  assert.equal(range("30 hari terakhir"), "2026-07-11..2026-08-09");
  assert.equal(range("3 bulan terakhir"), "2026-06-12..2026-08-09");
});

test("quarters", () => {
  assert.equal(range("q3"), "2026-07-01..2026-08-09");
  assert.equal(range("kuartal 3"), "2026-07-01..2026-08-09");
  // Q2 2026 ends 30 June; the data starts 12 June, so it clips on the left.
  assert.equal(range("triwulan 2"), "2026-06-12..2026-06-30");
});

test("whole dataset", () => {
  assert.equal(range("total semua waktu"), "2026-06-12..2026-08-09");
  assert.equal(range("sepanjang data"), "2026-06-12..2026-08-09");
});

test("a period entirely outside the data yields null, never a wrong number", () => {
  assert.equal(range("penjualan januari"), null);
  assert.equal(range("penjualan tahun lalu"), null);
  assert.equal(range("omzet 2027-01-05"), null);
});

test("no time phrase means inherit the filter bar", () => {
  assert.equal(range("produk terlaris"), null);
  assert.equal(range("toko mana yang paling tinggi"), null);
});

test("clipping is reported so the answer can say so", () => {
  assert.equal(extractRange("penjualan juni", EXTENT)?.clipped, true);
  assert.equal(extractRange("penjualan juli", EXTENT)?.clipped, false);
});

// --- entity matching ---------------------------------------------------------

// Real names from pos_config in prd_levis_begbal: the "OLS SES - " prefix is on
// every one of them, so it carries no information and must not be what matches.
const CATALOG = {
  stores: [
    { id: 1, name: "OLS SES - GRAND INDONESIA" },
    { id: 2, name: "OLS SES - PACIFIC PLACE MALL" },
    { id: 3, name: "OLS SES - CENTRAL PARK" },
  ],
  categories: ["MENS BOTTOMS", "WOMENS TOPS", "ACCESSORIES"],
  byStoreId: new Map<number, string>(),
};

function slots(text: string) {
  return extractSlots(text, EXTENT, CATALOG);
}

test("a store is recognised from the distinctive part of its name", () => {
  assert.deepEqual(slots("bagaimana grand indonesia").storeIds, [1]);
  assert.deepEqual(slots("penjualan Pacific Place bulan lalu").storeIds, [2]);
  assert.deepEqual(slots("omzet central park").storeIds, [3]);
});

test("a typo still resolves the store", () => {
  assert.deepEqual(slots("penjualan grand indonesa").storeIds, [1]);
});

test("a partial name does not resolve a store", () => {
  // "grand" alone is ambiguous the moment a second Grand-something opens.
  assert.deepEqual(slots("penjualan grand").storeIds, []);
  assert.deepEqual(slots("toko mana yang paling tinggi").storeIds, []);
});

test("categories resolve the same way", () => {
  assert.deepEqual(slots("penjualan mens bottoms juli").categories, ["MENS BOTTOMS"]);
  assert.deepEqual(slots("produk terlaris").categories, []);
});

test("membership", () => {
  assert.equal(slots("penjualan member bulan lalu").membership, "member");
  assert.equal(slots("transaksi non-member").membership, "guest");
  assert.equal(slots("penjualan bulan lalu").membership, null);
});

test("limit", () => {
  assert.equal(slots("top 5 produk terlaris").limit, 5);
  assert.equal(slots("10 toko teratas").limit, 10);
  assert.equal(slots("produk terlaris").limit, undefined);
});

test("out-of-range is distinguished from no-range", () => {
  assert.equal(slots("penjualan januari").outOfRange, true);
  assert.equal(slots("produk terlaris").outOfRange, false);
});
