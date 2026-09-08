// The matcher, and — more importantly — what it must NOT match.
//
// On an accounting dashboard a confident wrong answer is worse than no answer,
// because somebody may pay against it. Most of these cases assert a refusal or
// a null, not a match.

import { test } from "node:test";
import assert from "node:assert/strict";

import { detectUnanswerable, matchIntent } from "../src/lib/agent/intent";

const noEntities = { hasAccount: false, hasPartner: false };

function skillOf(q: string, opts = noEntities): string | null {
  return matchIntent(q, opts)?.skill ?? null;
}

test("plain finance questions reach the right skill", () => {
  const cases: [string, string][] = [
    ["berapa hutang yang lewat jatuh tempo", "ap_overdue"],
    ["posisi hutang ke vendor berapa", "ap_summary"],
    ["apa yang jatuh tempo pekan depan", "ap_upcoming"],
    ["berapa piutang terbuka", "ar_summary"],
    ["posisi GR/IR berapa", "grir"],
    ["open item mana yang paling tua", "oldest_items"],
    ["berapa baris rekening koran yang belum cocok", "bank_unreconciled"],
    ["apakah buku bisa ditutup", "close_readiness"],
    ["neraca saldo seimbang tidak", "trial_balance"],
    ["apa yang perlu saya kerjakan", "briefing"],
  ];
  for (const [q, expected] of cases) {
    assert.equal(skillOf(q), expected, q);
  }
});

test("the account skill needs an actual account", () => {
  // Same words, different outcome: without a resolved account there is nothing
  // to scope to, so the skill is removed from the running rather than guessing.
  assert.equal(skillOf("apa isi akunnya"), null);
  assert.equal(
    skillOf("apa isi akunnya", { hasAccount: true, hasPartner: false }),
    "account_detail",
  );
});

test("questions this database cannot answer are refused, not matched", () => {
  const refusals = [
    "berapa margin bulan lalu",
    "berapa PPN masukan bulan ini",
    "berapa penjualan bulan lalu",
    "siapa yang input jurnal ini",
    "berapa stok kaos di gudang",
    "berapa anggaran tahun ini",
    "bagaimana proyeksi arus kas",
    "berapa gaji karyawan bulan ini",
  ];
  for (const q of refusals) {
    assert.ok(detectUnanswerable(q), `should refuse: ${q}`);
  }
});

test("answerable questions are not refused", () => {
  const fine = [
    "berapa hutang yang lewat jatuh tempo",
    "open item mana yang paling tua",
    "apakah buku bisa ditutup",
    "posisi GR/IR berapa",
  ];
  for (const q of fine) {
    assert.equal(detectUnanswerable(q), null, `should not refuse: ${q}`);
  }
});

test("an ambiguous sentence scores itself out", () => {
  // No lead over the runner-up means no answer. That is the design: a tie is
  // exactly the case where a confident number would be a coin flip.
  assert.equal(skillOf("halo apa kabar"), null);
  assert.equal(skillOf("tolong"), null);
  assert.equal(skillOf(""), null);
});

test("a sales question is sent to the sales cockpit, not answered here", () => {
  const message = detectUnanswerable("berapa penjualan bulan lalu");
  assert.ok(message);
  assert.match(message!, /cockpit/i);
});
