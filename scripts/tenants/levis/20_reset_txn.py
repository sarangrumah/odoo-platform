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
#
# Env flags:
#   RESET_DRY=0             actually execute (default 1 = report only)
#   RESET_KEEP_JOURNALS     comma-separated account.journal codes whose moves survive,
#                           e.g. "EBRTB" to keep loaded opening balances / trial balances.
import os
env = env  # provided by odoo shell
log = lambda m: print("[reset_txn] " + m)
cr = env.cr
DRY = os.environ.get("RESET_DRY", "1") != "0"
KEEP_JOURNALS = [c.strip() for c in os.environ.get("RESET_KEEP_JOURNALS", "").split(",") if c.strip()]

CORE = [
    "account_move", "account_move_line", "account_payment",
    "account_bank_statement", "account_bank_statement_line",
    "pos_order", "pos_order_line", "pos_payment", "pos_session",
    "stock_move", "stock_move_line", "stock_picking", "stock_valuation_layer", "stock_quant",
    "purchase_order", "purchase_order_line", "sale_order", "sale_order_line",
    "retail_import_log", "retail_import_line",
    # Transaction tables the FK walk can NEVER reach, because they only point AT master
    # (res_company/res_partner/res_users) or are pointed at BY a core table rather than
    # pointing to one. Without seeding them here they survive every reset as orphans:
    #   custom_po_return(+_line)  -- only the *_allocation child links to purchase/stock,
    #                                so RTV headers kept showing up in Purchase Return.
    #   account_full_reconcile    -- account_move_line.full_reconcile_id points to IT.
    "custom_po_return", "custom_po_return_line", "account_full_reconcile",
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

# ---- leak detector: txn-ish tables that hold rows but no FK path reaches them ----
# Any future module that stores documents without an FK to a CORE table reproduces the
# custom_po_return bug. Surface it loudly instead of silently leaving orphans behind.
cr.execute(
    "SELECT c.relname, c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname='public' AND c.relkind='r' AND c.relname NOT IN %s AND c.relname NOT IN %s "
    "AND (c.relname LIKE 'custom_%%' OR c.relname LIKE 'levis_%%' OR c.relname LIKE 'retail_%%')",
    (tuple(closure) or ('',), tuple(GUARD) or ('',)),
)
leaks = []
for t, _ in cr.fetchall():
    cr.execute('SELECT count(*) FROM "%s"' % t)
    n = cr.fetchone()[0]
    if n:
        leaks.append((t, n))
if leaks:
    log("!!! UNREACHABLE non-empty txn-ish tables (NOT wiped -- add to CORE if transactional):")
    for t, n in sorted(leaks, key=lambda r: -r[1]):
        log("    %-52s %d" % (t, n))

# ---- rows to preserve (RESET_KEEP_JOURNALS) -------------------------------------
KEEP_MOVE, KEEP_AML = set(), set()
if KEEP_JOURNALS:
    cr.execute(
        "SELECT m.id FROM account_move m JOIN account_journal j ON j.id=m.journal_id "
        "WHERE j.code = ANY(%s)", (KEEP_JOURNALS,),
    )
    KEEP_MOVE = {r[0] for r in cr.fetchall()}
    if KEEP_MOVE:
        cr.execute("SELECT id FROM account_move_line WHERE move_id = ANY(%s)", (list(KEEP_MOVE),))
        KEEP_AML = {r[0] for r in cr.fetchall()}
    log("keep journals %s -> %d moves / %d lines preserved"
        % (KEEP_JOURNALS, len(KEEP_MOVE), len(KEEP_AML)))
    if not KEEP_MOVE:
        raise SystemExit("RESET_KEEP_JOURNALS=%s matched no journal -- refusing to run"
                         % ",".join(KEEP_JOURNALS))

# FK columns of every closure table that point at account_move / account_move_line.
cr.execute(
    "SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text "
    "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey) "
    "WHERE c.contype='f' AND c.confrelid::regclass::text IN ('account_move','account_move_line') "
    "AND c.conrelid::regclass::text = ANY(%s)",
    (list(closure),),
)
_move_refs = {}
for tbl, col, tgt in cr.fetchall():
    _move_refs.setdefault(tbl, []).append((col, tgt))


def delete_sql(t):
    """DELETE statement for closure table `t`, honouring the keep-set.

    A row survives only if it is anchored to a kept move/line: at least one of its
    FK columns into account_move/account_move_line points inside the keep-set, and
    none of them points outside it. Tables with no such FK are emptied wholesale --
    that is what makes pos_session (move_id NULL) go away while the tax/analytic
    rel-tables hanging off the kept EBRTB lines stay.
    """
    if not KEEP_MOVE:
        return 'DELETE FROM %s' % t, ()
    if t == "account_move":
        return 'DELETE FROM %s WHERE id <> ALL(%%s)' % t, (list(KEEP_MOVE),)
    if t == "account_move_line":
        return 'DELETE FROM %s WHERE move_id <> ALL(%%s)' % t, (list(KEEP_MOVE),)
    refs = _move_refs.get(t)
    if not refs:
        return 'DELETE FROM %s' % t, ()
    inside, outside, params = [], [], []
    for col, tgt in refs:
        keep = list(KEEP_MOVE if tgt == "account_move" else KEEP_AML)
        inside.append('("%s" IS NOT NULL AND "%s" = ANY(%%s))' % (col, col))
        outside.append('("%s" IS NOT NULL AND "%s" <> ALL(%%s))' % (col, col))
        params.append(keep)
    # keep  <=>  (any col inside) AND NOT (any col outside)   ->   delete the negation
    sql = 'DELETE FROM %s WHERE NOT ((%s) AND NOT (%s))' % (t, " OR ".join(inside), " OR ".join(outside))
    return sql, tuple(params + params)

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
        # Don't null a GUARD ref that points at a row we are about to preserve
        # (e.g. res_company.account_opening_move_id -> a kept EBRTB opening move).
        keep = KEEP_MOVE if tgt == "account_move" else (KEEP_AML if tgt == "account_move_line" else set())
        if keep:
            cr.execute('UPDATE "%s" SET "%s"=NULL WHERE "%s" IS NOT NULL AND "%s" <> ALL(%%s)'
                       % (tbl, col, col, col), (list(keep),))
        else:
            cr.execute('UPDATE "%s" SET "%s"=NULL WHERE "%s" IS NOT NULL' % (tbl, col, col))
        log("nulled %s.%s (-> %s) rows=%d" % (tbl, col, tgt, cr.rowcount))
    # wipe with FK triggers disabled (no cascade, no ordering, no master reached)
    cr.execute("SET session_replication_role = 'replica'")
    for t in closure:
        # `t` is already a valid (regclass) identifier — quoted only where needed;
        # do NOT wrap in quotes again (would double-quote e.g. "Products").
        sql, params = delete_sql(t)
        cr.execute(sql, params)
    # Rows preserved by RESET_KEEP_JOURNALS may still point at siblings that were just
    # deleted (a kept line's full_reconcile_id, reversed_entry_id, ...). FK triggers are
    # off, so nothing complained -- null those nullable refs or the DB is left corrupt.
    if KEEP_MOVE:
        cr.execute(
            "SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text "
            "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey) "
            "WHERE c.contype='f' AND NOT a.attnotnull "
            "AND c.conrelid::regclass::text = ANY(%s) AND c.confrelid::regclass::text = ANY(%s)",
            (list(closure), list(closure)),
        )
        for tbl, col, tgt in cr.fetchall():
            cr.execute(
                'UPDATE "%s" SET "%s"=NULL WHERE "%s" IS NOT NULL '
                'AND NOT EXISTS (SELECT 1 FROM "%s" p WHERE p.id="%s"."%s")'
                % (tbl, col, col, tgt, tbl, col)
            )
            if cr.rowcount:
                log("orphan ref nulled %s.%s (-> %s) rows=%d" % (tbl, col, tgt, cr.rowcount))
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
