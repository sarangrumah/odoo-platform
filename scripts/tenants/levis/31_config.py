# Apply config to a levis DB (run via odoo shell):
#  1. tracking = lot for all storable products
#  2. cash rounding "Nearest Rupiah" (1.00, HALF-UP) on POS + enable feature
#  3. map product categories to the EBR COA (income/expense/stock accounts, real_time/fifo)
# Cost price is handled separately (prd: leave 0; demo: 60% in seed).
env = env
log = lambda m: print("[cfg] " + m)
Acc = env['account.account'].with_company(1)
def acc(code):
    a = Acc.search([('code', '=', code)], limit=1)
    if not a:
        raise Exception("account %s not found" % code)
    return a

# ---------------------------------------------------------- 1. tracking = lot
templates = env['product.template'].search([('is_storable', '=', True)])
templates.write({'tracking': 'lot'})
log("set tracking=lot on storable templates: %d" % len(templates))
# make sure the lots/serial feature group is enabled company-wide
grp = env.ref('stock.group_production_lot', raise_if_not_found=False)
if grp:
    internal = env['res.users'].search([('share', '=', False)])
    grp.sudo().write({'user_ids': [(4, u.id) for u in internal]})
log("lots feature users: %d" % (len(grp.user_ids) if grp else 0))
env.cr.commit()

# ---------------------------------------------------------- 2. cash rounding
gain = acc('9990000001'); loss = acc('9990000002')
CR = env['account.cash.rounding']
cr = CR.search([('rounding', '=', 1.0), ('rounding_method', '=', 'HALF-UP')], limit=1)
if not cr:
    cr = CR.create({
        'name': 'Nearest Rupiah', 'rounding': 1.0, 'rounding_method': 'HALF-UP',
        'strategy': 'add_invoice_line',
        'profit_account_id': gain.id, 'loss_account_id': loss.id,
    })
log("cash.rounding: %s (id=%s)" % (cr.name, cr.id))
# enable the Cash Rounding feature (so it's available on invoices)
try:
    env['res.config.settings'].create({'group_cash_rounding': True}).execute()
except Exception as e:
    log("group_cash_rounding setting warn: %s" % e)
# apply to all POS configs
n = 0
for pc in env['pos.config'].search([]):
    vals = {'cash_rounding': True, 'rounding_method': cr.id}
    if 'only_round_cash_method' in pc._fields:
        vals['only_round_cash_method'] = False
    pc.write(vals)
    n += 1
log("POS configs with cash rounding: %d" % n)
env.cr.commit()

# ---------------------------------------------------------- 3. category -> COA
ACCMAP = {
    'textile':     dict(inc='5120010001', exp='6120010001', val='1113100021', inp='2103109121'),
    'footwear':    dict(inc='5120010002', exp='6120010002', val='1113100022', inp='2103109122'),
    'accessories': dict(inc='5120010003', exp='6120010003', val='1113100023', inp='2103109123'),
    'misc':        dict(inc='5120010004', exp='6120010004', val='1113100024', inp='2103109124'),
}
OUT = acc('1113200001')  # Stock in transit (shared variation counterpart fallback)
STJ = env['account.journal'].search([('code', '=', 'STJ')], limit=1) or \
      env['account.journal'].search([('type', '=', 'general')], limit=1)
# resolve once
RES = {b: {k: acc(c) for k, c in m.items()} for b, m in ACCMAP.items()}

def root_name(cat):
    c = cat
    while c.parent_id:
        c = c.parent_id
    return (c.name or '').upper()

def branch(rn):
    if 'FOOTWEAR' in rn: return 'footwear'
    if 'ACCESSORIES' in rn: return 'accessories'
    if 'BOTTOMS' in rn or 'TOPS' in rn: return 'textile'
    return 'misc'

cats = env['product.category'].search([])
from collections import Counter
bc = Counter()
for cat in cats:
    b = branch(root_name(cat))
    bc[b] += 1
    m = RES[b]
    cat.with_company(1).write({
        'property_account_income_categ_id': m['inc'].id,
        'property_account_expense_categ_id': m['exp'].id,
        'property_valuation': 'real_time',
        'property_cost_method': 'fifo',
        'property_stock_valuation_account_id': m['val'].id,
        'account_stock_variation_id': m['inp'].id,   # GR/IR clearing per branch
        'property_stock_journal': STJ.id,
    })
log("categories mapped by branch: %s (total %d)" % (dict(bc), len(cats)))
env.cr.commit()

# ---- verify ----
sample = env['product.category'].search([('name', 'in', ['MENS FOOTWEAR', 'MENS BOTTOMS', 'MENS ACCESSORIES'])])
for c in sample:
    cc = c.with_company(1)
    log("CAT %-18s inc=%s exp=%s val=%s val_method=%s" % (
        c.name, cc.property_account_income_categ_id.code, cc.property_account_expense_categ_id.code,
        cc.property_stock_valuation_account_id.code, cc.property_valuation))
log("tracking=lot templates: %d / total %d" % (
    env['product.template'].search_count([('tracking', '=', 'lot')]),
    env['product.template'].search_count([])))
log("==== DONE ====")
