# -*- coding: utf-8 -*-
"""Fill the pemotong identity the Coretax export wizards require (sheet item #2).

WHY THIS IS NEEDED
------------------
``custom_coretax_export`` refuses to render a workbook until the withholding
agent is fully identified (``res.company._check_coretax_pemotong``). On
prd_arkaaim both companies carry their NPWP in the standard ``res.partner.vat``
field, but ``custom_tax_id`` reads its own ``x_custom_npwp`` — which was never
populated — so every template raised "Identitas pemotong belum lengkap".

Step 1 backfills ``x_custom_npwp`` from ``vat`` for every partner that has one
and not the other (the two fields are deliberately separate in ``custom_tax_id``;
this only copies, never overwrites).

Steps 2 and 3 write values that CANNOT be derived from the database — the
signer's NPWP and the Coretax User Id must come from the tax team. Leave them
empty and the script will just report them as still missing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < setup_coretax_identity.py

Defaults to PREVIEW. Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = True

# company name -> {signer NPWP (15/16 digits), Coretax User Id, NITKU suffix}
# Supplied by the tax team (Arman). Leave a value empty to skip writing it.
IDENTITY = {
    "PT Aero Inovasi Media": {
        "x_custom_npwp_penandatangan": "",
        "x_custom_coretax_user_id": "",
        "x_custom_nitku_suffix": "000000",
    },
    "PT Aero Reksa Kreasi Angkasa": {
        "x_custom_npwp_penandatangan": "",
        "x_custom_coretax_user_id": "",
        "x_custom_nitku_suffix": "000000",
    },
}
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

print("=" * 78)
print("Coretax pemotong identity — %s" % ("COMMIT" if COMMIT else "PREVIEW ONLY"))
print("=" * 78)

# --- 1. backfill x_custom_npwp from vat ----------------------------------
print("\n[1] Partners with vat but no x_custom_npwp")
partners = env["res.partner"].sudo().search([("vat", "!=", False), ("x_custom_npwp", "in", (False, ""))])
for partner in partners:
    print("    id %-5s %-40s %s" % (partner.id, partner.display_name[:40], partner.vat))
    if COMMIT:
        partner.x_custom_npwp = partner.vat
print("    total: %s" % len(partners))

# --- 2. company-level identity -------------------------------------------
print("\n[2] Company identity")
for name, values in IDENTITY.items():
    company = env["res.company"].sudo().search([("name", "=", name)], limit=1)
    if not company:
        print("    NOT FOUND  %s" % name)
        continue
    to_write = {k: v for k, v in values.items() if v}
    if to_write and COMMIT:
        company.write(to_write)
    print("    %-30s %s" % (name, to_write or "(nothing supplied)"))

# --- 3. verdict ----------------------------------------------------------
print("\n[3] Can each company export now?")
for name in IDENTITY:
    company = env["res.company"].sudo().search([("name", "=", name)], limit=1)
    if not company:
        continue
    try:
        npwp = company._check_coretax_pemotong()
        print("    %-30s READY (NPWP %s)" % (name, npwp))
    except Exception as exc:  # ValidationError carries the missing-field list
        detail = str(exc).replace("\n", " ").replace("  ", " ")
        print("    %-30s BLOCKED: %s" % (name, detail[:120]))

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPreview only — nothing written. Set COMMIT = True to apply.")
