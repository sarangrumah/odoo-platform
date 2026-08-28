// Boundary cases for the aging classifier.
//
// Every one of these is a case the SQL and the TypeScript twin must agree on,
// and most of them are the ones a re-implementation gets wrong: the report
// returns `not_due` for `days <= 0` BEFORE consulting the bucket table, which
// is why `d_0_30` really means 1–30 days and a document due exactly on the
// cut-off is not overdue.

import { test } from "node:test";
import assert from "node:assert/strict";

import { classifyBucket } from "../src/lib/aging";

const ASOF = "2026-08-28";

const CASES: [string | null, string][] = [
  [null, "not_due"],              // no due date at all
  ["2026-09-15", "not_due"],      // due in the future
  ["2026-08-28", "not_due"],      // due exactly on the cut-off
  ["2026-08-27", "d_0_30"],       // one day late
  ["2026-07-29", "d_0_30"],       // thirty days late — still the first bucket
  ["2026-07-28", "d_31_60"],      // thirty-one days late
  ["2026-06-29", "d_31_60"],      // sixty
  ["2026-06-28", "d_61_90"],      // sixty-one
  ["2026-05-30", "d_61_90"],      // ninety
  ["2026-05-29", "d_91_180"],     // ninety-one
  ["2026-03-01", "d_91_180"],     // 180 days back — the last day of the bucket
  ["2026-02-28", "d_181_365"],    // 181 days back; Feb 28 to Aug 28 is 181, not 180
  ["2025-08-28", "d_181_365"],    // exactly one year
  ["2025-08-27", "d_over_365"],   // 366 days
  ["2020-01-01", "d_over_365"],
];

test("classifyBucket matches _classify_bucket at every boundary", () => {
  for (const [due, expected] of CASES) {
    assert.equal(classifyBucket(due, ASOF), expected, `due=${due}`);
  }
});

test("a due date on the cut-off is never overdue", () => {
  assert.equal(classifyBucket(ASOF, ASOF), "not_due");
});

test("the first overdue bucket spans exactly thirty days", () => {
  const days = (n: number) =>
    new Date(Date.parse(`${ASOF}T00:00:00Z`) - n * 86_400_000).toISOString().slice(0, 10);
  for (let n = 1; n <= 30; n += 1) {
    assert.equal(classifyBucket(days(n), ASOF), "d_0_30", `${n} days late`);
  }
  assert.equal(classifyBucket(days(31), ASOF), "d_31_60");
});
