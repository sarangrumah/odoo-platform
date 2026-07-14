// Capture configuration screenshots for the Feature & Configuration Guide.
const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://localhost:18069', DB = 'erp_dev', USER = 'admin', PASS = 'wmsdemo123';
const OUT = path.resolve(__dirname, '..', 'img');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const SHOTS = [
  ['product-inventory.png', '/odoo/action-stock.product_template_action_product/28', { tab: 'Inventory' }],
  ['locations-list.png', '/odoo/action-stock.action_location_form', {}],
  ['location-bin.png', '/odoo/action-stock.action_location_form/36', {}],
  ['operation-types.png', '/odoo/action-stock.stock_picking_type_action', {}],
  ['label-templates.png', '/odoo/action-custom_barcode.action_custom_label_template', {}],
  ['printer-config.png', '/odoo/action-custom_barcode.action_custom_printer_config', {}],
  ['barcode-formats.png', '/odoo/action-custom_barcode.action_custom_barcode_format', {}],
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

  for (const [file, url, { tab }] of SHOTS) {
    try {
      await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.o_list_view, .o_form_view, .o_kanban_view, .o_view_controller', { timeout: 30000 });
      await page.waitForLoadState('networkidle').catch(()=>{});
      if (tab) {
        const t = page.locator(`.o_notebook .nav-link:has-text("${tab}"), .o_notebook a:has-text("${tab}")`).first();
        if (await t.count()) { await t.click(); await sleep(600); }
      }
      await sleep(900);
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
      const vw = page.viewportSize().width, vh = page.viewportSize().height;
      let height = bottom ? Math.min(vh, Math.ceil(bottom) + 18) : vh;
      height = Math.max(height, 340);
      await page.screenshot({ path: path.join(OUT, file), clip: { x: 0, y: 0, width: vw, height } });
      console.log('  OK', file, '->', height + 'px');
    } catch (e) { console.log('  FAIL', file, '-', e.message.split('\n')[0]); }
  }
  await browser.close();
  console.log('capture3 done');
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
