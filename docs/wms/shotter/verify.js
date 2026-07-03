const { chromium } = require('playwright');
const path = require('path');
const FILE = 'file:///' + path.resolve(__dirname, '..', 'WMS-Odoo-Capability-Deck.html').replace(/\\/g, '/');
const OUT = path.resolve(__dirname);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  await page.goto(FILE, { waitUntil: 'networkidle' });
  const total = await page.evaluate(() => document.querySelectorAll('.slide').length);
  console.log('total slides =', total);
  // find indices of live slides (those containing the LIVE badge)
  const liveIdx = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('.slide').forEach((s, i) => { if (s.querySelector('.live-badge')) out.push(i); });
    return out;
  });
  console.log('live slide indices =', JSON.stringify(liveIdx));
  for (const i of liveIdx) {
    await page.evaluate((n) => window.show(n), i);
    await sleep(500);
    const broken = await page.evaluate(() => {
      const imgs = [...document.querySelectorAll('.slide.active img')];
      return imgs.filter(im => !im.complete || im.naturalWidth === 0).map(im => im.getAttribute('src'));
    });
    await page.screenshot({ path: path.join(OUT, `verify-${i}.png`) });
    console.log(`slide ${i}: imgs broken =`, JSON.stringify(broken));
  }
  console.log('console errors:', errs.length ? errs.slice(0,5) : 'none');
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
