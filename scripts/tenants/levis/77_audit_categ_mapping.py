# -*- coding: utf-8 -*-
"""Audit: does the general ledger still agree with the products' categories?

A ``product.category`` at Levi's is an account mapping — it decides which
``Gross Sales-<x>`` / ``Sales Discount-<x>`` / ``Sales Return-<x>`` account a
product's turnover lands on (see ``34_coa_categ_tree.py``). Put a product in the
wrong bucket and the revenue is misclassified; correct the category afterwards
and the ledger does **not** follow, because the POS closing entries are already
posted and carry no ``product_id`` at all.

This script is read-only. It recomputes, from ``pos.order.line`` and from any
posted move line that still names a product, what *should* be sitting on each
revenue account given the categories as they are today, and diffs that against
what really is. A non-zero difference means somebody's category moved after the
fact — repair it with the **Product Category Reclassification** screen
(``levis.categ.reclass``), which books the correction per day and per store and
respects the fiscal-year lock.

Run:

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
        < scripts/tenants/levis/77_audit_categ_mapping.py

Env:
    AUDIT_DATE_FROM / AUDIT_DATE_TO   ISO dates, default: everything
    AUDIT_CSV                         write the per-product detail to this path
"""

import csv
import os
from collections import defaultdict
from datetime import datetime, time

from odoo.fields import Date

DATE_FROM = os.environ.get("AUDIT_DATE_FROM") or ""
DATE_TO = os.environ.get("AUDIT_DATE_TO") or ""
CSV_PATH = os.environ.get("AUDIT_CSV") or ""

_SOLD_STATES = ("paid", "done", "invoiced")

company = env.company
Executor = env["retail.import.executor"]
discount_on = Executor._x24_discount_reclass_enabled()


def code(account):
    """account.code is company-dependent in Odoo 19 — read it in company context."""
    return account.with_company(company).code if account else "-"


def money(value):
    return "{:>18,.0f}".format(value)


print("=" * 96)
print("Category-mapping audit — %s" % env.cr.dbname)
print("company: %s | discount reclass: %s" % (company.display_name, "on" if discount_on else "off"))
print("period : %s .. %s" % (DATE_FROM or "(start)", DATE_TO or "(today)"))
print("=" * 96)

# ---------------------------------------------------------------------------
# 1. What the current categories say should have been posted
# ---------------------------------------------------------------------------
domain = [
    ("order_id.state", "in", _SOLD_STATES),
    ("order_id.company_id", "=", company.id),
    ("order_id.account_move", "=", False),
]
if DATE_FROM:
    domain.append(("order_id.date_order", ">=", datetime.combine(Date.to_date(DATE_FROM), time.min)))
if DATE_TO:
    domain.append(("order_id.date_order", "<=", datetime.combine(Date.to_date(DATE_TO), time.max)))

grouped = env["pos.order.line"]._read_group(
    domain,
    ["product_id", "ri_is_return"],
    ["price_subtotal:sum", "ri_src_discount:sum"],
)

expected = defaultdict(float)  # account -> signed balance
per_product = defaultdict(lambda: defaultdict(float))  # product -> account -> balance
first_sale = {}

for product, is_return, subtotal, discount in grouped:
    if not product:
        continue
    base = (
        Executor._ri_category_account(company, product, "return")
        if is_return
        else Executor._ri_income_account(company, product)
    )
    if base:
        expected[base] -= subtotal
        per_product[product][base] -= subtotal
    if discount_on and discount:
        income = Executor._ri_income_account(company, product)
        dacc = Executor._ri_category_account(company, product, "discount")
        if income and dacc:
            expected[income] -= discount
            expected[dacc] += discount
            per_product[product][income] -= discount
            per_product[product][dacc] += discount

# Posted move lines that still name a product (invoices, stock valuation). On
# prd_levis_begbal there are none, but other Levi's databases invoice POS orders.
gl_domain = [
    ("product_id", "!=", False),
    ("parent_state", "=", "posted"),
    ("company_id", "=", company.id),
    ("account_id.account_type", "in", ("income", "income_other")),
]
if DATE_FROM:
    gl_domain.append(("date", ">=", DATE_FROM))
if DATE_TO:
    gl_domain.append(("date", "<=", DATE_TO))
for line in env["account.move.line"].search(gl_domain):
    expected[line.account_id] += line.balance
    per_product[line.product_id][line.account_id] += line.balance

# ---------------------------------------------------------------------------
# 2. What is actually on the ledger
# ---------------------------------------------------------------------------
posted_domain = [
    ("parent_state", "=", "posted"),
    ("company_id", "=", company.id),
    ("account_id.account_type", "in", ("income", "income_other")),
    # ``66_reclass_sales_structure.py`` deliberately nets Sales Return into Gross
    # Sales per trading day. That is a presentation choice, not a category
    # mapping, so it is excluded here and reported on its own below — otherwise
    # it shows up forever as a difference nobody can fix.
    ("move_id.ref", "not like", "EBR-RECLASS%"),
]
if DATE_FROM:
    posted_domain.append(("date", ">=", DATE_FROM))
if DATE_TO:
    posted_domain.append(("date", "<=", DATE_TO))
posted = {
    account: balance
    for account, balance in env["account.move.line"]._read_group(posted_domain, ["account_id"], ["balance:sum"])
}

# Only accounts a product category can actually route to. Bank interest and the
# like are income too, but no category ever points at them, so leaving them in
# would report a permanent, meaningless difference.
mapped_accounts = set(expected)
for categ in env["product.category"].search([]).with_company(company):
    for field in (
        "property_account_income_categ_id",
        "property_account_sales_discount_categ_id",
        "property_account_sales_return_categ_id",
    ):
        if categ[field]:
            mapped_accounts.add(categ[field])
posted = {account: balance for account, balance in posted.items() if account in mapped_accounts}

# Reclass entries booked by hand (EBR-RECLASS-*) and by levis.categ.reclass move
# turnover between these accounts on purpose; report them so a difference that is
# explained by one is recognisable rather than alarming.
reclass_refs = env["account.move"].search(
    [("state", "=", "posted"), ("company_id", "=", company.id), ("ref", "like", "EBR-RECLASS%")]
)

print("\n1) REVENUE ACCOUNTS — expected (from today's categories) vs posted\n")
print("%-12s %-42s %18s %18s %18s" % ("CODE", "ACCOUNT", "EXPECTED", "POSTED", "DIFFERENCE"))
accounts = sorted(set(expected) | set(posted), key=lambda a: code(a))
clean = True
for account in accounts:
    exp = expected.get(account, 0.0)
    act = posted.get(account, 0.0)
    diff = act - exp
    if abs(diff) < 1:
        diff = 0.0
    else:
        clean = False
    print("%-12s %-42s %s %s %s" % (code(account), (account.name or "")[:42], money(exp), money(act), money(diff)))
print(
    "\n%s"
    % (
        "CLEAN — every revenue account matches its products' categories."
        if clean
        else "DIFFERENCES FOUND — see the suspect list below."
    )
)
if reclass_refs:
    print(
        "note: %s EBR-RECLASS entry/entries are excluded above (structural "
        "Sales Return -> Gross Sales netting from 66_reclass_sales_structure.py)." % len(reclass_refs)
    )

# ---------------------------------------------------------------------------
# 3. Suspect products
# ---------------------------------------------------------------------------
print("\n2) SUSPECT PRODUCTS\n")

# (a) category edited after the product had already been sold
env.cr.execute(
    """
    SELECT pl.product_id, MIN(po.date_order)
      FROM pos_order_line pl
      JOIN pos_order po ON po.id = pl.order_id
     WHERE po.company_id = %s
  GROUP BY pl.product_id
    """,
    (company.id,),
)
first_order_date = dict(env.cr.fetchall())

late_edits = []
for product in per_product:
    sold_at = first_order_date.get(product.id)
    if sold_at and product.product_tmpl_id.write_date and product.product_tmpl_id.write_date > sold_at:
        late_edits.append(product)

# (b) products parked halfway down the tree: a category that has children and is
#     not one of the COA root buckets. The real homes are the leaves.
non_leaf = [p for p in per_product if p.categ_id.parent_id and p.categ_id.child_id]

# (c) auto-registered non-merchandise products. Two different questions:
#     c1 — the product drifted away from what the config says it should be;
#     c2 — the config itself may be wrong. A ``TS…`` code is treated as tailoring
#          labour unless it is listed in ``x24_np_goods_codes``, but Levi's issues
#          TS codes to sold goods too (patches, buttons, pins). Only Finance can
#          say which is which, so these are listed for review, not flagged.
xids = env["ir.model.data"].search([("module", "=", "levis"), ("name", "like", "x24prod_%")])
np_products = env["product.product"].browse([x.res_id for x in xids if x.model == "product.product"]).exists()
np_strays, np_service = [], []
# A TS code that is not on the goods list resolves to the service bucket; use that
# as the yardstick instead of re-reading the parameters here.
service_home = Executor._x24_np_category("TS__AUDIT_PROBE")
for product in np_products:
    if product not in per_product:
        continue
    should_be = Executor._x24_np_category(product.default_code)
    if should_be and product.categ_id != should_be:
        np_strays.append(product)
        continue
    if should_be and should_be == service_home:
        np_service.append(product)

for title, bucket, cap in (
    (
        "edited after their first sale — WEAK signal, an X101 re-import touches "
        "write_date too; the account table above is the real verdict",
        late_edits,
        10,
    ),
    ("parked on a non-root category that has children", non_leaf, 25),
    ("auto-registered non-merchandise NOT in the category its config dictates", np_strays, 25),
    (
        "TS-coded items booked as tailoring labour — review: any that are really "
        "sold goods belong in retail_import.x24_np_goods_codes",
        np_service,
        25,
    ),
):
    print("-- %s: %d" % (title, len(bucket)))
    for product in sorted(bucket, key=lambda p: -abs(sum(per_product[p].values())))[:cap]:
        amounts = " ".join(
            "%s %s" % (code(acc), money(bal).strip()) for acc, bal in per_product[product].items() if abs(bal) >= 1
        )
        print(
            "   %-14s %-44s %-28s %s"
            % (
                product.default_code or "-",
                (product.display_name or "")[:44],
                product.categ_id.complete_name[:28],
                amounts,
            )
        )
    print("")

# ---------------------------------------------------------------------------
# 4. Inventory side, reported only
# ---------------------------------------------------------------------------
storable = [p for p in per_product if p.is_storable]
print("3) INVENTORY SIDE — %d storable product(s) with turnover in the window." % len(storable))
print("   Changing their category also moves COGS-<x> and Inventories-<x>; the")
print("   reclassification screen books those legs too, but any levis.cogs.run")
print("   already posted aggregates per category and has to be reviewed by hand.")
runs = env["levis.cogs.run"].search([("company_id", "=", company.id), ("state", "=", "generated")])
if runs:
    print("   posted COGS runs: %s" % ", ".join(runs.mapped("name")))

# ---------------------------------------------------------------------------
# 5. CSV detail
# ---------------------------------------------------------------------------
if CSV_PATH:
    with open(CSV_PATH, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["default_code", "product", "category", "account_code", "account", "balance"])
        for product, by_account in per_product.items():
            for account, balance in by_account.items():
                if abs(balance) < 1:
                    continue
                writer.writerow(
                    [
                        product.default_code or "",
                        product.display_name,
                        product.categ_id.complete_name,
                        code(account),
                        account.name,
                        round(balance, 2),
                    ]
                )
    print("\nCSV written to %s" % CSV_PATH)

print("\nDone. Nothing was written to the database.")
