# -*- coding: utf-8 -*-
"""Give every product a category, so sales invoices stop landing on an archived account.

WHY THIS IS NEEDED
------------------
On prd_arkaaim, customer invoices of company 1 (PT Aero Inovasi Media) book to
``400000 Product Sales`` — an account that was ARCHIVED when the PSAK chart
replaced the generic one. That is fatal, not cosmetic: core refuses every write
to such a move ("The account Product Sales (400000) is archived."), so the
invoice can neither be posted nor even edited. It surfaced on the draft invoice
of SO/AIM/2026/09/001 and would have hit SO/AIM/2026/09/002 next.

The cause is NOT the categories. Company 1's ``ir.default`` already supplies
``property_account_income_categ_id`` = 5199000000 "Gross Sales-Others", and every
category resolves to it correctly. The cause is that 30 product templates have
``categ_id`` **NULL**, so::

    product_template._get_product_accounts()
        -> self.property_account_income_id or self.categ_id.property_account_income_categ_id

has nothing on either side — no template account, and no category to ask — and
the line falls through to the stale generic account. Product 8 "Sewa Drone Unit"
is the counter-example that proves it: same NULL category, but an explicit
template income account, and it resolves correctly.

WHAT THIS SETS
--------------
1. A category for every template that has none, by the product's own type:
   ``service`` -> "Services", ``consu`` -> "Goods". Both resolve to the same
   income account per company, so this is an accounting no-op — it exists only
   to give ``_get_product_accounts`` something to read. Category valuation is
   ``periodic`` on this DB, so attaching a category posts no stock entries.

2. An explicit income account on the drone RENTAL templates, which are the ones
   actually sold by company 1. They book to 5122000000 "Gross Sales-Rental
   Asset" — the account Accounting confirmed for invoice 277, the one the Sales
   journal already defaults to, and the same account the pre-existing template
   ``Sewa Drone Unit`` (id 8) carries. Everything else keeps the generic
   5199000000 it inherits from its category.

NOT DONE HERE
-------------
Company 1's ``6122000000`` (id 359) and ``6199000000`` (id 360) are typed
``income`` while company 2's equivalents are ``expense_direct_cost``. The
company-1 ``ir.default`` for ``property_account_expense_categ_id`` therefore
points COGS at an income-typed account. That is a real CoA defect but a separate
one, and correcting an account type touches existing balances — flag it to
Accounting rather than fixing it here.

WHEN TO RUN
-----------
Once on prd_arkaaim. Idempotent: a second run prints only OK lines.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < fix_product_income_accounts.py

PREVIEW still applies the changes and runs the end-to-end check below, then
rolls everything back — so the evidence is real. Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
CATEGORY_BY_TYPE = {"service": "Services", "consu": "Goods"}
RENTAL_INCOME_CODE = "5122000000"  # Gross Sales-Rental Asset
# Templates sold as drone rental by company 1. Matched by id AND name so a
# renumbered DB fails loudly instead of repointing the wrong product.
RENTAL_TEMPLATES = {
    154: "Sewa Drone Show 250 Unit",
    155: "Sewa Drone Show 1500 Unit",
    157: "Sewa Drone 1000 Unit",
}
VERIFY_COMPANY_ID = 1
VERIFY_SALE_ORDER = 16  # SO/AIM/2026/09/002 — the next order due to be invoiced
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Template = env["product.template"].sudo()
Category = env["product.category"].sudo()
Account = env["account.account"].sudo()

company = env["res.company"].sudo().browse(VERIFY_COMPANY_ID)

print("=" * 78)
print("Product income-account wiring — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("=" * 78)

failures = []
changed = 0

# --------------------------------------------------------------- step 1 ---
print("\n--- 1. Templates without a category " + "-" * 42)
categories = {}
for ptype, catname in CATEGORY_BY_TYPE.items():
    cat = Category.search([("name", "=", catname), ("parent_id", "=", False)], limit=1)
    if not cat:
        failures.append("product category %r not found" % catname)
        print("FAIL  product category %r not found" % catname)
    categories[ptype] = cat

orphans = Template.with_context(active_test=False).search([("categ_id", "=", False)], order="id")
if not orphans:
    print("OK    every template already has a category")
for tmpl in orphans:
    cat = categories.get(tmpl.type)
    if not cat:
        msg = "template %s (%s) has type %r with no mapped category" % (tmpl.id, tmpl.name, tmpl.type)
        print("FAIL  %s" % msg)
        failures.append(msg)
        continue
    print("SET   template %-4s %-45s type=%-8s -> %s" % (tmpl.id, tmpl.name, tmpl.type, cat.name))
    tmpl.categ_id = cat.id
    changed += 1

# --------------------------------------------------------------- step 2 ---
print("\n--- 2. Rental templates: explicit income account " + "-" * 29)
income = Account.with_company(company).search([("code", "=", RENTAL_INCOME_CODE)], limit=1)
if not income:
    failures.append("account %s not found in company %s" % (RENTAL_INCOME_CODE, company.id))
    print("FAIL  account %s not found in company %s" % (RENTAL_INCOME_CODE, company.id))
elif not income.active:
    failures.append("account %s is archived" % RENTAL_INCOME_CODE)
    print("FAIL  account %s is archived" % RENTAL_INCOME_CODE)
else:
    for tid, expected_name in RENTAL_TEMPLATES.items():
        tmpl = Template.with_company(company).browse(tid)
        if not tmpl.exists():
            msg = "rental template id %s does not exist" % tid
            print("FAIL  %s" % msg)
            failures.append(msg)
            continue
        if tmpl.name != expected_name:
            msg = (
                "rental template id %s is %r, expected %r — refusing to repoint "
                "a product that is not the one this script was written for" % (tid, tmpl.name, expected_name)
            )
            print("FAIL  %s" % msg)
            failures.append(msg)
            continue
        if tmpl.property_account_income_id == income:
            print("OK    template %-4s %-30s already on %s" % (tid, tmpl.name, income.code))
            continue
        print(
            "SET   template %-4s %-30s income %s -> %s (%s)"
            % (
                tid,
                tmpl.name,
                tmpl.property_account_income_id.code or "(from category)",
                income.code,
                income.display_name,
            )
        )
        tmpl.property_account_income_id = income.id
        changed += 1

env.cr.flush()
env.invalidate_all()

# --------------------------------------------------------------- step 3 ---
# Prove it end to end rather than trusting the writes: resolve the account the
# way core does, then actually build an invoice off a real order and post it.
print("\n--- 3. Verification " + "-" * 58)
for tid in sorted(RENTAL_TEMPLATES):
    tmpl = Template.with_company(company).browse(tid)
    resolved = tmpl._get_product_accounts().get("income")
    ok = bool(resolved) and resolved.active
    print(
        "%-5s template %-4s %-30s -> %s (active=%s)"
        % (
            "OK" if ok else "FAIL",
            tid,
            tmpl.name,
            resolved.display_name if resolved else "NONE",
            resolved.active if resolved else "-",
        )
    )
    if not ok:
        failures.append("template %s still resolves to %s" % (tid, resolved.code if resolved else "NONE"))

still_null = Template.with_context(active_test=False).search_count([("categ_id", "=", False)])
print("%-5s templates still without a category: %d" % ("OK" if not still_null else "FAIL", still_null))
if still_null:
    failures.append("%d template(s) still have no category" % still_null)

order = env["sale.order"].sudo().browse(VERIFY_SALE_ORDER)
if order.exists() and order.invoice_status == "to invoice":
    invoice = order._create_invoices()
    for line in invoice.invoice_line_ids:
        print(
            "      invoice line %-30s -> %s (active=%s)"
            % (line.product_id.name, line.account_id.display_name, line.account_id.active)
        )
    try:
        invoice.action_post()
        print("OK    test invoice posts: %s %s %s" % (invoice.name, invoice.currency_id.name, invoice.amount_total))
    except Exception as exc:  # noqa: BLE001 - the whole point is to surface it
        print("FAIL  test invoice will not post: %s" % exc)
        failures.append("test invoice will not post: %s" % exc)
    # The test invoice is never kept: it is undone here so COMMIT persists only
    # the configuration above, and the client still presses Create Invoice
    # themselves when they are ready.
    invoice.button_draft()
    invoice.unlink()
    print("      test invoice discarded (only the configuration is kept)")
else:
    print("      SO %s not invoiceable — end-to-end check skipped" % VERIFY_SALE_ORDER)

print("\n" + "-" * 78)
print("%d record(s) %s" % (changed, "updated" if COMMIT else "would change"))

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if failures:
    print("!! %d FAILURE(S) — rolling back, nothing persisted:" % len(failures))
    for f in failures:
        print("   - %s" % f)
    env.cr.rollback()
    print("ROLLED BACK.")
elif COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
