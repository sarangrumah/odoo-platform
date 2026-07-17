import { chromium } from 'playwright';
import fs from 'fs';

const BASE = 'http://localhost:18069';
const DB = 'prd_levis_begbal';
const OUT = 'shots';
fs.mkdirSync(OUT, { recursive: true });

// name, action id, mode: 'list' | 'first' (open first record) | 'new' (click New)
const T = [
  // --- A. Home / navigation
  ['A01_home_apps', null, 'apps'],

  // --- B. Retail Import (IT / Ops Admin)
  ['B01_retail_import_logs', 795, 'list'],
  ['B02_retail_import_log_form', 795, 'first'],
  ['B03_retail_import_wizard', 797, 'list'],
  ['B04_retail_import_profiles', 794, 'list'],
  ['B05_retail_import_profile_form', 794, 'first'],
  ['B06_retail_import_feeds', 796, 'list'],
  ['B07_retail_import_mailboxes', 850, 'list'],

  // --- C. Point of Sale (Store)
  ['C01_pos_dashboard', 610, 'list'],
  ['C02_pos_orders', 593, 'list'],
  ['C03_pos_order_form', 593, 'first'],
  ['C04_pos_sessions', 613, 'list'],
  ['C05_pos_session_form', 613, 'first'],
  ['C06_pos_payments', 609, 'list'],
  ['C07_pos_reporting_orders', 616, 'list'],

  // --- D. Purchase (Buyer / Approver)
  ['D01_purchase_orders', 470, 'list'],
  ['D02_purchase_order_new', 470, 'new'],
  ['D03_rfq', 469, 'list'],
  ['D04_po_returns', 842, 'list'],
  ['D05_po_return_new', 842, 'new'],
  ['D06_vendors', 299, 'list'],

  // --- E. Inventory (Warehouse / DC)
  ['E01_inventory_overview', 432, 'list'],
  ['E02_scrap_batches', 844, 'list'],
  ['E03_scrap_batch_new', 844, 'new'],
  ['E04_scrap', 395, 'list'],
  ['E05_products', 438, 'list'],
  ['E06_product_form', 438, 'first'],
  ['E07_lots', 393, 'list'],
  ['E08_stock_report', 437, 'list'],
  ['E09_moves_history', 404, 'list'],

  // --- F. Accounting / AP
  ['F01_invoicing_dashboard', null, 'url:/odoo/accounting'],
  ['F02_vendor_bills', null, 'url:/odoo/action-account.action_move_in_invoice_type'],
  ['F03_journal_entries', null, 'url:/odoo/action-account.action_move_journal_line'],
  ['F04_journal_entry_form', null, 'url:/odoo/action-account.action_move_journal_line', 'first'],
  ['F05_chart_of_accounts', null, 'url:/odoo/action-account.action_account_form'],
  ['F06_inventory_reconciliation', 822, 'list'],
  ['F07_inventory_reconciliation_new', 822, 'new'],
  ['F08_periodic_cogs', 847, 'list'],
  ['F09_periodic_cogs_new', 847, 'new'],
  ['F10_card_bin_mdr', 845, 'list'],
  ['F11_card_bin_mdr_new', 845, 'new'],
  ['F12_trade_nontrade_accounts', 843, 'list'],
  ['F13_payments', null, 'url:/odoo/action-account.action_account_payments_payable'],

  // --- G. Fixed Assets
  ['G01_fixed_assets', 525, 'list'],
  ['G02_fixed_asset_new', 525, 'new'],
  ['G03_asset_groups', 523, 'list'],
  ['G04_asset_group_form', 523, 'first'],
  ['G05_asset_locations', 524, 'list'],
  ['G06_post_depreciation', 841, 'list'],
  ['G07_revaluations', 840, 'list'],
  ['G08_asset_register_wizard', 526, 'list'],

  // --- H. Reports
  ['H01_trial_balance', 505, 'list'],
  ['H02_general_ledger', 504, 'list'],
  ['H03_balance_sheet', 506, 'list'],
  ['H04_profit_loss', 507, 'list'],
  ['H05_cash_flow', 508, 'list'],
  ['H06_gl_analysis', 846, 'list'],
  ['H07_aged_receivable', 509, 'list'],
  ['H08_aged_payable', 510, 'list'],
  ['H09_kartu_utang', 512, 'list'],
  ['H10_kartu_piutang', 513, 'list'],
  ['H11_rekap_faktur_pajak', 824, 'list'],
  ['H12_rekap_bupot', 825, 'list'],
  ['H13_ekualisasi_omzet', 832, 'list'],

  // --- I. Tax (Pajak Indonesia)
  ['I01_withholding_rules', 789, 'list'],
  ['I02_pph_categories', 788, 'list'],
  ['I03_withholding_lines', 790, 'list'],
  ['I04_faktur_pengganti', 791, 'list'],
  ['I05_pre_export_validation', 792, 'list'],
  ['I06_coretax_bupot', 669, 'list'],

  // --- J. Approvals
  ['J01_approvals', null, 'url:/odoo/approvals'],

  // --- K. Settings / Technical (IT Admin)
  ['K01_system_parameters', null, 'url:/odoo/action-base.action_ir_config_list'],
  ['K02_scheduled_actions', null, 'url:/odoo/action-base.ir_cron_act'],
  ['K03_users', null, 'url:/odoo/action-base.action_res_users'],
  ['K04_companies', null, 'url:/odoo/action-base.action_res_company_form'],
];

const results = [];

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1680, height: 980 }, deviceScaleFactor: 2 });
const p = await ctx.newPage();
p.setDefaultTimeout(25000);

// login
await p.goto(`${BASE}/web/login?db=${DB}`, { waitUntil: 'domcontentloaded' });
await p.fill('input[name=login]', 'docbot@levis.local');
await p.fill('input[name=password]', 'DocBot#2026');
await p.click('button:has-text("Log in")');
await p.waitForURL(/\/odoo/, { timeout: 60000 }).catch(() => {});
await p.waitForTimeout(3000);
console.log('logged in ->', p.url());

async function settle() {
  await p.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  // wait for Odoo action manager to render something
  await p.waitForSelector('.o_action_manager .o_view_controller, .o_form_view, .o_list_view, .o_kanban_view, .modal-content', { timeout: 20000 }).catch(() => {});
  await p.waitForTimeout(1800);
}

for (const [name, action, mode, sub] of T) {
  try {
    let url;
    if (mode === 'apps') url = `${BASE}/odoo`;
    else if (typeof mode === 'string' && mode.startsWith('url:')) url = BASE + mode.slice(4);
    else url = `${BASE}/odoo/action-${action}`;

    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await settle();

    const eff = sub || mode;
    if (eff === 'first') {
      const row = p.locator('.o_list_view .o_data_row').first();
      if (await row.count()) { await row.click(); await settle(); }
    } else if (eff === 'new') {
      const nb = p.locator('button.o_list_button_add, .o_control_panel button:has-text("New")').first();
      if (await nb.count()) { await nb.click(); await settle(); }
    }

    // close any lingering tooltip/notification
    await p.keyboard.press('Escape').catch(() => {});
    await p.waitForTimeout(300);

    await p.screenshot({ path: `${OUT}/${name}.png` });
    const bad = await p.locator('.o_error_dialog, .modal-title:has-text("Error")').count();
    results.push({ name, url, ok: !bad, err: bad ? 'error dialog' : '' });
    console.log((bad ? 'ERRDLG ' : 'ok     ') + name);
  } catch (e) {
    await p.screenshot({ path: `${OUT}/${name}.png` }).catch(() => {});
    results.push({ name, ok: false, err: String(e).split('\n')[0].slice(0, 90) });
    console.log('FAIL   ' + name + ' :: ' + String(e).split('\n')[0].slice(0, 90));
  }
}

fs.writeFileSync('shots/_manifest.json', JSON.stringify(results, null, 2));
console.log(`\n${results.filter(r => r.ok).length}/${results.length} ok`);
await b.close();
