# -*- coding: utf-8 -*-
"""Turn on the goods-receipt (GR/IR) journal for the ARKA-AIM tenant.

WHAT IT SWITCHES ON
-------------------
``custom_arka_aim_purchase_type`` 19.0.1.1.0 books the accrual at receipt::

    Goods receipt   Dr Stock Valuation        Cr GR/IR clearing
    Vendor bill     Dr GR/IR clearing         Cr Accounts Payable

The code posts only for a product category that is **real-time** valued and only
when the stream's GR/IR account, the category's valuation account and a stock
journal are all configured. This script is that configuration; without it the
module stays inert and receipts keep booking nothing, exactly as today.

WHAT IT WRITES
--------------
Per ARKA-AIM company (``x_doc_code`` set), for each category in ``CATEGORIES``:

* ``property_valuation``                    -> ``real_time``
* ``property_stock_valuation_account_id``   -> ``INVENTORY_CODES`` of that company
  (on AIM this replaces ``110100 Stock Valuation``, a leftover of the generic
  CoA template that is not part of the Erajaya chart the tenant actually uses,
  and which no entry has ever been booked to)
* ``property_stock_journal``                -> the company's ``STJ`` journal
* ``res.company.account_stock_journal_id``  -> the same journal, when empty

and once for the database, ``ir.config_parameter``
``custom_arka_aim_purchase_type.suppress_gr_journal`` -> ``"0"`` (post).

All four category fields are company-dependent in Odoo 19, so every read and
write goes through ``with_company`` -- writing them from the wrong company
context silently stores the value under the wrong key.

WHICH CATEGORIES, AND WHY NOT THE OTHERS
----------------------------------------
What ARKA-AIM actually receives on a PO is drone-show operating cost -- Legal &
Compliance, Accommodation, Logistics, Documentation, Consumption -- carried on
``consu`` products in **Goods**, plus venue/supporting tools in **Services /
Exhibition** received through ``custom_service_receipt``. **Expenses** carries no
receipt yet and is included so it behaves the same the day it does.

**Fixed Assets (Non-Valuated)** is deliberately left periodic. The drones in it
are capitalised through the fixed-asset register from the receipt and the bill;
raising an inventory accrual for them as well would book their value twice.
**Drone Unit** on trn_arkaaim is the same category under another name and is left
out for the same reason -- it holds that database's largest receipts
(Rp 10,68 M), so switching it on is the one change here that would really move
the books. **Drone Sparepart** IS switched on: spare parts are ordinary stock.
Plain **Services** stays periodic on both.

COST METHOD IS NOT TOUCHED
--------------------------
An incoming move is valued at the purchase price by ``purchase_stock``, whatever
the cost method -- verified on the 39 receipts already booked, where
``stock_move.value`` equals the PO line subtotal to the rupiah. Leaving the
method alone keeps outgoing valuation exactly as it is today.

NOT RETROACTIVE
---------------
Only receipts validated **after** this runs raise an accrual. The 39 already-done
receipts (Rp 910.200.000) are left alone: their bills have posted or will post to
expense the old way, and back-dating an accrual into a reported period would
change a closed month for no gain.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < enable_gr_journal.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
# Category names across BOTH ARKA-AIM charts; one that is not in this database is
# reported and skipped, so the same script serves prd and trn.
CATEGORIES = (
    "Goods",  # both
    "Expenses",  # both
    "Services / Exhibition",  # prd_arkaaim (a child of "Services")
    "Drone Sparepart",  # trn_arkaaim
)
# Inventory account codes, tried in order -- first one in the company's chart
# wins. prd_arkaaim runs the Erajaya chart, trn_arkaaim the plain Indonesian one.
INVENTORY_CODES = ("1113100099", "11300180")
JOURNAL_CODE = "STJ"  # Inventory Valuation
PARAM_KEY = "custom_arka_aim_purchase_type.suppress_gr_journal"
PARAM_VALUE = "0"  # "0" = post the GR journal, "1" = periodic
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Account = env["account.account"].sudo()
Journal = env["account.journal"].sudo()
Category = env["product.category"].sudo()
AccountMap = env["arka.purchase.account.map"].sudo()

print("=" * 92)
print("ARKA-AIM GR/IR journal — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 92)

companies = env["res.company"].sudo().search([("x_doc_code", "!=", False)], order="id")
if not companies:
    print("!! no company carries x_doc_code — this is not an ARKA-AIM database. Nothing done.")

changed = 0
blocked = []

for company in companies:
    print("\n--- company %s — %s" % (company.id, company.name))

    inventory = Account.browse()
    for code in INVENTORY_CODES:
        inventory = Account.with_company(company).search(
            [("code", "=", code), ("company_ids", "in", company.id)], limit=1
        )
        if inventory:
            break
    journal = Journal.search([("code", "=", JOURNAL_CODE), ("company_id", "=", company.id)], limit=1)
    if not inventory:
        blocked.append("company %s: none of %s in its chart" % (company.id, ", ".join(INVENTORY_CODES)))
        print("    !! no inventory account (%s) — company skipped" % ", ".join(INVENTORY_CODES))
        continue
    if not journal:
        blocked.append("company %s: no %s journal" % (company.id, JOURNAL_CODE))
        print("    !! journal %s NOT FOUND — company skipped" % JOURNAL_CODE)
        continue
    print("    inventory account : %s %s (id=%s)" % (inventory.code, inventory.name, inventory.id))
    print("    stock journal     : %s %s (id=%s)" % (journal.code, journal.name, journal.id))

    # The receipt credits the stream's GR/IR account; without it nothing posts.
    for ptype in ("trade", "non_trade"):
        grir = AccountMap._grir_account(company, ptype)
        if grir:
            print("    GR/IR %-9s : %s %s" % (ptype, grir.with_company(company).code, grir.name))
        else:
            blocked.append("company %s: no GR/IR account mapped for %s" % (company.id, ptype))
            print("    !! GR/IR %-9s : NOT MAPPED — receipts of this stream will book nothing" % ptype)

    if not company.account_stock_journal_id:
        print("    company.account_stock_journal_id: (empty) -> %s" % journal.code)
        if COMMIT:
            company.account_stock_journal_id = journal.id
        changed += 1

    for name in CATEGORIES:
        # Matched on complete_name: "Services / Exhibition" is a CHILD category
        # whose own name is just "Exhibition", and matching on name alone
        # silently skipped it.
        categ = Category.search([("complete_name", "=", name)], limit=1) or Category.search(
            [("name", "=", name)], limit=1
        )
        if not categ:
            # Expected: the two charts do not carry the same category names.
            print("    - %-24s not in this database" % name)
            continue
        categ = categ.with_company(company)
        before = (
            categ.property_valuation,
            categ.property_stock_valuation_account_id.id,
            categ.property_stock_journal.id,
        )
        after = ("real_time", inventory.id, journal.id)
        if before == after:
            print("    = %-24s already configured" % name)
            continue
        print(
            "    ~ %-24s valuation %s -> real_time | valuation acct %s -> %s | journal %s -> %s"
            % (name, before[0] or "(unset)", before[1] or "-", after[1], before[2] or "-", after[2])
        )
        if COMMIT:
            categ.write(
                {
                    "property_valuation": "real_time",
                    "property_stock_valuation_account_id": inventory.id,
                    "property_stock_journal": journal.id,
                }
            )
        changed += 1

param = env["ir.config_parameter"].sudo()
current = param.get_param(PARAM_KEY, "(unset)")
print("\n--- switch")
print("    %s: %s -> %s" % (PARAM_KEY, current, PARAM_VALUE))
if current != PARAM_VALUE:
    if COMMIT:
        param.set_param(PARAM_KEY, PARAM_VALUE)
    changed += 1

print("\n" + "=" * 92)
print("%s change(s) %s" % (changed, "written" if COMMIT else "pending — set COMMIT = True to apply"))
for note in blocked:
    print("  !! %s" % note)
print("=" * 92)

if COMMIT:
    env.cr.commit()
