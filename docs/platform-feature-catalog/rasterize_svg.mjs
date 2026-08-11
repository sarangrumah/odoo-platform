// Rasterise src/svg/*.svg to src/png/*.png at 2x for the DOCX build.
//
// Word does not render SVG reliably, so the pandoc path needs bitmaps. The PDF
// path keeps the vectors.
//
// Usage: node rasterize_svg.mjs

import { mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadChromium } from './playwright_entry.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SVG_DIR = join(HERE, 'src', 'svg');
const PNG_DIR = join(HERE, 'src', 'png');

mkdirSync(PNG_DIR, { recursive: true });

const chromium = await loadChromium();
const browser = await chromium.launch();
const context = await browser.newContext({ colorScheme: 'light', deviceScaleFactor: 2 });
const page = await context.newPage();

for (const file of readdirSync(SVG_DIR).filter((f) => f.endsWith('.svg')).sort()) {
  const svg = readFileSync(join(SVG_DIR, file), 'utf8');
  await page.setContent(
    `<!doctype html><meta charset="utf-8">
     <style>html,body{margin:0;padding:0;background:#fff;display:inline-block}</style>
     ${svg}`,
    { waitUntil: 'load' },
  );
  const el = await page.$('svg');
  const out = join(PNG_DIR, `${basename(file, '.svg')}.png`);
  await el.screenshot({ path: out, omitBackground: false });
  console.log(`  ${basename(out)}`);
}

await browser.close();
