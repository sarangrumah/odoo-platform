// Cut-off phrases. Anchored to a fixed "today" so the suite cannot drift with
// the wall clock — the same reason the sales cockpit pins its extent.

import { test } from "node:test";
import assert from "node:assert/strict";

import { extractAsOf, normalise } from "../src/lib/agent/slots";

const TODAY = "2026-08-28";

function asOf(q: string): string | null {
  return extractAsOf(q, TODAY)?.asOf ?? null;
}

test("explicit dates win over everything else", () => {
  assert.equal(asOf("berapa hutang per 2026-07-31"), "2026-07-31");
  assert.equal(asOf("posisi per 15 Juli 2026"), "2026-07-15");
  assert.equal(asOf("posisi per 3 Januari"), "2026-01-03");
});

test("month-end phrases resolve to the last day of that month", () => {
  assert.equal(asOf("berapa hutang per akhir Juli"), "2026-07-31");
  assert.equal(asOf("saldo akhir Februari 2026"), "2026-02-28");
  assert.equal(asOf("posisi sampai Juni 2026"), "2026-06-30");
});

test("relative months are anchored to the supplied today", () => {
  assert.equal(asOf("posisi akhir bulan lalu"), "2026-07-31");
  assert.equal(asOf("hutang bulan lalu"), "2026-07-31");
  assert.equal(asOf("posisi akhir bulan ini"), "2026-08-31");
  assert.equal(asOf("saldo akhir tahun lalu"), "2025-12-31");
});

test("a bare month name means the end of that month", () => {
  // Finance asks about positions, not periods: "hutang Juli" is the balance at
  // the end of July, not the movement during it.
  assert.equal(asOf("berapa hutang Juli"), "2026-07-31");
  assert.equal(asOf("open item Desember 2025"), "2025-12-31");
});

test("today and yesterday", () => {
  assert.equal(asOf("berapa hutang hari ini"), TODAY);
  assert.equal(asOf("posisi sekarang"), TODAY);
  assert.equal(asOf("saldo kemarin"), "2026-08-27");
});

test("a sentence with no period returns null, so the caller keeps its own", () => {
  assert.equal(asOf("berapa hutang yang lewat jatuh tempo"), null);
  assert.equal(asOf("open item mana yang paling tua"), null);
});

test("akhir bulan lalu is not swallowed by the bare bulan lalu rule", () => {
  // Both phrases resolve to the same date here, but through different branches;
  // the label is what proves the more specific rule ran first.
  assert.equal(extractAsOf("akhir bulan lalu", TODAY)?.label, "akhir bulan lalu");
});

test("normalise strips punctuation without eating letters or digits", () => {
  assert.equal(normalise("Berapa hutang, per 31 Juli?"), "berapa hutang per 31 juli");
  assert.equal(normalise("  GR/IR   2103109121 "), "gr ir 2103109121");
});
