# -*- coding: utf-8 -*-
"""Configure custom_account_deferred on the ARKA-AIM companies.

WHY THIS IS NEEDED
------------------
``custom_account_deferred`` is installed on prd_arkaaim, but neither company
carries a deferred expense account, a deferred revenue account or a deferred
journal — so the module refuses to generate any deferral / recognition entry.
The feature looks present in the menu and does nothing, which is exactly the
kind of silent config gap the payment blocker turned out to be.

prd_levis_begbal has been running with this configured since 24-Jul-2026
(``scripts/tenants/levis/74_set_deferred_config.py``). This script applies the
same choices to ARKA, which happens to use the same CoA names:

    deferred_expense_account_id -> "Other prepaid expenses"     1116100007  (asset_prepayments)
    deferred_revenue_account_id -> "Deferred Income - Current"  2103300009  (liability_current)
    deferred_journal_id         -> the company's general journal

JOURNAL DIFFERS PER COMPANY AND PER DB. prd_arkaaim company 1 has ``MISC``
("Jurnal Umum") and company 2 has ``JM`` ("Journal Memorial") — there is no
MISC on company 2. trn_arkaaim has MISC on both. Hence a preference list rather
than a single code.

Matching is by account CODE within the company: prd_arkaaim's CoA is
per-company, so the same code exists as two records, and ``account.code`` is
company-dependent on Odoo 19 — a plain read returns blank for the non-active
company. The script resolves ``with_company`` and refuses to guess: an account
or journal it cannot find is reported and that company is skipped.

WHEN TO RUN
-----------
trn_arkaaim first, then prd_arkaaim. Idempotent.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < setup_deferred_config.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
# (code, allowed account types) — first candidate found in the company's CoA
# wins. Two charts are in play: prd_arkaaim runs the 10-digit Erajaya-style
# chart, trn_arkaaim still runs the older 8-digit ARKA chart.
EXPENSE_CANDIDATES = (
    ("1116100007", ("asset_prepayments",)),  # prd: Other prepaid expenses
    ("11210040", ("asset_current", "asset_prepayments")),  # trn: Prepaid Expense
)
REVENUE_CANDIDATES = (
    ("2103300009", ("liability_current",)),  # prd: Deferred Income - Current
    ("28110030", ("liability_current",)),  # trn: Deferred Revenue
)
JOURNAL_CODES = ("MISC", "JM")  # first match wins
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

if "deferred_journal_id" not in env["res.company"]._fields:
    raise SystemExit("custom_account_deferred is not installed on this DB — install it first.")

Account = env["account.account"].sudo()
Journal = env["account.journal"].sudo()

print("=" * 78)
print("Deferred config — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("=" * 78)


def find_account(company, candidates):
    """First candidate code present in ``company``'s CoA with an acceptable type."""
    tried = []
    for code, allowed_types in candidates:
        account = Account.with_company(company).search(
            [("code", "=", code), ("company_ids", "in", company.id)], limit=1
        )
        if not account:
            tried.append("%s (absent)" % code)
            continue
        if account.account_type not in allowed_types:
            # A wrong type here books the deferral to the wrong side of the
            # balance sheet and nobody notices until the audit.
            tried.append("%s (type %s)" % (code, account.account_type))
            continue
        return account, None
    return None, "no usable account among %s" % ", ".join(tried)


changed = 0
for company in env["res.company"].sudo().search([], order="id"):
    expense, err_e = find_account(company, EXPENSE_CANDIDATES)
    revenue, err_r = find_account(company, REVENUE_CANDIDATES)

    journal = Journal.browse()
    for code in JOURNAL_CODES:
        journal = Journal.search(
            [("code", "=", code), ("type", "=", "general"), ("company_id", "=", company.id)], limit=1
        )
        if journal:
            break
    err_j = None if journal else "no general journal among %s" % ", ".join(JOURNAL_CODES)

    problems = [e for e in (err_e, err_r, err_j) if e]
    if problems:
        print("SKIP  company %s (%s): %s" % (company.id, company.name, "; ".join(problems)))
        continue

    current = (
        company.deferred_expense_account_id,
        company.deferred_revenue_account_id,
        company.deferred_journal_id,
    )
    wanted = (expense, revenue, journal)
    if current == wanted:
        print("OK    company %s (%s): already configured" % (company.id, company.name))
        continue

    print(
        "SET   company %s (%s):\n"
        "        expense  %-28s -> %s (%s)\n"
        "        revenue  %-28s -> %s (%s)\n"
        "        journal  %-28s -> %s (%s)"
        % (
            company.id,
            company.name,
            current[0].display_name if current[0] else "NOT SET",
            expense.with_company(company).code,
            expense.name,
            current[1].display_name if current[1] else "NOT SET",
            revenue.with_company(company).code,
            revenue.name,
            current[2].code if current[2] else "NOT SET",
            journal.code,
            journal.name,
        )
    )
    if COMMIT:
        company.write(
            {
                "deferred_expense_account_id": expense.id,
                "deferred_revenue_account_id": revenue.id,
                "deferred_journal_id": journal.id,
            }
        )
    changed += 1

print("-" * 78)
print("%d company(ies) %s" % (changed, "updated" if COMMIT else "would change"))

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
