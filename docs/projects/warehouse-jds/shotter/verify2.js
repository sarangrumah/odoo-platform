const { chromium } = require('playwright');
const path = require('path');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const fileUrl = (n) => 'file:///' + path.resolve(__dirname, '..', n).replace(/\\/g, '/');

(async () => {
  const browser = await chromium.launch({ headless: true });

  // ---- 1. Feature/Config guide (long-form doc) ----
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 }, deviceScaleFactor: 1.4 });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(fileUrl('WMS-Feature-Configuration-Guide.html'), { waitUntil: 'networkidle' });
  const broken = await page.evaluate(() =>
    [...document.querySelectorAll('img')].filter(im => !im.complete || im.naturalWidth === 0).map(im => im.getAttribute('src')));
  const h2s = await page.evaluate(() => document.querySelectorAll('h2').length);
  const imgs = await page.evaluate(() => document.querySelectorAll('img').length);
  console.log(`GUIDE: h2=${h2s}, imgs=${imgs}, broken=${JSON.stringify(broken)}, errors=${errs.length?errs.slice(0,3):'none'}`);
  // capture top + a config-table section + a screenshot section
  await page.screenshot({ path: path.join(__dirname, 'guide-top.png') });
  await page.evaluate(() => document.getElementById('putaway').scrollIntoView());
  await sleep(400);
  await page.screenshot({ path: path.join(__dirname, 'guide-putaway.png') });

  // ---- 2. Deck appendix slides ----
  const p2 = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.4 });
  await p2.goto(fileUrl('WMS-Odoo-Capability-Deck.html'), { waitUntil: 'networkidle' });
  const total = await p2.evaluate(() => document.querySelectorAll('.slide').length);
  console.log('DECK total slides =', total);
  for (const n of [total-3, total-2, total-1]) {
    await p2.evaluate((i) => window.show(i), n);
    await sleep(400);
    const b = await p2.evaluate(() => [...document.querySelectorAll('.slide.active img')].filter(im=>!im.complete||im.naturalWidth===0).length);
    await p2.screenshot({ path: path.join(__dirname, `deck-appx-${n}.png`) });
    console.log(`  deck slide ${n}: broken imgs=${b}`);
  }
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
