import { chromium } from 'playwright';

const BASE = 'http://localhost:18069';
const DB = 'prd_levis_begbal';

// Wizards render as a small modal centred in a big grey backdrop. A full-page shot
// is mostly dead space and the form is unreadable in print, so clip to the dialog.
const W = [
  ['B03_retail_import_wizard', 797],
  ['G08_asset_register_wizard', 526],
  ['H01_trial_balance', 505],
  ['H02_general_ledger', 504],
  ['H03_balance_sheet', 506],
  ['H04_profit_loss', 507],
  ['H05_cash_flow', 508],
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
const ctx = await b.newContext({ viewport: { width: 1680, height: 980 }, deviceScaleFactor: 3 });
const p = await ctx.newPage();
p.setDefaultTimeout(25000);

await p.goto(`${BASE}/web/login?db=${DB}`, { waitUntil: 'domcontentloaded' });
await p.fill('input[name=login]', 'docbot@levis.local');
await p.fill('input[name=password]', 'DocBot#2026');
await p.click('button:has-text("Log in")');
await p.waitForURL(/\/odoo/, { timeout: 60000 }).catch(() => {});
await p.waitForTimeout(3000);

for (const [name, action] of W) {
  try {
    await p.goto(`${BASE}/odoo/action-${action}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await p.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    await p.waitForSelector('.modal-content', { timeout: 20000 });
    await p.waitForTimeout(1600);
    await p.locator('.modal-content').first().screenshot({ path: `shots/${name}.png` });
    console.log('ok   ' + name);
  } catch (e) {
    console.log('FAIL ' + name + ' :: ' + String(e).split('\n')[0].slice(0, 70));
  }
}
await b.close();
