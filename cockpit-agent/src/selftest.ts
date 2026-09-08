// Exercises everything in the sidecar except the model call: the HMAC handshake
// with the cockpit, the catalogue fetch that builds the tool list, and one real
// skill invocation. Run it after any change to the signing scheme or the
// catalogue contract.
//
//   docker run --rm --network odoo19-platform-net -v "$PWD:/app" -w /app \
//     --env-file ../.env -e COCKPIT_URL=http://cockpit-dev:8080/cockpit \
//     node:22-alpine npx tsx src/selftest.ts

import { describeSkills, runSkill } from "./cockpit.js";

const { skills } = await describeSkills();
console.log(`catalogue: ${skills.length} skills`);
for (const s of skills) {
  console.log(`  ${s.id.padEnd(15)} slots=[${s.slots.join(",")}]`);
}

const result = await runSkill("store_ranking", { from: "2026-07-01", to: "2026-07-31" }, 3);
console.log(`\nstore_ranking -> ${result.headline}`);
console.log(`rows: ${result.table?.rows.length ?? 0}, href: ${result.href}`);

// The endpoint must refuse anything that is not a catalogued skill name.
try {
  await runSkill("'; DROP TABLE pos_order; --", {});
  console.log("\nFAIL: an unknown skill name was accepted");
  process.exit(1);
} catch {
  console.log("\nunknown skill name rejected");
}
