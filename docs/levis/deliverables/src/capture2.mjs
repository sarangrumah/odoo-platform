import { chromium } from 'playwright';
import fs from 'fs';

const BASE = 'http://localhost:18069';
const DB = 'prd_levis_begbal';
const OUT = 'shots';

// wizard-style actions (target=new -> modal). No Escape, wait for .modal-content.
const W = [
  ['B03_retail_import_wizard', 797],
  ['G08_asset_register_wizard', 526],
  ['H01_trial_balance', 505],
  ['H02_general_ledger', 504],
  ['H03_balance_sheet', 506],
  ['H04_profit_loss', 507],
  ['H05_cash_flow', 508],
  ['H06_gl_analysis', 846],
  ['H07_aged_receivable', 509],
  ['H08_aged_payable', 510],
  ['H09_kartu_utang', 512],
  ['H10_kartu_piutang', 513],
  ['H11_rekap_faktur_pajak', 824],
  ['H12_rekap_bupot', 825],
  ['H13_ekualisasi_omzet', 832],
  ['I04_faktur_pengganti', 791],
  ['I05_pre_export_validation', 792],
];

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1680, height: 980 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
p.setDefaultTimeout(25000);

await p.goto(`${BASE}/web/login?db=${DB}`, { waitUntil: 'domcontentloaded' });
await p.fill('input[name=login]', 'docbot@levis.local');
await p.fill('input[name=password]', 'DocBot#2026');
await p.click('button:has-text("Log in")');
await p.waitForURL(/\/odoo/, { timeout: 60000 }).catch(() => {});
await p.waitForTimeout(3000);

const res = [];
for (const [name, action] of W) {
  try {
    await p.goto(`${BASE}/odoo/action-${action}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await p.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    // a wizard renders either as a modal, or (target=current) as a plain form
    await p.waitForSelector('.modal-content, .o_form_view, .o_list_view', { timeout: 20000 }).catch(() => {});
    await p.waitForTimeout(2200);

    const isModal = await p.locator('.modal-content').count();
    await p.screenshot({ path: `${OUT}/${name}.png` });   // full page incl. dimmed backdrop
    res.push({ name, modal: !!isModal });
    console.log(`ok ${name} ${isModal ? '(modal)' : '(inline form)'}`);
  } catch (e) {
    res.push({ name, err: String(e).split('\n')[0].slice(0, 80) });
    console.log('FAIL ' + name + ' :: ' + String(e).split('\n')[0].slice(0, 80));
  }
}
fs.writeFileSync('shots/_manifest_wizards.json', JSON.stringify(res, null, 2));
await b.close();
