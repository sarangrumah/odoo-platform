const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://localhost:18069', DB = 'erp_dev', USER = 'admin', PASS = 'wmsdemo123';
const OUT = path.resolve(__dirname, '..', 'img');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1700 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const resp = await ctx.request.post(`${BASE}/web/session/authenticate`, {
    headers: { 'Content-Type': 'application/json' },
    data: { jsonrpc: '2.0', params: { db: DB, login: USER, password: PASS } },
  });
  if (!(await resp.json()).result) throw new Error('auth failed');
  await page.goto(`${BASE}/odoo/action-stock.product_template_action_product/28`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.o_form_view', { timeout: 30000 });
  await page.waitForLoadState('networkidle').catch(()=>{});
  const t = page.locator('.o_notebook .nav-link:has-text("Inventory")').first();
  if (await t.count()) { await t.click(); await sleep(700); }
  await sleep(800);
  const bottom = await page.evaluate(() => {
    const g = [...document.querySelectorAll('.o_inner_group, .o_group')];
    // bottom of the Putaway/Velocity group if present, else form sheet
    const sheet = document.querySelector('.o_form_sheet');
    let b = sheet ? sheet.getBoundingClientRect().bottom : null;
    return b;
  });
  const vw = page.viewportSize().width, vh = page.viewportSize().height;
  let height = bottom ? Math.min(vh, Math.ceil(bottom) + 18) : 1300;
  await page.screenshot({ path: path.join(OUT, 'product-inventory.png'), clip: { x: 0, y: 0, width: vw, height } });
  console.log('OK product-inventory.png ->', height + 'px');
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
