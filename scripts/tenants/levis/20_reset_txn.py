# Reset ALL transaction data on a levis DB while KEEPING master data.
# Run via:  odoo shell -d <db> --no-http < 20_reset_txn.py
# Set DRY=1 (default) to only compute+print the delete closure; DRY=0 to actually wipe.
#
# Approach (safe): compute the transitive FK-closure of the CORE transaction tables
# (every table that references them, directly or transitively), EXCLUDING a hard GUARD
# set of master tables. Then, with session_replication_role='replica' (FK triggers off,
# so DELETE neither cascades into master nor needs ordering), DELETE every row of every
# closure table, and NULL any GUARD-table columns that pointed at a wiped table. A
# master before/after snapshot is the safety net; a full pg_dump backup exists.
#
# WARNING: an earlier version used TRUNCATE ... CASCADE which bridged via
# res_company.account_opening_move_id and wiped the whole DB. Do NOT use CASCADE here.
import os
env = env  # provided by odoo shell
log = lambda m: print("[reset_txn] " + m)
cr = env.cr
DRY = os.environ.get("RESET_DRY", "1") != "0"

CORE = [
    "account_move", "account_move_line", "account_payment",
    "account_bank_statement", "account_bank_statement_line",
    "pos_order", "pos_order_line", "pos_payment", "pos_session",
    "stock_move", "stock_move_line", "stock_picking", "stock_valuation_layer", "stock_quant",
    "purchase_order", "purchase_order_line", "sale_order", "sale_order_line",
    "retail_import_log", "retail_import_line",
]
# Master / config tables that must NEVER be emptied (their refs to txn are nulled instead).
GUARD = {
    "res_company", "res_partner", "res_users", "res_groups", "res_currency", "res_country",
    "res_bank", "res_partner_bank", "res_company_users_rel", "res_config_settings",
    "product_product", "product_template", "product_category", "product_pricelist",
    "product_pricelist_item", "product_attribute", "product_attribute_value",
    "product_template_attribute_line", "product_template_attribute_value",
    "product_supplierinfo", "uom_uom", "uom_category",
    "account_account", "account_account_tag", "account_tax", "account_tax_group",
    "account_journal", "account_group", "account_fiscal_position", "account_fiscal_position_tax",
    "account_analytic_account", "account_analytic_plan", "account_reconcile_model",
    "pos_config", "pos_category", "pos_payment_method", "pos_bill",
    "ir_model_data", "ir_config_parameter", "ir_property", "ir_sequence", "ir_default",
    "stock_warehouse", "stock_location", "stock_picking_type", "stock_lot",
    "custom_operating_unit", "custom_bast", "custom_core",
    # non-financial / non-import tables that only appear in the closure via a nullable
    # FK to a txn table — keep them, just null that ref:
    "product_value", "project_project", "project_task", "project_milestone",
}

def children_of(tables):
    cr.execute(
        "SELECT DISTINCT c.conrelid::regclass::text "
        "FROM pg_constraint c "
        "WHERE c.contype='f' AND c.confrelid::regclass::text = ANY(%s)",
        (list(tables),),
    )
    return {r[0] for r in cr.fetchall()}

# ---- compute closure ----
closure, frontier = set(CORE), set(CORE)
hit_guard = set()
while frontier:
    kids = children_of(frontier)
    hit_guard |= (kids & GUARD)
    new = kids - closure - GUARD
    closure |= new
    frontier = new

# keep only tables that actually exist (e.g. stock_valuation_layer was removed in Odoo 19)
existing = set()
for t in closure:
    cr.execute("SELECT to_regclass(%s)", (t,))
    if cr.fetchone()[0]:
        existing.add(t)
missing = closure - existing
closure = existing
log("closure = %d existing tables to empty (%d listed names absent); "
    "GUARD tables referenced (kept, refs nulled): %s"
    % (len(closure), len(missing), sorted(hit_guard)))

# rows per closure table (skip zero for brevity)
cr.execute(
    "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE relname = ANY(%s) ORDER BY n_live_tup DESC",
    (list(closure),),
)
nonzero = [(t, n) for t, n in cr.fetchall() if n]
log("non-empty closure tables (%d):" % len(nonzero))
for t, n in nonzero:
    log("    %-52s %d" % (t, n))

MASTER = ['account.account', 'account.tax', 'account.journal', 'product.category',
          'product.template', 'product.product', 'pos.config', 'pos.payment.method',
          'res.partner', 'res.users']
before = {m: env[m].sudo().search_count([]) for m in MASTER}

if DRY:
    log("DRY RUN — no deletes performed. Set RESET_DRY=0 to execute.")
else:
    # GUARD columns pointing at closure tables -> NULL them first
    cr.execute(
        "SELECT c.conrelid::regclass::text tbl, a.attname col, c.confrelid::regclass::text tgt "
        "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey) "
        "WHERE c.contype='f' AND c.conrelid::regclass::text = ANY(%s) "
        "AND c.confrelid::regclass::text = ANY(%s)",
        (list(GUARD), list(closure)),
    )
    for tbl, col, tgt in cr.fetchall():
        cr.execute('UPDATE "%s" SET "%s"=NULL WHERE "%s" IS NOT NULL' % (tbl, col, col))
        log("nulled %s.%s (-> %s)" % (tbl, col, tgt))
    # wipe with FK triggers disabled (no cascade, no ordering, no master reached)
    cr.execute("SET session_replication_role = 'replica'")
    for t in closure:
        # `t` is already a valid (regclass) identifier — quoted only where needed;
        # do NOT wrap in quotes again (would double-quote e.g. "Products").
        cr.execute("DELETE FROM %s" % t)
    cr.execute("SET session_replication_role = 'origin'")
    env.cr.commit()
    env.invalidate_all()
    # remove lazy X24 products + import xids
    IMD = env['ir.model.data'].sudo()
    lazy = IMD.search([('module', '=', 'levis'), ('name', 'like', 'x24prod_%'),
                       ('model', '=', 'product.product')])
    prods = env['product.product'].sudo().browse(lazy.mapped('res_id')).exists()
    tmpls = prods.mapped('product_tmpl_id')
    nlazy = len(prods)
    try:
        prods.unlink(); tmpls.exists().unlink()
    except Exception as e:
        log("lazy unlink warn: %s" % e); env.cr.rollback(); nlazy = 0
    for pat in ('x24prod_%', 'posorder_%', 'posreturn_%', 'x31entry_%'):
        IMD.search([('module', '=', 'levis'), ('name', 'like', pat)]).unlink()
    env.cr.commit()
    log("lazy products removed: %d" % nlazy)

# ---- verify master ----
after = {m: env[m].sudo().search_count([]) for m in MASTER}
log("==== MASTER before -> after ====")
ok = True
for m in MASTER:
    d = after[m] - before[m]
    tag = ""
    if m in ('product.template', 'product.product') and d < 0:
        tag = "(lazy removed)"
    elif d != 0:
        tag = "!!! CHANGED !!!"; ok = False
    log("  %-20s %8d -> %8d  %s" % (m, before[m], after[m], tag))
log("==== %s ====" % ("MASTER INTACT" if ok else "MASTER CHANGED — CHECK/RESTORE"))
