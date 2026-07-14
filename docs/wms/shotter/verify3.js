const { chromium } = require('playwright');
const path = require('path');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const fileUrl = 'file:///' + path.resolve(__dirname, '..', 'WMS-Feature-Configuration-Guide.html').replace(/\\/g, '/');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1400 }, deviceScaleFactor: 1.4 });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  const broken = await page.evaluate(() =>
    [...document.querySelectorAll('img')].filter(im => !im.complete || im.naturalWidth === 0).map(im => im.getAttribute('src')));
  const imgs = await page.evaluate(() => document.querySelectorAll('img').length);
  const figs = await page.evaluate(() => document.querySelectorAll('figure').length);
  console.log(`GUIDE: imgs=${imgs}, figures=${figs}, broken=${JSON.stringify(broken)}, errors=${errs.length?errs.slice(0,3):'none'}`);
  for (const [id, name] of [['product','g2-product'],['wh-volume','g3-bin'],['barcode','g10-barcode']]) {
    await page.evaluate((i) => document.getElementById(i).scrollIntoView(), id);
    await sleep(450);
    await page.screenshot({ path: path.join(__dirname, name + '.png') });
  }
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
