# Clean & configure the prd_levis master DB (run via: odoo shell -d prd_levis).
# - reset DB identity (uuid/secret) so it doesn't clash with rnd_levis
# - deactivate outgoing mail
# - strip leftover test transactions (POS open session, draft/confirmed POs, MISC entries)
# - set passwords: staff -> Od00@2026#, super admin am.ademaryadi@gmail.com -> M@ryadi86!
# - ensure the 4 company bank accounts exist
# - verify master data intact
import uuid

env = env  # provided by odoo shell
log = lambda m: print("[clean_master] " + m)

# ---------------------------------------------------------------- 1. DB identity
env["ir.config_parameter"].sudo().set_param("database.uuid", str(uuid.uuid4()))
env["ir.config_parameter"].sudo().set_param("database.secret", str(uuid.uuid4()))
log("reset database.uuid / database.secret")
env.cr.commit()

# ---------------------------------------------------------------- 2. mail off
for model in ("ir.mail_server", "fetchmail.server"):
    if model in env:
        recs = env[model].sudo().search([])
        if recs:
            recs.write({"active": False})
            log("deactivated %d %s" % (len(recs), model))
env.cr.commit()

# ---------------------------------------------------------------- 3. strip txns
# 3a. POS orders (open session) + payments + lines. Paid POS orders block ORM
# state changes/unlink, but here they have NO linked account.move / picking / payment
# (verified), so raw SQL deletion of the throwaway test rows is safe.
cr = env.cr
cr.execute("SELECT count(*) FROM pos_order")
log("pos.order to remove (SQL): %d" % cr.fetchone()[0])
cr.execute("DELETE FROM pos_payment WHERE pos_order_id IN (SELECT id FROM pos_order)")
cr.execute("DELETE FROM pos_order_line WHERE order_id IN (SELECT id FROM pos_order)")
for rel in ("stock_reference_pos_order_rel", "l10n_id_qris_transaction_pos_order_rel"):
    cr.execute("SELECT to_regclass(%s)", (rel,))
    if cr.fetchone()[0]:
        # nosemgrep: odoo-sql-injection-percent-format - rel iterates a hardcoded table-name tuple, never user input
        cr.execute("DELETE FROM %s WHERE pos_order_id IN (SELECT id FROM pos_order)" % rel)
cr.execute("DELETE FROM pos_order")
cr.execute("DELETE FROM pos_session")
env.cr.commit()
log(
    "pos.session remaining=%d, pos.order remaining=%d"
    % (env["pos.session"].search_count([]), env["pos.order"].search_count([]))
)

# 3b. Purchases: cancel + unlink POs and their receipts/moves
pickings = env["stock.picking"].sudo().search([])
if pickings:
    try:
        pickings.action_cancel()
    except Exception as e:
        log("picking cancel warn: %s" % e)
    pickings.unlink()
log(
    "stock.picking remaining=%d, stock.move remaining=%d"
    % (env["stock.picking"].search_count([]), env["stock.move"].search_count([]))
)
pos = env["purchase.order"].sudo().search([])
if pos:
    try:
        pos.button_cancel()
    except Exception as e:
        log("PO cancel warn: %s" % e)
    pos.unlink()
log("purchase.order remaining=%d" % env["purchase.order"].search_count([]))
env.cr.commit()

# 3c. Stray manual journal entries (MISC test entries)
moves = env["account.move"].sudo().search([("move_type", "=", "entry")])
log("account.move (entry) to remove: %d" % len(moves))
for mv in moves:
    try:
        if mv.state == "posted":
            mv.button_draft()
        mv.unlink()
    except Exception as e:
        log("could not remove move %s (%s) - leaving in place" % (mv.name, e))
        env.cr.rollback()
env.cr.commit()

# Any leftover sale orders (none expected)
so = env["sale.order"].sudo().search([])
if so:
    so.write({"state": "cancel"})
    so.unlink()
env.cr.commit()

# ---------------------------------------------------------------- 4. passwords
admin = env["res.users"].sudo().search([("login", "=", "am.ademaryadi@gmail.com")], limit=1)
if admin:
    admin.active = True
    admin.password = "M@ryadi86!"
    grp_ids = [env.ref("base.group_system").id, env.ref("base.group_erp_manager").id]
    admin.write({"group_ids": [(4, g) for g in grp_ids]})
    log("super admin %s -> password set, system+erp_manager groups" % admin.login)
else:
    log("WARNING: am.ademaryadi@gmail.com not found")

staff = (
    env["res.users"]
    .sudo()
    .search(
        [
            ("share", "=", False),
            ("login", "not in", ["__system__", "public", "portaltemplate", "am.ademaryadi@gmail.com"]),
        ]
    )
)
n = 0
for u in staff:
    u.password = "Od00@2026#"
    n += 1
log("staff users set to default password: %d" % n)
env.cr.commit()

# ---------------------------------------------------------------- 5. bank accounts
company = env["res.company"].search([], limit=1)
partner = company.partner_id
banks = {
    "1680008812008": "Mandiri",
    "7898989920": "BNI",
    "001901888305302": "BRI",
    "2685151268": "BCA",
}
Bank = env["res.partner.bank"].sudo()
for acc, name in banks.items():
    if not Bank.search([("acc_number", "=", acc)], limit=1):
        Bank.create(
            {
                "acc_number": acc,
                "partner_id": partner.id,
                "acc_holder_name": "PT ERA BUSANA RETAILINDO",
            }
        )
        log("created company bank %s (%s)" % (acc, name))
env.cr.commit()


# ---------------------------------------------------------------- 6. verify
def count(model, domain=None):
    return env[model].sudo().search_count(domain or [])


log("==== VERIFY prd_levis ====")
log("company           : %s" % company.name)
log("account.account   : %d" % count("account.account"))
log("account.tax       : %d" % count("account.tax"))
log("account.journal   : %d" % count("account.journal"))
log("product.category  : %d" % count("product.category"))
log("product.template  : %d" % count("product.template"))
log("res.users         : %d" % count("res.users"))
log("-- transactional (expect 0) --")
for m in [
    "sale.order",
    "purchase.order",
    "pos.order",
    "pos.session",
    "stock.picking",
    "account.move",
    "account.payment",
]:
    log("%-16s : %d" % (m, count(m)))
log("==== DONE ====")
env.cr.commit()
