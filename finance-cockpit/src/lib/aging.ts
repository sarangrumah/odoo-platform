// =============================================================================
// Aging buckets — the classifier, and nothing else.
//
// Deliberately free of database and React imports so it can be unit-tested
// directly. The SQL twin lives beside the query that uses it, in
// queries/ap.ts, and tests/buckets.test.ts pins the boundaries both must agree
// on.
//
// Ported from `custom.report.aged.receivable._classify_bucket`. The detail that
// gets re-implemented wrongly: `days <= 0` returns `not_due` BEFORE the bucket
// table is consulted, so `d_0_30` really means 1–30 days and a document due
// exactly on the cut-off is not overdue.
// =============================================================================

export const BUCKETS = [
  { code: "not_due", label: "Belum jatuh tempo", lower: null, upper: null },
  { code: "d_0_30", label: "1–30 hari", lower: 1, upper: 30 },
  { code: "d_31_60", label: "31–60 hari", lower: 31, upper: 60 },
  { code: "d_61_90", label: "61–90 hari", lower: 61, upper: 90 },
  { code: "d_91_180", label: "91–180 hari", lower: 91, upper: 180 },
  { code: "d_181_365", label: "181–365 hari", lower: 181, upper: 365 },
  { code: "d_over_365", label: "> 365 hari", lower: 366, upper: null },
] as const;

export type BucketCode = (typeof BUCKETS)[number]["code"];

/** The TypeScript twin of `_classify_bucket`, kept for the unit tests. */
export function classifyBucket(due: string | null, asOf: string): BucketCode {
  if (!due || due >= asOf) return "not_due";
  const days = Math.round(
    (new Date(`${asOf}T00:00:00Z`).getTime() - new Date(`${due}T00:00:00Z`).getTime()) / 86_400_000,
  );
  if (days <= 0) return "not_due";
  for (const b of BUCKETS) {
    if (b.lower === null) continue;
    if (b.upper === null) {
      if (days >= b.lower) return b.code;
    } else if (days >= b.lower && days <= b.upper) {
      return b.code;
    }
  }
  return "d_over_365";
}

