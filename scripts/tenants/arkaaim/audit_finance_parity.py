# -*- coding: utf-8 -*-
"""Read-only audit of the finance/accounting configuration of an ARKA-AIM DB.

WHY THIS EXISTS
---------------
The "No outstanding account could be found to make the payment" blocker on
prd_arkaaim was pure configuration: company 1 had no outstanding account on any
payment-method line, no chart-template outstanding XMLID and no transfer
account, while company 2 quietly worked off the XMLID fallback. Nothing in the
UI shows those three jalur side by side, so the gap stayed invisible until a
user tried to pay a bill.

This script prints them together, plus the neighbouring settings that fail the
same silent way (deferred, accrual, down payment, forex, POS receivable, lock
dates, available payment methods). Run it before and after any config change,
and on every new ARKA DB, as the evidence trail.

It writes nothing and rolls back on exit. Safe on production.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < audit_finance_parity.py

Compare two DBs by running it twice and diffing the output.
"""

env = self.env  # noqa: F821  (provided by odoo shell)

Account = env["account.account"].sudo()
Journal = env["account.journal"].sudo()
IMD = env["ir.model.data"].sudo()

# Company settings that break silently when unset, with the symptom they cause.
COMPANY_FIELDS = (
    ("transfer_account_id", "last-resort outstanding account for new journals"),
    ("account_journal_suspense_account_id", "bank statement suspense"),
    ("downpayment_account_id", "DP invoices leak into sales revenue when empty"),
    ("deferred_expense_account_id", "custom_account_deferred cannot post"),
    ("deferred_revenue_account_id", "custom_account_deferred cannot post"),
    ("expense_accrual_account_id", "accrual entries"),
    ("revenue_accrual_account_id", "accrual entries"),
    ("income_currency_exchange_account_id", "forex gain"),
    ("expense_currency_exchange_account_id", "forex loss"),
    ("petty_cash_advance_account_id", "custom_petty_cash realization"),
)

LOCK_FIELDS = (
    "fiscalyear_lock_date",
    "tax_lock_date",
    "sale_lock_date",
    "purchase_lock_date",
    "hard_lock_date",
)


def code_of(account, company):
    """``account.code`` is company-dependent in Odoo 19 — read it in scope."""
    if not account:
        return "NOT SET"
    return account.with_company(company).code or "?"


companies = env["res.company"].sudo().search([], order="id")

print("=" * 96)
print("Finance config audit — db %s" % env.cr.dbname)
print("=" * 96)

for company in companies:
    print("\n" + "=" * 96)
    print("COMPANY %s — %s   (currency %s)" % (company.id, company.name, company.currency_id.name))
    print("=" * 96)

    # --- 1. how a payment finds its liquidity account --------------------
    print("\n[1] Outstanding account resolution")
    journals = Journal.with_company(company).search(
        [("company_id", "=", company.id), ("type", "in", ("bank", "cash"))], order="id"
    )
    if not journals:
        print("    (no bank/cash journal)")
    for journal in journals:
        print(
            "    %-6s %-8s %-40s default=%s"
            % (journal.code, journal.type, journal.name, code_of(journal.default_account_id, company))
        )
        lines = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
        if not lines:
            print("           (no payment method line)")
        for line in lines:
            acct = line.payment_account_id
            flag = "  <-- EMPTY" if not acct else ""
            print(
                "           %-16s %-8s outstanding=%s%s"
                % (line.name, line.payment_method_id.payment_type, code_of(acct, company), flag)
            )

    # jalur 2: the chart-template refs, keyed on the ROOT company id
    root = company.root_id or company
    print("\n    chart-template fallback (jalur 2), root company %s:" % root.id)
    for suffix in ("debit", "credit"):
        xmlid = "%s_account_journal_payment_%s_account_id" % (root.id, suffix)
        row = IMD.search([("module", "=", "account"), ("name", "=", xmlid)], limit=1)
        if row:
            acct = Account.browse(row.res_id).exists()
            print("      %-12s %s -> %s (%s)" % (suffix, xmlid, code_of(acct, company), acct.display_name))
        else:
            print("      %-12s %s -> MISSING" % (suffix, xmlid))

    # --- 2. company accounting defaults ----------------------------------
    print("\n[2] Company accounting defaults")
    for fname, why in COMPANY_FIELDS:
        if fname not in company._fields:
            print("    %-42s (field absent — module not installed)" % fname)
            continue
        value = company[fname]
        shown = code_of(value, company) if value else "NOT SET"
        flag = "  <-- %s" % why if not value else ""
        print("    %-42s %s%s" % (fname, shown, flag))

    # --- 3. lock dates ---------------------------------------------------
    print("\n[3] Lock dates")
    for fname in LOCK_FIELDS:
        if fname not in company._fields:
            continue
        print("    %-42s %s" % (fname, company[fname] or "-"))

# --- 4. database-wide -----------------------------------------------------
print("\n" + "=" * 96)
print("DATABASE-WIDE")
print("=" * 96)

print("\n[4] Payment methods available")
for method in env["account.payment.method"].sudo().search([], order="code, payment_type"):
    print("    %-16s %-9s %s" % (method.code, method.payment_type, method.name))

print("\n[5] Accounting modules installed")
watched = (
    "account",
    "account_accountant",
    "custom_accounting_full",
    "custom_accounting_reports",
    "custom_accounting_asset",
    "custom_accounting_recurring",
    "custom_account_reconcile",
    "custom_account_deferred",
    "custom_account_batch_payment",
    "custom_bank_import",
    "custom_petty_cash",
    "custom_payment_admin_fee",
    "custom_payment_methods_id",
    "custom_payment_voucher",
    "custom_tax_id",
    "custom_coretax_export",
)
modules = env["ir.module.module"].sudo().search([("name", "in", list(watched))])
by_name = {m.name: m for m in modules}
for name in watched:
    module = by_name.get(name)
    if not module:
        print("    %-32s ABSENT (not in the addons path)" % name)
    else:
        print("    %-32s %-12s %s" % (name, module.state, module.latest_version or "-"))

print("\n[6] Payment volume (sanity: a company with 0 payments may be blocked)")
env.cr.execute(
    """
    SELECT company_id, state, COUNT(*)
      FROM account_payment
     GROUP BY company_id, state
     ORDER BY company_id, state
    """
)
rows = env.cr.fetchall()
if not rows:
    print("    (no payment at all)")
for company_id, state, count in rows:
    print("    company %s  %-10s %d" % (company_id, state, count))

env.cr.execute("SELECT COUNT(*) FROM account_bank_statement_line")
print("\n[7] Bank statement lines: %d" % env.cr.fetchone()[0])

env.cr.rollback()
print("\n" + "=" * 96)
print("Read-only — rolled back.")
print("=" * 96)
