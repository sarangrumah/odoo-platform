// Locate Playwright without a node_modules in the repo.
//
// There is no `npm install` here; Playwright lives only in the npx cache, whose
// directory names are content hashes and get garbage-collected. A bare
// `import 'playwright'` — which the Levi's deliverables script uses — fails from
// this directory. Probe the known caches, and let PLAYWRIGHT_ENTRY override.

import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const NPX_CACHE = '/root/.npm/_npx';

function candidates() {
  const out = [];
  if (process.env.PLAYWRIGHT_ENTRY) out.push(process.env.PLAYWRIGHT_ENTRY);
  for (const pkg of ['playwright', 'playwright-core']) {
    try {
      for (const dir of readdirSync(NPX_CACHE)) {
        out.push(join(NPX_CACHE, dir, 'node_modules', pkg, 'index.mjs'));
      }
    } catch { /* cache absent — fall through to the error below */ }
  }
  return out;
}

export async function loadChromium() {
  for (const entry of candidates()) {
    if (!existsSync(entry)) continue;
    const mod = await import(entry);
    if (mod.chromium) return mod.chromium;
  }
  throw new Error(
    'Playwright not found. Looked in ' + NPX_CACHE + '/*/node_modules/{playwright,playwright-core}. ' +
    'Set PLAYWRIGHT_ENTRY to the absolute path of playwright/index.mjs, or run ' +
    '`npx playwright@1.61.1 install --with-deps chromium` first.'
  );
}
