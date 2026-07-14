// WMS screenshot capture against the live erp_dev instance.
const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://localhost:18069';
const DB = 'erp_dev';
const USER = 'admin';
const PASS = 'wmsdemo123';
const OUT = path.resolve(__dirname, '..', 'img');

const SHOTS = [
  // [filename, url, waitSelector, optional tabLabel]
  ['putaway-strategy.png', `/odoo/action-custom_wms_putaway.action_putaway_strategy/3`, '.o_form_view'],
  ['putaway-suggestions.png', `/odoo/action-custom_wms_putaway.action_putaway_suggestion`, '.o_list_view'],
  ['cycle-count-session.png', `/odoo/action-custom_wms_cycle_count.action_cycle_count_session/1`, '.o_form_view'],
  ['cycle-count-plan.png', `/odoo/action-custom_wms_cycle_count.action_cycle_count_plan`, '.o_list_view'],
  ['transfer-orders.png', `/odoo/action-custom_wms_to_engine.action_transfer_order`, '.o_list_view'],
  ['transfer-order-rules.png', `/odoo/action-custom_wms_to_engine.action_to_rule`, '.o_list_view'],
  ['hht-devices.png', `/odoo/action-custom_hht_bridge.action_hht_device`, '.o_list_view'],
  ['hht-scan-log.png', `/odoo/action-custom_hht_bridge.action_hht_scan_log`, '.o_list_view'],
  ['barcode-session.png', `/odoo/action-custom_barcode.action_custom_barcode_scan_session/1`, '.o_form_view'],
  ['quality-checks.png', `/odoo/action-custom_quality_full.action_quality_check`, '.o_list_view'],
  ['quality-points.png', `/odoo/action-custom_quality_full.action_quality_point`, '.o_list_view'],
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();

  // ---- login via JSON session authenticate (sets session cookie on the context) ----
  console.log('authenticating...');
  const resp = await ctx.request.post(`${BASE}/web/session/authenticate`, {
    headers: { 'Content-Type': 'application/json' },
    data: { jsonrpc: '2.0', params: { db: DB, login: USER, password: PASS } },
  });
  const body = await resp.json();
  if (!body.result || !body.result.uid) {
    throw new Error('auth failed: ' + JSON.stringify(body).slice(0, 300));
  }
  console.log('authenticated uid=', body.result.uid);
  await page.goto(`${BASE}/odoo`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.o_main_navbar, .o_home_menu, .o_action_manager', { timeout: 30000 });
  console.log('webclient loaded, url=', page.url());

  let ok = 0, fail = 0;
  for (const [file, url, waitSel, tab] of SHOTS) {
    try {
      await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector(waitSel, { timeout: 25000 });
      await page.waitForLoadState('networkidle').catch(()=>{});
      if (tab) {
        const t = page.locator(`.o_notebook a:has-text("${tab}")`).first();
        if (await t.count()) { await t.click(); await sleep(400); }
      }
      await sleep(900); // let rendering settle
      await page.screenshot({ path: path.join(OUT, file) });
      console.log('  OK', file);
      ok++;
    } catch (e) {
      console.log('  FAIL', file, '-', e.message.split('\n')[0]);
      fail++;
    }
  }

  // ---- HHT PWA shell (best-effort) ----
  try {
    await page.goto(`${BASE}/hht/`, { waitUntil: 'domcontentloaded' });
    await sleep(1500);
    await page.screenshot({ path: path.join(OUT, 'hht-pwa-shell.png') });
    console.log('  OK hht-pwa-shell.png');
    ok++;
  } catch (e) { console.log('  FAIL hht-pwa-shell -', e.message.split('\n')[0]); fail++; }

  console.log(`done: ${ok} ok, ${fail} fail`);
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
