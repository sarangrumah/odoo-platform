// Print src/catalog.html to A4 PDF via headless Chromium.
//
// The cover is printed separately with no margins and no footer, then joined
// with pdfunite, so the cover page carries no page number — the same trick the
// Levi's deliverables use.
//
// Usage: node build_pdf.mjs [input.html] [output.pdf]

import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { loadChromium } from './playwright_entry.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const input = resolve(process.argv[2] || join(HERE, 'src', 'catalog.html'));
const output = resolve(process.argv[3] || join(HERE, 'dist', 'Katalog_Fitur_Platform_Odoo_Erajaya.pdf'));
const tmp = join(HERE, 'dist', '.pdf-parts');

const FOOTER = `
<div style="width:100%;font-family:Calibri,sans-serif;font-size:7.5pt;color:#5A6675;
            padding:0 16mm;display:flex;justify-content:space-between;">
  <span>Katalog Fitur Platform Odoo — Erajaya Group</span>
  <span>Halaman <span class="pageNumber"></span> dari <span class="totalPages"></span></span>
</div>`;

const EMPTY = '<div></div>';

if (!existsSync(input)) {
  console.error(`input not found: ${input}`);
  process.exit(1);
}

const chromium = await loadChromium();
const browser = await chromium.launch({ args: ['--font-render-hinting=none'] });
// Force light on BOTH the context and the media emulation: setting only one
// leaves prefers-color-scheme active and a dark block would print inverted.
const context = await browser.newContext({ colorScheme: 'light' });
const page = await context.newPage();
await page.goto(pathToFileURL(input).href, { waitUntil: 'load' });
await page.emulateMedia({ media: 'print', colorScheme: 'light' });

mkdirSync(tmp, { recursive: true });
const coverPdf = join(tmp, 'cover.pdf');
const bodyPdf = join(tmp, 'body.pdf');

await page.pdf({
  path: coverPdf,
  format: 'A4',
  printBackground: true,
  pageRanges: '1',
  margin: { top: '0mm', bottom: '0mm', left: '0mm', right: '0mm' },
});

await page.pdf({
  path: bodyPdf,
  format: 'A4',
  printBackground: true,
  pageRanges: '2-',
  displayHeaderFooter: true,
  headerTemplate: EMPTY,
  footerTemplate: FOOTER,
  margin: { top: '18mm', bottom: '20mm', left: '16mm', right: '16mm' },
});

await browser.close();

mkdirSync(dirname(output), { recursive: true });
execFileSync('pdfunite', [coverPdf, bodyPdf, output]);
rmSync(tmp, { recursive: true, force: true });

const pages = execFileSync('pdfinfo', [output], { encoding: 'utf8' })
  .split('\n').find((l) => l.startsWith('Pages:'))?.split(/\s+/)[1];
console.log(`${pages} pages → ${output}`);
