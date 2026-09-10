# Verify the store-float cycle end to end, then roll everything back.
#
#   docker exec -i odoo19-platform-odoo \
#     odoo shell -d <db> --no-http --shell-interface=python \
#     < 102_verify_petty_cash_store_float.py
#
# Expects 101_setup_petty_cash_store_float.py to have run (types PCA/PCR/PCC and
# at least one float). Writes nothing: the last statement is a rollback.
#
# Two shell-only traps this script exists to sidestep, both of which make the
# module look broken when it is not:
#
#   * A UserError caught in a shell does NOT undo the INSERT that preceded it.
#     The refused request keeps reserving float for the rest of the run, so the
#     next assertion fails for the wrong reason. Hence the savepoints.
#   * ``env.invalidate_all()`` FLUSHES before it invalidates -- after a
#     ROLLBACK TO SAVEPOINT it writes the phantom totals straight back into the
#     row the rollback just restored. Use ``env.clear()``.
#
# Prints go to stderr; `odoo shell` swallows stdout.
import sys


def p(*a):
    print(*a, file=sys.stderr)


Req = env["petty.cash.request"]
Type = env["petty.cash.type"]
Float = env["petty.cash.float"]
co = env.company
t_init = Type.search([("code", "=", "PCA")], limit=1)
t_real = Type.search([("code", "=", "PCR")], limit=1)
t_claim = Type.search([("code", "=", "PCC")], limit=1)
# Whichever store has no float activity yet, so the run starts from a clean
# balance -- falling back to the first float configured.
_floats = Float.search([("company_id", "=", co.id)])
_fresh = _floats.filtered(lambda f: not f.request_ids) or _floats
if not _fresh:
    p("No petty.cash.float configured -- run 101 first.")
    raise SystemExit(1)
store = _fresh[0].l10n_ou_analytic_id
p("store:", store.display_name)
partner = env["res.partner"].create({"name": "Kasir Kemang"})
emp = env["hr.employee"].create({"name": "Kasir Kemang", "work_contact_id": partner.id})
expense = env["account.account"].search([("account_type", "=", "expense")], limit=1) or env["account.account"].create(
    {"code": "ZPC6001", "name": "Beban Toko", "account_type": "expense"}
)


def expect_refused(label, fn):
    """Run fn expecting a UserError, WITHOUT leaving its half-created row behind.

    A UserError caught in a plain shell does not undo the INSERT that preceded
    it, so the refused request would keep reserving float for the rest of the
    run. The savepoint is what makes the refusal a true no-op.

    env.clear(), not env.invalidate_all(): the latter FLUSHES before it
    invalidates, which writes the phantom float total straight back into the
    row the savepoint just restored.
    """
    env.cr.execute("SAVEPOINT pcv")
    try:
        fn()
    except Exception as e:
        env.cr.execute("ROLLBACK TO SAVEPOINT pcv")
        env.clear()
        p("OK  %s ->" % label, str(e).strip().splitlines()[0][:90])
        return
    env.cr.execute("ROLLBACK TO SAVEPOINT pcv")
    env.clear()
    p("FAIL: %s was accepted" % label)


def mk(t, amt):
    return Req.create(
        {
            "employee_id": emp.id,
            "advance_type_id": t.id,
            "l10n_ou_analytic_id": store.id,
            "amount_requested": amt,
            "purpose": "verify",
        }
    )


def bal():
    """Read the float straight out of Postgres.

    Reading through the ORM here means trusting whatever cache state the
    previous savepoint dance left behind; the columns are stored, so the row
    is the authority.
    """
    env.flush_all()
    f = Float.search([("l10n_ou_analytic_id", "=", store.id)], limit=1)
    env.cr.execute(
        "SELECT amount_granted, amount_reserved, amount_available, amount_gl_balance FROM petty_cash_float WHERE id=%s",
        (f.id,),
    )
    return (f,) + env.cr.fetchone()


p("plafon awal:", Float.search([("l10n_ou_analytic_id", "=", store.id)]).amount_plafon)

# 1. plafon enforced
expect_refused("tolak Petty Cash Awal 1.5jt", lambda: mk(t_init, 1500000))

# 2. grant + disburse
init = mk(t_init, 1000000)
init.action_submit()
init.action_approve()
init.action_disburse()
p("OK  Petty Cash Awal", init.name, "state", init.state, "| granted/reserved/avail/gl:", bal()[1:])

# 3. draft reserves
usage = mk(t_real, 300000)
p("OK  Realisasi draft", usage.name, "reserved", usage.amount_float_consumed, "| avail:", bal()[3])

# 4. over-budget refused
expect_refused("tolak realisasi 800rb (sisa 700rb)", lambda: mk(t_real, 800000))

# 5. claim bypasses
claim = mk(t_claim, 900000)
p("OK  Claim", claim.name, "lolos tanpa potong saldo; reserved", claim.amount_float_consumed, "| avail:", bal()[3])

# 6. approve + realize 250rb
usage.action_submit()
usage.action_approve()
p("    realisasi approved, tanpa Bank Out; state:", usage.state)
rz = env["petty.cash.realization"].create(
    {
        "request_id": usage.id,
        "line_ids": [
            (
                0,
                0,
                {"line_type": "expense", "name": "ATK", "account_id": expense.id, "price_unit": 250000, "quantity": 1},
            )
        ],
    }
)
rz.action_post()
f, g, r, a, gl = bal()
p("OK  realisasi 250rb diposting; request reserved", usage.amount_float_consumed, "| avail:", a, "| GL:", gl)

# 7. close & release
usage.action_close_release()
f, g, r, a, gl = bal()
p("OK  close&release; state", usage.state, "| avail:", a, "| GL:", gl)
p("    jurnal realisasi:", rz.bill_ids.mapped("name"), rz.bill_ids.mapped("state"))

env.cr.rollback()
p("ROLLED BACK")
