// The netting port, tested against the properties that make it trustworthy.
//
// The invariant matters more than any single case: FIFO only moves rupiah
// between rows, so the signed sum must survive it exactly. If that holds, the
// headline figure on the Open Items page — computed WITHOUT netting — is
// guaranteed to agree with the netted detail, and check 8 on the tie page is
// asserting something real rather than a tautology.

import { test } from "node:test";
import assert from "node:assert/strict";

import { fifo, netOffsetting, focusPartner, type NettableRow } from "../src/lib/netting";
import { isZero, IDR_ROUNDING as R } from "../src/lib/money";

let nextId = 1;

function row(
  residual: number,
  opts: { partnerId?: number | null; date?: string; accountId?: number } = {},
): NettableRow {
  return {
    id: nextId++,
    accountId: opts.accountId ?? 778,
    partnerId: opts.partnerId === undefined ? null : opts.partnerId,
    currencyId: null,
    date: opts.date ?? "2026-08-01",
    residualAsOf: residual,
    outstanding: residual,
  };
}

const sum = (rows: NettableRow[], key: "residualAsOf" | "outstanding" = "outstanding") =>
  rows.reduce((s, r) => s + r[key], 0);

function survivorsOf(map: Map<number, NettableRow[]>): NettableRow[] {
  return Array.from(map.values()).flat();
}

test("fifo consumes the oldest debit against the oldest credit", () => {
  const debits = [
    row(100, { date: "2026-01-01" }),
    row(100, { date: "2026-02-01" }),
  ];
  const credits = [row(-150, { date: "2026-01-15" })];
  fifo(debits, credits, R);

  assert.equal(debits[0].outstanding, 0, "oldest debit fully consumed first");
  assert.equal(debits[1].outstanding, 50, "younger debit keeps the remainder");
  assert.equal(credits[0].outstanding, 0);
});

test("netting never changes the signed sum", () => {
  const rows = [
    row(500, { partnerId: 1 }),
    row(-300, { partnerId: 1 }),
    row(-150, { partnerId: null }),
    row(80, { partnerId: 2 }),
  ];
  const before = sum(rows, "residualAsOf");
  const after = sum(survivorsOf(netOffsetting(rows, R)));
  assert.ok(isZero(before - after, R), `${before} vs ${after}`);
});

test("the invariant holds for random inputs", () => {
  // A deterministic generator: a seeded LCG, so a failure is reproducible and
  // the test never flakes differently between runs.
  let seed = 20260828;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };

  for (let iteration = 0; iteration < 500; iteration += 1) {
    const rows: NettableRow[] = [];
    const count = 2 + Math.floor(rand() * 30);
    for (let i = 0; i < count; i += 1) {
      const amount = Math.round((rand() - 0.5) * 2_000_000) || 1;
      const partnerId = rand() < 0.4 ? null : 1 + Math.floor(rand() * 4);
      const day = 1 + Math.floor(rand() * 28);
      rows.push(
        row(amount, {
          partnerId,
          date: `2026-08-${String(day).padStart(2, "0")}`,
          accountId: rand() < 0.5 ? 778 : 780,
        }),
      );
    }
    const before = sum(rows, "residualAsOf");
    const after = sum(survivorsOf(netOffsetting(rows, R)));
    assert.ok(isZero(before - after, R), `iteration ${iteration}: ${before} vs ${after}`);
  }
});

test("the GR/IR shape nets away completely", () => {
  // What account 778 actually looks like: goods-receipt credits booked with no
  // partner, bill debits booked against the vendor. Pass 1 cannot touch them —
  // they are in different partner groups — so this is entirely pass 2's work.
  const credits = Array.from({ length: 20 }, (_, i) =>
    row(-1_000_000, { partnerId: null, date: `2026-08-${String(i + 1).padStart(2, "0")}` }),
  );
  const debits = Array.from({ length: 10 }, (_, i) =>
    row(2_000_000, { partnerId: 7, date: `2026-08-${String(i + 1).padStart(2, "0")}` }),
  );

  const survivors = survivorsOf(netOffsetting([...credits, ...debits], R));
  assert.equal(survivors.length, 0, "equal totals must cancel entirely");
});

test("a shortfall on one side survives at exactly its size", () => {
  const credits = Array.from({ length: 20 }, () => row(-1_000_000, { partnerId: null }));
  const debits = Array.from({ length: 9 }, () => row(2_000_000, { partnerId: 7 }));

  const survivors = survivorsOf(netOffsetting([...credits, ...debits], R));
  assert.equal(sum(survivors), -2_000_000, "the unmatched credit is what is left");
});

test("two rows that both name a partner are never netted against each other", () => {
  const rows = [row(500_000, { partnerId: 1 }), row(-500_000, { partnerId: 2 })];
  const survivors = survivorsOf(netOffsetting(rows, R));
  assert.equal(survivors.length, 2, "different named partners must stay apart");
});

test("netting never crosses accounts", () => {
  const rows = [row(500_000, { accountId: 778 }), row(-500_000, { accountId: 780 })];
  const survivors = survivorsOf(netOffsetting(rows, R));
  assert.equal(survivors.length, 2);
});

test("isZero uses the currency rounding, not a fixed epsilon", () => {
  // IDR rounding is 0.01, so the threshold is 0.005 — not 0.5, and not 1e-9.
  assert.equal(R, 0.01);
  assert.ok(isZero(0.004, R));
  assert.ok(!isZero(0.006, R));
  assert.ok(!isZero(0.5, R));
});

test("focusPartner narrows without re-netting", () => {
  const rows = [
    row(100, { partnerId: 1 }),
    row(200, { partnerId: 2 }),
    row(300, { partnerId: null }),
  ];
  assert.equal(focusPartner(rows, null).length, 3);
  assert.equal(focusPartner(rows, 2).length, 1);
  assert.equal(focusPartner(rows, "none").length, 1);
  assert.equal(focusPartner(rows, "none")[0].residualAsOf, 300);
});
