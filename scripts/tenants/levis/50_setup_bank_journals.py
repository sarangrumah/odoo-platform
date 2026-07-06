"""Provision the Levi's bank journals on an EXISTING DB (feedback Finance-AP #4/#6/#7).

`custom_levis_localization`'s ``post_init_hook`` only runs on a fresh install, so
already-installed DBs (rnd_levis / prd_levis / prd_detail_levis) are seeded with
this script. Idempotent — safe to re-run.

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis \
        --no-http < scripts/tenants/levis/50_setup_bank_journals.py

Creates, per company that has stores, resolving accounts by EBR code:
  * one BANK-OUT journal (BCA 2687778282) — vendor payments post DIRECT to the
    bank GL account (no outstanding suspense);
  * one BANK-IN journal per rekening (BCA 2685151268, Mandiri, BNI, BRI) — receipts
    land in the per-bank IC clearing (suspense) account;
  * CHECK / GIRO / BANK TRANSFER payment methods on each journal.

Payment numbering (<last-4 of rekening>/YYYY/MM/###) is applied automatically by
account.move._compute_name once a bank journal carries a bank account.
"""

import sys

from odoo.addons.custom_levis_localization.models.setup import seed_bank_journals

res = seed_bank_journals(env)  # noqa: F821  (env injected by `odoo shell`)
env.cr.commit()  # noqa: F821
sys.stderr.write("Bank journals seeding done: %s\n" % (res,))
sys.stderr.flush()
