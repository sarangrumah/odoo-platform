const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://localhost:18069', DB = 'erp_dev', USER = 'admin', PASS = 'wmsdemo123';
const OUT = path.resolve(__dirname, '..', 'img');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const resp = await ctx.request.post(`${BASE}/web/session/authenticate`, {
    headers: { 'Content-Type': 'application/json' },
    data: { jsonrpc: '2.0', params: { db: DB, login: USER, password: PASS } },
  });
  if (!(await resp.json()).result) throw new Error('auth failed');
  await page.goto(`${BASE}/odoo`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.o_main_navbar', { timeout: 30000 });

  async function capture(file, url, { tab } = {}) {
    try {
      await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.o_list_view, .o_form_view, .o_kanban_view, .o_view_controller', { timeout: 30000 });
      await page.waitForLoadState('networkidle').catch(()=>{});
      if (tab) {
        const t = page.locator(`.o_notebook .nav-link:has-text("${tab}"), .o_notebook a:has-text("${tab}")`).first();
        if (await t.count()) { await t.click(); await sleep(600); }
      }
      await sleep(1100);
      await page.screenshot({ path: path.join(OUT, file) });
      console.log('  OK', file);
    } catch (e) { console.log('  FAIL', file, '-', e.message.split('\n')[0]); }
  }

  await capture('cycle-count-session.png', '/odoo/action-custom_wms_cycle_count.action_cycle_count_session/1', { tab: 'Lines' });
  await capture('putaway-suggestions.png', '/odoo/action-custom_wms_putaway.action_putaway_suggestion');
  await capture('transfer-orders.png', '/odoo/action-custom_wms_to_engine.action_transfer_order');
  await browser.close();
  console.log('retry done');
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
