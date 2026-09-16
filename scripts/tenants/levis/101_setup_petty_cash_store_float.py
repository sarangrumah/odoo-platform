# Seed the 0.6.0 store-float configuration for custom_petty_cash.
#
#   docker exec -i [-e PCF_COMMIT=1] odoo19-platform-odoo \
#     odoo shell -d <db> --no-http < 101_setup_petty_cash_store_float.py
#
# WHY A SCRIPT AND NOT A MIGRATION
# --------------------------------
# custom_petty_cash is a SHARED addon: six DBs carry it (four Levi's + two
# ARKA-AIM). Auto-creating three new petty.cash.type records on every company of
# every one of them would drop unused clutter into two tenants that never asked
# for the store float. The module ships the *kinds* and the engine; this script
# opts one tenant in.
#
# WHAT IT DOES (idempotent, PREVIEW unless PCF_COMMIT=1)
#   1. three petty.cash.type records per company -- Petty Cash Awal / Realisasi /
#      Claim -- each with its own sequence, inheriting the accounting map of the
#      company's existing default type (or the res.company fallback fields);
#   2. one petty.cash.float per Operating Unit analytic account, at the plafon in
#      ir.config_parameter custom_petty_cash.initial_amount (default 1.000.000).
#
# Env:
#   PCF_COMMIT=1     write (default: report only, nothing is written)
#   PCF_PLAFON=...   plafon per store in rupiah (default: 1000000)
#   PCF_NO_FLOATS=1  seed the types only, leave the floats to Finance
import os

COMMIT = os.environ.get("PCF_COMMIT") == "1"
PLAFON = float(os.environ.get("PCF_PLAFON") or 1000000)
SEED_FLOATS = os.environ.get("PCF_NO_FLOATS") != "1"

# (code, name, kind, sequence prefix)
TYPES = [
    ("PCA", "Petty Cash Awal", "pc_initial", "PCA/%(year)s/"),
    ("PCR", "Realisasi", "pc_realization", "PCR-R/%(year)s/"),
    ("PCC", "Claim", "pc_claim", "PCC/%(year)s/"),
]

Type = env["petty.cash.type"]
Float = env["petty.cash.float"]
Sequence = env["ir.sequence"]
Param = env["ir.config_parameter"].sudo()

plan_name = (
    Param.get_param("custom_petty_cash.ou_plan_name")
    or Param.get_param("custom_accounting_reports.branch_plan_name")
    or "Operating Unit"
)
plan = env["account.analytic.plan"].search([("name", "=", plan_name)], limit=1)

print("=" * 72)
print("custom_petty_cash store float setup -- %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("plafon per store : %s" % f"{PLAFON:,.0f}")
print("analytic plan    : %s%s" % (plan_name, "" if plan else "  << NOT FOUND"))
print("=" * 72)

if not plan:
    print("Refusing to seed floats: no analytic plan named %r. Set" % plan_name)
    print("ir.config_parameter custom_petty_cash.ou_plan_name to this tenant's")
    print("Operating Unit plan first.")
    SEED_FLOATS = False

Param.set_param("custom_petty_cash.initial_amount", str(PLAFON))

for company in env["res.company"].search([]):
    print("\n--- %s (id %s) ---" % (company.name, company.id))
    # The accounting map to copy: the company's default type, else any type,
    # else the legacy res.company fields that predate petty.cash.type.
    source = Type.search([("company_id", "=", company.id), ("is_default", "=", True)], limit=1) or Type.search(
        [("company_id", "=", company.id)], limit=1
    )
    accounting = {
        "advance_account_id": (source.advance_account_id or company.petty_cash_advance_account_id).id or False,
        "bank_out_journal_id": (source.bank_out_journal_id or company.petty_cash_bank_out_journal_id).id or False,
        "payment_journal_id": (source.payment_journal_id or company.petty_cash_payment_journal_id).id or False,
        "expense_journal_id": (source.expense_journal_id or company.petty_cash_expense_journal_id).id or False,
    }
    if not accounting["advance_account_id"]:
        print("  SKIP: no advance account configured (type or Accounting Settings).")
        continue
    print("  accounting inherited from: %s" % (source.display_name if source else "res.company fallback"))

    for code, name, kind, prefix in TYPES:
        existing = Type.search([("company_id", "=", company.id), ("code", "=", code)], limit=1)
        if existing:
            print("  = %-4s %-18s already present (id %s)" % (code, name, existing.id))
            continue
        seq_code = "petty.cash.request.%s" % kind
        seq = Sequence.search([("code", "=", seq_code)], limit=1)
        print("  + %-4s %-18s kind=%s seq=%s" % (code, name, kind, prefix))
        if not COMMIT:
            continue
        if not seq:
            seq = Sequence.create({"name": "Petty Cash - %s" % name, "code": seq_code, "prefix": prefix, "padding": 5})
        Type.create(
            dict(
                accounting,
                name=name,
                code=code,
                kind=kind,
                company_id=company.id,
                sequence_id=seq.id,
                # Claims are settled straight by Finance and routinely carry a
                # supplier invoice; the float kinds book plain expenses.
                allow_third_party=(kind == "pc_claim"),
            )
        )

    if not SEED_FLOATS:
        continue
    analytics = env["account.analytic.account"].search(
        [("plan_id", "=", plan.id), "|", ("company_id", "=", False), ("company_id", "=", company.id)]
    )
    print("  stores in plan %r: %s" % (plan_name, len(analytics)))
    for analytic in analytics:
        existing = Float.search([("company_id", "=", company.id), ("l10n_ou_analytic_id", "=", analytic.id)], limit=1)
        if existing:
            print("    = float %-40s plafon %s" % (analytic.display_name[:40], f"{existing.amount_plafon:,.0f}"))
            continue
        print("    + float %-40s plafon %s" % (analytic.display_name[:40], f"{PLAFON:,.0f}"))
        if COMMIT:
            Float.create(
                {
                    "company_id": company.id,
                    "l10n_ou_analytic_id": analytic.id,
                    "amount_plafon": PLAFON,
                }
            )

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPREVIEW only -- nothing written. Re-run with PCF_COMMIT=1.")
