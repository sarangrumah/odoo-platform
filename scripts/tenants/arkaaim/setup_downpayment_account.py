# -*- coding: utf-8 -*-
"""Route customer down-payment invoices off the sales revenue COA (sheet item #6).

WHY THIS IS NEEDED
------------------
Client complaint: "Jurnal pembuatan DP belum tersedia, masih masuk ke coa/jurnal
penjualan."

That is exactly what core Odoo does when the company has no down-payment
account configured. ``sale/wizard/sale_make_invoice_advance.py`` builds the DP
invoice line with::

    self.company_id.downpayment_account_id or account

where ``account`` falls back to the product's income account — i.e. sales
revenue. On prd_arkaaim ``res_company.downpayment_account_id`` is NULL for BOTH
companies, so every down payment lands in revenue and inflates recognised
sales before the work is delivered.

The fix is configuration, not code: point each company at its customer-advance
liability account. A DP then posts Dr AR / Cr Advances-from-customers, and only
moves to revenue when the final invoice consumes it.

ACCOUNT CHOICE
--------------
``2108100001`` "Advances from customers - Third parties"
(``account_type = liability_current``). This mirrors what the localisation
templates do (e.g. ``l10n_th`` maps ``downpayment_account_id`` to a 2124xx
liability), and matches the Erajaya CoA.

NOTE ON ACCOUNT IDS: prd_arkaaim's CoA is per-company, not shared, so the same
code exists as two records — id 309 (company 1 / AIM) and id 1022 (company 2 /
ARKA). This script resolves by CODE + company rather than hardcoding ids, so it
stays correct if the CoA is reloaded. See the ``code_store`` caveat: in Odoo 19
``account.code`` is company-dependent, so the code must be read
``with_company`` (or out of ``code_store``) — a plain read returns blank for the
non-active company.

Related parties DP (``2108200001``) is deliberately NOT configured: Odoo holds
a single down-payment account per company, and third-party is the common case.
Intercompany DPs need a manual reclass — flag that to Accounting.

WHEN TO RUN
-----------
Once, on prd_arkaaim. Idempotent: re-running skips companies already correct.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < setup_downpayment_account.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
DP_ACCOUNT_CODE = "2108100001"  # Advances from customers - Third parties
EXPECTED_TYPE = "liability_current"
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Account = env["account.account"].sudo()
companies = env["res.company"].sudo().search([], order="id")

print("=" * 78)
print("Down-payment account setup — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("=" * 78)

changed = 0
for company in companies:
    current = company.downpayment_account_id

    # Resolve the account within this company's scope. `code` is
    # company-dependent in Odoo 19, so search with_company.
    account = Account.with_company(company).search(
        [("code", "=", DP_ACCOUNT_CODE), ("company_ids", "in", company.id)],
        limit=1,
    )

    if not account:
        print("SKIP  company %s (%s): account %s not found in its CoA" % (company.id, company.name, DP_ACCOUNT_CODE))
        continue

    if account.account_type != EXPECTED_TYPE:
        # Guard: a receivable/revenue account here would silently recreate the
        # very problem this script fixes, and a payable type would also drag in
        # the due-date rule.
        print(
            "SKIP  company %s (%s): account %s has type %r, expected %r"
            % (company.id, company.name, DP_ACCOUNT_CODE, account.account_type, EXPECTED_TYPE)
        )
        continue

    if current and current.id == account.id:
        print(
            "OK    company %s (%s): already set to %s (id %s)" % (company.id, company.name, DP_ACCOUNT_CODE, account.id)
        )
        continue

    was = ("%s (id %s)" % (current.code, current.id)) if current else "NOT SET"
    print(
        "SET   company %s (%s): %s -> %s (id %s, %s)"
        % (company.id, company.name, was, DP_ACCOUNT_CODE, account.id, account.account_type)
    )
    if COMMIT:
        company.downpayment_account_id = account.id
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
