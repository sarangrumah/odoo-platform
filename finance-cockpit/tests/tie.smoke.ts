// =============================================================================
// Smoke test: run all fourteen tie checks against the real prd_levis_begbal.
//
// This is the highest-value test in the project. The unit tests prove the
// classifier and the netting behave; this one proves the whole stack still
// agrees with the ledger, and it fails loudly the day it stops.
//
// Needs the database, so it lives outside `--test` and is run by hand or before
// a deploy:
//
//   docker run --rm --network odoo19-platform-net \
//     -v "$PWD:/app" -w /app --env-file ../.env \
//     -e FINANCE_DB_HOST=postgres node:22-alpine \
//     npx tsx tests/tie.smoke.ts [YYYY-MM-DD]
//
// Exits non-zero if any check that is supposed to reconcile does not.
// =============================================================================

import { createRequire } from "node:module";

// Next's App Router supplies React 19's `cache()`; the react in node_modules is
// 18.3 and has no such export, so queries/common.ts throws at import time under
// plain node. Identity is the correct shim: `cache` only dedupes within one
// request, and this script is one request.
const require_ = createRequire(import.meta.url);
const react = require_("react") as { cache?: <T>(fn: T) => T };
if (typeof react.cache !== "function") react.cache = (fn) => fn;

const money = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

async function main() {
  const { runTieChecks } = await import("../src/lib/queries/tie");
  const { defaultCompanyIds } = await import("../src/lib/queries/common");
  const { today, startOfMonth } = await import("../src/lib/finance-filters");
  const { pool } = await import("../src/lib/db");

  const asOf = process.argv[2] ?? today();
  const companies = await defaultCompanyIds();

  console.log(`as of ${asOf} · companies ${companies.join(", ")}\n`);

  const checks = await runTieChecks(
    { asOf, from: startOfMonth(asOf), companies },
    today(),
  );

  let failed = 0;
  for (const check of checks) {
    const mark = check.state === "ok" ? "OK  " : check.state === "info" ? "note" : "FAIL";
    if (check.state === "bad") failed += 1;
    console.log(
      `${mark}  ${String(check.id).padStart(2)}. ${check.title}\n` +
        `      ${check.leftLabel} ${money.format(check.left)}` +
        (check.rightLabel ? ` · ${check.rightLabel} ${money.format(check.right)}` : "") +
        ` · selisih ${money.format(check.difference)}`,
    );
    if (check.state === "bad") console.log(`      diharapkan: ${check.expectation}`);
  }

  console.log(
    `\n${checks.length - failed} of ${checks.length} reconcile or are explained; ${failed} failed.`,
  );

  await pool().end();
  if (failed) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
