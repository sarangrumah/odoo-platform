# Seed demo_levis with transactions (run via: odoo shell -d demo_levis).
# Stage 1: customers, stock-on-hand, purchases->bill->payment, sales->invoice->payment,
# and a manual accounting entry. POS is seeded by 21_seed_pos.py.
import uuid
from datetime import date

env = env
log = lambda m: print("[seed] " + m)

# Guard: don't double-seed.
if env['sale.order'].search_count([]) or env['purchase.order'].search_count([]):
    log("transactions already present - aborting to avoid double seed")
else:
    company = env['res.company'].browse(1)
    env['ir.config_parameter'].sudo().set_param('database.uuid', str(uuid.uuid4()))
    env['ir.config_parameter'].sudo().set_param('database.secret', str(uuid.uuid4()))

    D1 = date(2026, 6, 5)
    D2 = date(2026, 6, 12)
    BANK = env['account.journal'].search([('type', '=', 'bank')], limit=1)
    PRODUCT_IDS = [195132, 195136, 195141, 195145, 195155, 195165, 195170, 385974]
    products = env['product.product'].browse(PRODUCT_IDS).exists()
    # ensure a cost price for valuation / margin
    for p in products:
        if not p.standard_price:
            p.standard_price = round(p.lst_price * 0.55)
    log("products: %d, bank journal: %s" % (len(products), BANK.code))

    def validate_picking(picking):
        """Force full done quantities and validate, swallowing backorder wizard."""
        for mv in picking.move_ids:
            mv.quantity = mv.product_uom_qty
            if 'picked' in mv._fields:
                mv.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get('res_model'):
            wiz = env[res['res_model']].with_context(res.get('context', {})).browse(res.get('res_id'))
            if wiz and hasattr(wiz, 'process'):
                wiz.process()
        return picking.state

    def pay(moves, pay_date):
        env['account.payment.register'].with_context(
            active_model='account.move', active_ids=moves.ids
        ).create({'journal_id': BANK.id, 'payment_date': pay_date}).action_create_payments()

    # ---------------------------------------------------- A. customers
    Partner = env['res.partner']
    cust_data = [
        {'name': 'Andi Wijaya', 'is_company': False},
        {'name': 'Toko Sinar Jaya', 'is_company': True},
        {'name': 'PT Mitra Ritel Nusantara', 'is_company': True},
    ]
    customers = env['res.partner']
    for d in cust_data:
        c = Partner.create(dict(d, customer_rank=1, country_id=env.ref('base.id').id))
        customers |= c
    log("customers created: %d" % len(customers))
    env.cr.commit()

    # ---------------------------------------------------- B. stock on hand
    locations = [5, 20, 26, 32]  # WH/Stock + 3 POS store stocks
    n = 0
    for p in products:
        for loc in locations:
            qty = 200 if loc == 5 else 100
            q = env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': p.id, 'location_id': loc, 'inventory_quantity': qty})
            q.action_apply_inventory()
            n += 1
    log("stock quants applied: %d" % n)
    env.cr.commit()

    # ---------------------------------------------------- C. purchases
    vendors = env['res.partner'].search([('supplier_rank', '>', 0)], limit=2)
    pos_made = []
    for vi, vendor in enumerate(vendors):
        lines = [(0, 0, {'product_id': p.id, 'product_qty': 40, 'price_unit': round(p.lst_price * 0.55)})
                 for p in products[vi * 3: vi * 3 + 3]]
        po = env['purchase.order'].create({'partner_id': vendor.id, 'date_order': D1, 'order_line': lines})
        po.button_confirm()
        for pk in po.picking_ids:
            validate_picking(pk)
        po.action_create_invoice()
        bill = po.invoice_ids.filtered(lambda m: m.state == 'draft')
        bill.invoice_date = D1
        bill.action_post()
        pay(bill, D2)
        pos_made.append(po.name)
    log("purchases done: %s" % pos_made)
    env.cr.commit()

    # ---------------------------------------------------- D. sales
    so_made = []
    for i, cust in enumerate(customers):
        lines = [(0, 0, {'product_id': p.id, 'product_uom_qty': 3 + i})
                 for p in products[i * 2: i * 2 + 2]]
        so = env['sale.order'].create({'partner_id': cust.id, 'date_order': D1, 'order_line': lines})
        so.action_confirm()
        for pk in so.picking_ids:
            validate_picking(pk)
        inv = so._create_invoices()
        inv.invoice_date = D2
        inv.action_post()
        pay(inv, D2)
        so_made.append(so.name)
    log("sales done: %s" % so_made)
    env.cr.commit()

    # ---------------------------------------------------- E. manual accounting entry
    misc = env['account.journal'].search([('type', '=', 'general'), ('code', '=', 'MISC')], limit=1)
    accs = env['account.account'].search([('account_type', 'in', ('expense', 'expense_direct_cost'))], limit=1)
    cash_acc = env['account.account'].search([('account_type', '=', 'asset_cash')], limit=1)
    if misc and accs and cash_acc:
        je = env['account.move'].create({
            'journal_id': misc.id, 'date': D2, 'ref': 'Demo accrual',
            'line_ids': [
                (0, 0, {'account_id': accs.id, 'name': 'Misc expense', 'debit': 1500000, 'credit': 0}),
                (0, 0, {'account_id': cash_acc.id, 'name': 'Cash out', 'debit': 0, 'credit': 1500000}),
            ],
        })
        je.action_post()
        log("manual JE posted: %s" % je.name)
    env.cr.commit()

    log("==== STAGE 1 SUMMARY ====")
    for m in ['res.partner', 'purchase.order', 'sale.order', 'account.move', 'account.payment']:
        log("%-16s : %d" % (m, env[m].search_count([])))
    log("==== DONE ====")
