# -*- coding: utf-8 -*-
"""Make the products that cross between ARKA and AIM company-neutral.

Why
---
``custom_intercompany_procurement`` mirrors a confirmed purchase order into a
sales order in the SISTER company. A product whose ``company_id`` is locked to
the buying company cannot appear on that order — Odoo rejects it as a company
crossover — and the mirror module catches the error, logs it and posts to
chatter, so the buyer never sees it fail. In prd_arkaaim only 4 of 12 purchase
orders had ever produced a mirror, and all four happened to use a product with
no company.

What it changes
---------------
1. Every ``product.template`` that is scoped to a company AND already appears on
   a sale or purchase order line gets ``company_id = False``. Those are, by
   definition, products the two companies trade in. Equipment that only ever
   sits in one company's stock is left alone: it is never on an order line.
2. A template with the SAME NAME as one of those, with no usage anywhere
   (orders, journal items, stock moves), is archived — the second copy is what
   makes an operator pick the wrong one. Only ever archives an unused record.

Idempotent: running it twice finds nothing to do the second time.

Usage
-----
    odoo shell -d <db> ... < 01_share_intercompany_products.py          # apply
    APPLY=0 odoo shell -d <db> ... < 01_share_intercompany_products.py  # plan only
"""

import os

APPLY = os.environ.get("APPLY", "1") != "0"

Template = env["product.template"].sudo()


def usage(template):
    """Every place a product template leaves a trace."""
    product_ids = template.product_variant_ids.ids
    if not product_ids:
        return 0
    return sum(
        env[model].sudo().search_count([("product_id", "in", product_ids)])
        for model in ("sale.order.line", "purchase.order.line", "account.move.line", "stock.move")
    )


def ordered(template):
    product_ids = template.product_variant_ids.ids
    if not product_ids:
        return 0
    return env["sale.order.line"].sudo().search_count([("product_id", "in", product_ids)]) + env[
        "purchase.order.line"
    ].sudo().search_count([("product_id", "in", product_ids)])


scoped = Template.with_context(active_test=False).search([("company_id", "!=", False)])
to_share = scoped.filtered(ordered)

print("=" * 78)
print("Products locked to one company but traded on orders — to be made shared:")
for template in to_share:
    print(
        "  #%-5s %-46s company=%s order_lines=%s"
        % (template.id, template.display_name[:46], template.company_id.display_name, ordered(template))
    )
if not to_share:
    print("  (none — nothing to do)")

# Duplicates of those names that nobody has ever used.
to_archive = Template.browse()
for template in to_share:
    twins = Template.search([("name", "=", template.name), ("id", "!=", template.id)])
    for twin in twins:
        if usage(twin) == 0:
            to_archive |= twin

print("")
print("Unused same-name duplicates — to be archived:")
for template in to_archive:
    print(
        "  #%-5s %-46s company=%s" % (template.id, template.display_name[:46], template.company_id.display_name or "-")
    )
if not to_archive:
    print("  (none)")
print("=" * 78)

if not APPLY:
    print("PLAN ONLY — nothing written (APPLY=0)")
else:
    if to_share:
        to_share.write({"company_id": False})
    if to_archive:
        to_archive.write({"active": False})
    env.cr.commit()
    print("APPLIED: %s product(s) shared, %s duplicate(s) archived" % (len(to_share), len(to_archive)))

    leftovers = Template.with_context(active_test=False).search([("company_id", "!=", False)]).filtered(ordered)
    print("VERIFY: company-scoped products still on order lines:", leftovers.ids or "none")
