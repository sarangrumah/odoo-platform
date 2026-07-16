import { chromium } from 'playwright';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const [, , src, out, title] = process.argv;
if (!src || !out) { console.error('usage: node build-pdf.mjs <src.html> <out.pdf> [footerTitle]'); process.exit(1); }

const b = await chromium.launch();
const p = await (await b.newContext()).newPage();
await p.goto('file://' + path.resolve(src), { waitUntil: 'networkidle' });
await p.waitForTimeout(1500);

const foot = title || "Levi's / EBR — Odoo 19";
const tmpCover = out + '.cover.tmp.pdf';
const tmpBody = out + '.body.tmp.pdf';

// Cover: full-bleed, no footer, no margins.
await p.pdf({
  path: tmpCover, format: 'A4', printBackground: true,
  pageRanges: '1',
  margin: { top: '0', bottom: '0', left: '0', right: '0' },
});

// Body: page 2 onward, with a running footer. Page numbers restart at 1 here,
// so the cover stays unnumbered.
await p.pdf({
  path: tmpBody, format: 'A4', printBackground: true,
  pageRanges: '2-',
  displayHeaderFooter: true,
  headerTemplate: '<div></div>',
  footerTemplate: `
    <div style="width:100%;font-size:7.5pt;color:#5A6472;font-family:Inter,Helvetica,Arial,sans-serif;
                padding:0 16mm;display:flex;justify-content:space-between;border-top:1px solid #D8DCE3;
                padding-top:2mm;margin:0 0 6mm 0;">
      <span>${foot}</span>
      <span>Hal. <span class="pageNumber"></span></span>
    </div>`,
  margin: { top: '18mm', bottom: '20mm', left: '0', right: '0' },
});
await b.close();

execFileSync('pdfunite', [tmpCover, tmpBody, out]);
fs.unlinkSync(tmpCover); fs.unlinkSync(tmpBody);

const info = execFileSync('pdfinfo', [out]).toString();
console.log('written', out, '|', info.split('\n').find(l => l.startsWith('Pages')));
