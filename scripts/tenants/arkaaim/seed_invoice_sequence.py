# -*- coding: utf-8 -*-
"""Seed the ARKA customer-invoice numbering onto the INV/<CODE>/YYYY/MM/NNN format.

WHY THIS IS NEEDED
------------------
Odoo customer-invoice numbers are NOT drawn from an ir.sequence; account.move
uses the ``sequence.mixin``, which derives each new number from the previous
posted move's name in the same (journal, prefix) chain. ``custom_arka_aim_numbering``
overrides ``_get_starting_sequence`` to start FRESH chains at
``INV/<CODE>/YYYY/MM/000``, but a journal that already has posted invoices in an
older pattern (e.g. ARKA's ``INV/2026/00001`` annual chain) keeps continuing
that old chain — the override is never consulted. To switch such a journal you
seed the new pattern ONCE, on the first invoice of a clean month, by setting its
name explicitly while it is still a draft. Odoo then continues monthly from
there (``INV/<CODE>/YYYY/MM/001``, ``/002`` ...), resetting each month.

WHEN TO RUN
-----------
At the start of the month you want the new format to take effect, BEFORE posting
that month's first ARKA customer invoice, and ideally when that journal has no
other posted invoice yet in that month. Run interactively so you can eyeball the
target before committing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < seed_invoice_sequence.py

By default it operates on company code 'ARKA' for the CURRENT month and only
PREVIEWS (no commit). Set SEED_COMMIT = True to actually write. Adjust
SEED_CODE / SEED_YEAR / SEED_MONTH / SEED_MOVE_ID as needed.
"""

# ----- knobs -------------------------------------------------------------
SEED_CODE = "ARKA"  # res.company.x_doc_code to seed
SEED_YEAR = None  # int year, or None = current month's year
SEED_MONTH = None  # int month, or None = current month
SEED_MOVE_ID = None  # specific draft out_invoice id, or None = auto-pick earliest draft in the period
SEED_COMMIT = False  # True to persist; False = preview only
# -------------------------------------------------------------------------

from datetime import date  # noqa: E402

env = self.env  # noqa: F821  (provided by odoo shell)

company = env["res.company"].search([("x_doc_code", "=", SEED_CODE)], limit=1)
assert company, "No company with x_doc_code=%r" % SEED_CODE

today = date.today()
year = SEED_YEAR or today.year
month = SEED_MONTH or today.month
seed_name = "INV/%s/%04d/%02d/001" % (SEED_CODE, year, month)

journals = env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)])
period_start = date(year, month, 1)
period_end = date(year + (month // 12), (month % 12) + 1, 1)

Move = env["account.move"]
if SEED_MOVE_ID:
    target = Move.browse(SEED_MOVE_ID)
else:
    target = Move.search(
        [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "draft"),
            ("company_id", "=", company.id),
            ("journal_id", "in", journals.ids),
            ("invoice_date", ">=", period_start),
            ("invoice_date", "<", period_end),
        ],
        order="invoice_date, id",
        limit=1,
    )

# Safety: warn if the journal already has a posted invoice this month (the seed
# would create a parallel chain / out-of-order number).
already = Move.search_count(
    [
        ("move_type", "=", "out_invoice"),
        ("state", "=", "posted"),
        ("company_id", "=", company.id),
        ("journal_id", "in", journals.ids),
        ("invoice_date", ">=", period_start),
        ("invoice_date", "<", period_end),
    ]
)

print("Company        :", company.name, "(%s)" % SEED_CODE)
print("Target period  :", "%04d-%02d" % (year, month))
print("Seed name      :", seed_name)
print("Posted already :", already, "customer invoice(s) this month (want 0)")
if not target:
    print(
        "RESULT: no DRAFT customer invoice found in the period. Create the first "
        "invoice as a draft, then re-run (or set SEED_MOVE_ID)."
    )
else:
    print("Target move    : id=%s current name=%r date=%s" % (target.id, target.name, target.invoice_date))
    if target.name and target.name.startswith("INV/%s/" % SEED_CODE):
        print("RESULT: target already carries the new format; nothing to do.")
    elif SEED_COMMIT:
        target.name = seed_name
        env.cr.commit()
        print(
            "RESULT: COMMITTED. Set move %s name -> %s. Post it; later invoices "
            "will continue %s/.../NNN monthly." % (target.id, seed_name, "INV/%s/%04d/%02d" % (SEED_CODE, year, month))
        )
    else:
        print("RESULT: PREVIEW ONLY. Set SEED_COMMIT = True to write name=%r onto move %s." % (seed_name, target.id))
