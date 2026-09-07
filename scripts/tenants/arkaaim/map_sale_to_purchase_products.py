# -*- coding: utf-8 -*-
"""Pair each "Jasa …" product ARKA sells with the "Sewa …" product it buys.

Why
---
"Buat PO ke Sister Company" copies the sale lines, and the client's own
catalogue splits the two sides of one show::

    Jasa Drone Show 250 Unit   sold to the customer
    Sewa Drone Show 250 Unit   bought from AIM

``product.template.x_custom_ic_purchase_product_id`` records the pairing so the
generated purchase order carries what is actually bought. This script fills it
in from the names already in the database.

How the pairing is decided
--------------------------
On the **number** in the name, not on the words around it — the client writes
the rental side three different ways ("Sewa Drone Show 1500 Unit", "Sewa Drone
1000 Unit", "Sewa Drone 500 Unit"), and only the count is stable. A "Jasa"
product is paired with a "Sewa" product when exactly ONE active "Sewa" product
carries the same number.

It refuses to guess: a "Jasa" product with no number, with no "Sewa"
counterpart, or with more than one candidate is listed and left alone, for
someone who knows the catalogue to set by hand on the product form. Existing
pairings are never overwritten.

Idempotent.

Usage
-----
    odoo shell -d <db> ... < map_sale_to_purchase_products.py          # apply
    APPLY=0 odoo shell -d <db> ... < map_sale_to_purchase_products.py  # plan only
"""

import os
import re

APPLY = os.environ.get("APPLY", "1") != "0"

Template = env["product.template"].sudo()


def number_in(name):
    """The unit count in a product name, or None. "1.000" and "1,000" count."""
    found = re.findall(r"\d[\d.,]*", name or "")
    if not found:
        return None
    return int(re.sub(r"[.,]", "", found[0]))


sold = Template.search([("name", "=ilike", "Jasa%"), ("sale_ok", "=", True)])
bought = Template.search([("name", "=ilike", "Sewa%"), ("purchase_ok", "=", True)])

by_number = {}
for template in bought:
    number = number_in(template.name)
    if number is not None:
        by_number[number] = by_number.get(number, Template.browse()) | template

planned = []
skipped = []
for template in sold:
    if template.x_custom_ic_purchase_product_id:
        skipped.append((template, "already paired with %s" % template.x_custom_ic_purchase_product_id.display_name))
        continue
    number = number_in(template.name)
    if number is None:
        skipped.append((template, "no unit count in the name"))
        continue
    candidates = by_number.get(number, Template.browse())
    if not candidates:
        skipped.append((template, "no 'Sewa' product with %s units" % number))
        continue
    if len(candidates) > 1:
        skipped.append((template, "ambiguous: %s" % ", ".join(candidates.mapped("display_name"))))
        continue
    planned.append((template, candidates.product_variant_id))

print("=" * 78)
print("Pairings to write:")
for template, substitute in planned:
    print("  #%-5s %-34s ->  #%-5s %s" % (template.id, template.name[:34], substitute.id, substitute.display_name))
if not planned:
    print("  (none)")

print("")
print("Left for a human to decide:")
for template, why in skipped:
    print("  #%-5s %-34s  — %s" % (template.id, template.name[:34], why))
if not skipped:
    print("  (none)")
print("=" * 78)

if not APPLY:
    print("PLAN ONLY — nothing written (APPLY=0)")
else:
    for template, substitute in planned:
        template.x_custom_ic_purchase_product_id = substitute
    env.cr.commit()
    print("APPLIED: %s pairing(s) written" % len(planned))
    for template in Template.search([("x_custom_ic_purchase_product_id", "!=", False)]):
        print("VERIFY %-38s -> %s" % (template.name[:38], template.x_custom_ic_purchase_product_id.display_name))
