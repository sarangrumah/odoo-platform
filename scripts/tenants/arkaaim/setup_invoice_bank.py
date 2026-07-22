# -*- coding: utf-8 -*-
"""Print the bank account (and the product name) on ARKA-AIM invoices.

Covers sheet items #4 ("Menampilkan Nomor Rekening di Invoice") and #5 ("nama
produk harus ikut sampai ke invoice").

WHAT IT DOES
------------
1. Creates the ``res.partner.bank`` records for each company's own partner and
   attaches them to the bank/sale journals. ``custom_report_templates``'s
   invoice template prints ``o.partner_bank_id`` (bank, A/C, holder) when the
   invoice nominates one — that is how the number can differ per invoice, which
   is what Nuri asked about.
2. Fills ``res.company.report_bank_details``, the free-text fallback printed in
   the OTHER COMMENTS box when an invoice nominates no bank account.
3. Ticks ``res.company.report_show_product_name`` so every document line prints
   the product name above its description, even when a user overwrote that
   description with free text.

The account numbers are client data — fill ``BANKS`` before running. Step 3
needs no input and is applied on its own if ``BANKS`` is left empty.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < setup_invoice_bank.py

Defaults to PREVIEW. Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = True

# company name -> list of bank accounts to publish on its invoices.
#   acc_number       : rekening number as it should be printed
#   bank             : bank name (a res.bank is created if missing)
#   acc_holder_name  : "atas nama", printed under the number
#   journals         : journal names to attach this account to (optional)
BANKS = {
    # "PT Aero Reksa Kreasi Angkasa": [
    #     {
    #         "acc_number": "",
    #         "bank": "Bank Central Asia (BCA)",
    #         "acc_holder_name": "PT Aero Reksa Kreasi Angkasa",
    #         "journals": ["Bank"],
    #     },
    # ],
}

# company name -> free text for the OTHER COMMENTS box (fallback).
BANK_DETAILS = {
    # "PT Aero Reksa Kreasi Angkasa": (
    #     "Pembayaran ditransfer ke:\n"
    #     "Bank Central Asia (BCA)\n"
    #     "A/C: 000-000-0000 a.n. PT Aero Reksa Kreasi Angkasa\n"
    #     "NPWP: 10.1555.666.7-008.000"
    # ),
}

SHOW_PRODUCT_NAME = True  # step 3 — no client input needed
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

print("=" * 78)
print("ARKA-AIM invoice bank / product name — %s" % ("COMMIT" if COMMIT else "PREVIEW ONLY"))
print("=" * 78)


def _company(name):
    return env["res.company"].sudo().search([("name", "=", name)], limit=1)


# --- 1. bank accounts ----------------------------------------------------
print("\n[1] Bank accounts")
if not BANKS:
    print("    (no account numbers supplied — skipped)")
for name, accounts in BANKS.items():
    company = _company(name)
    if not company:
        print("    NOT FOUND  %s" % name)
        continue
    for spec in accounts:
        bank = env["res.bank"].sudo().search([("name", "=", spec["bank"])], limit=1)
        if not bank and COMMIT:
            bank = env["res.bank"].sudo().create({"name": spec["bank"]})
        existing = (
            env["res.partner.bank"]
            .sudo()
            .search(
                [
                    ("acc_number", "=", spec["acc_number"]),
                    ("partner_id", "=", company.partner_id.id),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
        )
        if existing:
            print("    ok       %-30s %s (exists)" % (name, spec["acc_number"]))
            account = existing
        else:
            print("    create   %-30s %s @ %s" % (name, spec["acc_number"], spec["bank"]))
            account = env["res.partner.bank"]
            if COMMIT:
                account = (
                    env["res.partner.bank"]
                    .sudo()
                    .create(
                        {
                            "acc_number": spec["acc_number"],
                            "bank_id": bank.id,
                            "partner_id": company.partner_id.id,
                            "company_id": company.id,
                            "acc_holder_name": spec.get("acc_holder_name") or company.name,
                        }
                    )
                )
        for journal_name in spec.get("journals", []):
            journal = (
                env["account.journal"]
                .sudo()
                .search([("name", "=", journal_name), ("company_id", "=", company.id)], limit=1)
            )
            if not journal:
                print("        journal NOT FOUND: %s" % journal_name)
                continue
            print("        attach to journal %s" % journal_name)
            if COMMIT and account:
                journal.bank_account_id = account.id

# --- 2. fallback text ----------------------------------------------------
print("\n[2] report_bank_details (OTHER COMMENTS fallback)")
if not BANK_DETAILS:
    print("    (no text supplied — skipped)")
for name, text in BANK_DETAILS.items():
    company = _company(name)
    if not company:
        print("    NOT FOUND  %s" % name)
        continue
    print("    %-30s %s" % (name, text.replace("\n", " | ")))
    if COMMIT:
        company.report_bank_details = text

# --- 3. product name on document lines -----------------------------------
print("\n[3] report_show_product_name")
if SHOW_PRODUCT_NAME:
    for company in env["res.company"].sudo().search([]):
        print("    %-30s %s -> True" % (company.name, company.report_show_product_name))
        if COMMIT:
            company.report_show_product_name = True

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPreview only — nothing written. Set COMMIT = True to apply.")
