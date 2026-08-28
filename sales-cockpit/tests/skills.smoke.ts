// =============================================================================
// Smoke test: run every catalogued skill against the real prd_levis_begbal.
//
// Not a unit test — it needs the database, so it lives outside `--test` and is
// run by hand (or in the container) rather than on every save:
//
//   docker run --rm --network odoo19-platform-net \
//     -v "$PWD:/app" -w /app --env-file ../.env \
//     -e COCKPIT_DB_HOST=postgres node:22-alpine \
//     npx tsx tests/skills.smoke.ts
//
// It asserts nothing about the figures — those belong to the dashboard, which
// is the point of the comparison in the manual checklist — only that every
// skill runs, returns a non-empty headline, and stays inside its row budget.
// =============================================================================

import { createRequire } from "node:module";

// Next's App Router supplies React 19's `cache()`; the react in node_modules is
// 18.3 and has no such export, so queries/sales.ts throws at import time under
// plain node. Identity is the correct shim: `cache` only dedupes within one
// request, and this script is one request.
const require_ = createRequire(import.meta.url);
const react = require_("react") as { cache?: <T>(fn: T) => T };
if (typeof react.cache !== "function") react.cache = (fn) => fn;

async function main() {
  const { SKILLS } = await import("../src/lib/agent/skills");
  const { dataExtent } = await import("../src/lib/queries/sales");
  const { pool } = await import("../src/lib/db");

  const extent = await dataExtent();
  console.log(`extent: ${extent.start} .. ${extent.end}\n`);

  const filters = {
    from: extent.start,
    to: extent.end,
    stores: [] as number[],
    categories: [] as string[],
    membership: null,
    associate: null,
  };

  let failed = 0;
  for (const skill of SKILLS) {
    const started = Date.now();
    try {
      const result = await skill.run({ filters, extent });
      const took = Date.now() - started;

      if (!result.headline?.trim()) throw new Error("empty headline");
      const rows = result.table?.rows.length ?? 0;
      if (rows > 10) throw new Error(`${rows} rows, budget is 10`);

      console.log(`✓ ${skill.id.padEnd(15)} ${String(took).padStart(5)}ms  ${result.headline}`);
      if (result.note) console.log(`  note: ${result.note}`);
    } catch (err) {
      failed += 1;
      console.log(`✗ ${skill.id.padEnd(15)} ${(err as Error).message}`);
    }
  }

  // store_detail needs a store in scope; exercise it against the top store.
  const { storeRanking } = await import("../src/lib/queries/sales");
  const top = (await storeRanking(filters))[0];
  if (top) {
    const detail = await import("../src/lib/agent/skills").then((m) =>
      m.SKILL_BY_ID.get("store_detail")!.run({
        filters: { ...filters, stores: [top.id] },
        extent,
      }),
    );
    console.log(`\n✓ store_detail (scoped)  ${detail.headline}`);
  }

  await pool().end();
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
