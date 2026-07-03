// Re-capture all WMS shots with smart clipping: keep the app navbar + breadcrumb,
// crop the empty canvas below the rendered content.
const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://localhost:18069', DB = 'erp_dev', USER = 'admin', PASS = 'wmsdemo123';
const OUT = path.resolve(__dirname, '..', 'img');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const SHOTS = [
  ['putaway-strategy.png', '/odoo/action-custom_wms_putaway.action_putaway_strategy/3', 'form'],
  ['putaway-suggestions.png', '/odoo/action-custom_wms_putaway.action_putaway_suggestion', 'any'],
  ['cycle-count-session.png', '/odoo/action-custom_wms_cycle_count.action_cycle_count_session/1', 'form', 'Lines'],
  ['cycle-count-plan.png', '/odoo/action-custom_wms_cycle_count.action_cycle_count_plan', 'any'],
  ['transfer-orders.png', '/odoo/action-custom_wms_to_engine.action_transfer_order', 'any'],
  ['transfer-order-rules.png', '/odoo/action-custom_wms_to_engine.action_to_rule', 'any'],
  ['hht-devices.png', '/odoo/action-custom_hht_bridge.action_hht_device', 'any'],
  ['hht-scan-log.png', '/odoo/action-custom_hht_bridge.action_hht_scan_log', 'any'],
  ['barcode-session.png', '/odoo/action-custom_barcode.action_custom_barcode_scan_session/1', 'form'],
  ['quality-checks.png', '/odoo/action-custom_quality_full.action_quality_check', 'any'],
  ['quality-points.png', '/odoo/action-custom_quality_full.action_quality_point', 'any'],
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1100 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const resp = await ctx.request.post(`${BASE}/web/session/authenticate`, {
    headers: { 'Content-Type': 'application/json' },
    data: { jsonrpc: '2.0', params: { db: DB, login: USER, password: PASS } },
  });
  if (!(await resp.json()).result) throw new Error('auth failed');
  await page.goto(`${BASE}/odoo`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.o_main_navbar', { timeout: 30000 });

  for (const [file, url, kind, tab] of SHOTS) {
    try {
      await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.o_list_view, .o_form_view, .o_kanban_view, .o_view_controller', { timeout: 30000 });
      await page.waitForLoadState('networkidle').catch(()=>{});
      if (tab) {
        const t = page.locator(`.o_notebook .nav-link:has-text("${tab}"), .o_notebook a:has-text("${tab}")`).first();
        if (await t.count()) { await t.click(); await sleep(600); }
      }
      await sleep(900);
      // Find the bottom of the *actual* content (rows / cards / sheet), not the
      // full-height scroll container, so we can crop the empty canvas below.
      const bottom = await page.evaluate(() => {
        const recs = [...document.querySelectorAll('.o_kanban_record')];
        if (recs.length) return Math.max(...recs.map(r => r.getBoundingClientRect().bottom));
        const tbl = document.querySelector('.o_list_table');
        if (tbl) return tbl.getBoundingClientRect().bottom;
        const sheet = document.querySelector('.o_form_sheet');
        if (sheet) return sheet.getBoundingClientRect().bottom;
        const c = document.querySelector('.o_content');
        return c ? c.getBoundingClientRect().bottom : null;
      });
      const vw = page.viewportSize().width;
      const vh = page.viewportSize().height;
      let height = bottom ? Math.min(vh, Math.ceil(bottom) + 18) : vh;
      height = Math.max(height, 360); // never absurdly short
      await page.screenshot({ path: path.join(OUT, file), clip: { x: 0, y: 0, width: vw, height } });
      console.log('  OK', file, '->', height + 'px');
    } catch (e) { console.log('  FAIL', file, '-', e.message.split('\n')[0]); }
  }
  await browser.close();
  console.log('capture2 done');
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
