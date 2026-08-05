# -*- coding: utf-8 -*-
"""End-to-end cash-advance verification for both ARKA-AIM companies.

Runs a complete cycle -- request, approve, disburse, realize, return, settle --
on company 1 and company 2, then renders the Kartu Uang Muka, asserting the GL
along the way. Always ends in ``env.cr.rollback()``, so it leaves nothing
behind and is safe to run against prd_arkaaim.

Run it AFTER setup_cash_advance.py, and re-run it after any upgrade of
custom_petty_cash.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 --shell-interface=python \
        < verify_cash_advance.py
"""

import datetime

env = self.env  # noqa: F821

OK = True


def check(label, cond, detail=""):
    global OK
    OK = OK and bool(cond)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, (" -- %s" % detail) if detail else ""))


for cid in (1, 2):
    company = env["res.company"].browse(cid)
    print("=" * 70)
    print("Company %s -- %s" % (cid, company.name))
    e = env(context=dict(env.context, allowed_company_ids=[cid], company_id=cid, company_ids=[cid]))

    ca = e["petty.cash.type"].search([("company_id", "=", cid), ("code", "=", "CA")], limit=1)
    check("CA type exists", bool(ca))
    check(
        "CA -> 1109000002",
        ca.advance_account_id.with_company(company).code == "1109000002",
        ca.advance_account_id.with_company(company).code,
    )
    check("advance account belongs to this company", cid in ca.advance_account_id.company_ids.ids)
    check("payment journal is dedicated PCPAY", ca.payment_journal_id.code == "PCPAY", ca.payment_journal_id.code)
    check("bank-out != payment journal", ca.bank_out_journal_id != ca.payment_journal_id)

    pc = e["petty.cash.type"].search([("company_id", "=", cid), ("code", "=", "PC")], limit=1)
    check("PC -> 1115200001", pc.advance_account_id.with_company(company).code == "1115200001")
    check(
        "PC bank-out != payment journal", pc.bank_out_journal_id != pc.payment_journal_id, pc.bank_out_journal_id.code
    )

    emp = e["hr.employee"].search([("company_id", "=", cid), ("work_contact_id", "!=", False)], limit=1)
    if not emp:
        emp = e["hr.employee"].create(
            {
                "name": "CA Verify %s" % cid,
                "company_id": cid,
                "work_contact_id": e["res.partner"].create({"name": "CA Verify Contact %s" % cid}).id,
            }
        )

    req = e["petty.cash.request"].create(
        {
            "employee_id": emp.id,
            "advance_type_id": ca.id,
            "company_id": cid,
            "amount_requested": 5_000_000.0,
            "purpose": "VERIFY",
        }
    )
    check("numbered from sequence", req.name != "New", req.name)
    req.action_submit()
    req.action_approve()
    req.action_disburse()
    check("state disbursed", req.state == "disbursed", req.state)
    check("disburse move posted", req.disburse_move_id.state == "posted")

    adv = req.disburse_move_id.line_ids.filtered(lambda l: l.account_id == ca.advance_account_id)
    check("Dr advance 5.000.000", adv.debit == 5_000_000.0, str(adv.debit))
    check("currency_id stamped", bool(adv.currency_id), adv.currency_id.name)
    check("amount_currency == debit", adv.amount_currency == adv.debit)
    check("move balanced", abs(sum(req.disburse_move_id.line_ids.mapped("balance"))) < 0.01)
    check("employee analytic tagged", bool(adv.analytic_distribution), str(adv.analytic_distribution))
    check("deadline set", bool(req.realization_deadline), str(req.realization_deadline))

    exp = e["account.account"].search([("company_ids", "in", cid), ("account_type", "=", "expense")], limit=1)
    real = e["petty.cash.realization"].create(
        {
            "request_id": req.id,
            "line_ids": [
                (
                    0,
                    0,
                    {"line_type": "expense", "name": "VERIFY expense", "account_id": exp.id, "price_unit": 3_000_000.0},
                )
            ],
        }
    )
    real.action_post()
    check("realization posted", real.state == "posted")
    check("outstanding 2.000.000", abs(req.amount_outstanding - 2_000_000.0) < 0.01, str(req.amount_outstanding))
    check("company-currency mirror matches", abs(req.amount_outstanding_company - 2_000_000.0) < 0.01)

    entry = real.bill_ids.filtered(lambda m: m.move_type == "entry")
    check("expense entry in the type's journal", entry.journal_id == ca.expense_journal_id, entry.journal_id.code)
    check("expense entry balanced", abs(sum(entry.line_ids.mapped("balance"))) < 0.01)

    req.action_return_balance()
    check("outstanding zero after return", abs(req.amount_outstanding) < 0.01)
    req.action_settle()
    check("state settled", req.state == "settled")
    check("advance lines reconciled", all(l.reconciled for l in req._advance_move_lines(posted_only=True)))

    st = e["petty.cash.report.statement"]._build_lines(
        {
            "company_ids": [cid],
            "date_from": datetime.date(2000, 1, 1),
            "date_to": datetime.date(2999, 12, 31),
            "posted_only": True,
        }
    )
    blocks = [b for b in st if b.get("type") == "partner"]
    check("statement has a block", len(blocks) >= 1)
    if blocks:
        blk = [b for b in blocks if b["partner_name"] == emp.name][0]
        check("statement closes at 0", abs(blk["closing"]) < 0.01, str(blk["closing"]))
        check("3 movements", len(blk["lines"]) == 3, str(len(blk["lines"])))
        check(
            "all movements named", all(r["movement"] for r in blk["lines"]), str([r["movement"] for r in blk["lines"]])
        )

    tbl = e["petty.cash.report.statement"].get_report_table(
        {"company_ids": [cid], "date_from": "2000-01-01", "date_to": "2999-12-31"}
    )
    check("screen rows non-blank", bool(tbl["lines"]) and any(any(r["values"].values()) for r in tbl["lines"]))

    out = e["petty.cash.report.outstanding"]._build_lines(
        {
            "company_ids": [cid],
            "date_from": datetime.date(2000, 1, 1),
            "date_to": datetime.date(2999, 12, 31),
            "posted_only": True,
        }
    )
    check("outstanding report renders", bool(out))

print("=" * 70)
print("RESULT: %s" % ("ALL CHECKS PASSED" if OK else "SOME CHECKS FAILED"))
env.cr.rollback()
print("rolled back -- DB unchanged")
