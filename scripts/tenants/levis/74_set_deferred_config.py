# Seed the custom_account_deferred company config on a levis DB.
# Run via odoo shell:  docker exec -i <odoo> odoo shell -d <db> --no-http < 74_set_deferred_config.py
#
# custom_account_deferred (19.0.1.0.0) refuses to generate deferral /
# recognition entries until the company carries a deferred expense account,
# a deferred revenue account and a general journal. This pins the choices
# made on 24-Jul-2026 (applied to rnd_levis, prd_levis_begbal, prd_levis):
#
#   deferred_expense_account_id -> "Other prepaid expenses"      (asset_prepayments)
#   deferred_revenue_account_id -> "Deferred Income - Current"   (liability_current)
#   deferred_journal_id         -> GLJV "General Journal"        (type=general)
#
# Idempotent: re-running rewrites the same values. Matching is by account
# NAME, not code — account.code is company-dependent on Odoo 19 and the
# EBR chart names are stable across the levis DBs.
#
# DRY by default. Set FIX_APPLY=1 to write.
import os

env = env  # noqa: F821 - provided by odoo shell

APPLY = os.environ.get("FIX_APPLY") == "1"
EXPENSE_ACCOUNT_NAME = "Other prepaid expenses"
REVENUE_ACCOUNT_NAME = "Deferred Income - Current"
JOURNAL_CODE = "GLJV"

tag = "APPLY" if APPLY else "DRY"
log = lambda m: print(f"[{tag}] {m}")  # noqa: E731

if "deferred_journal_id" not in env["res.company"]._fields:
    raise SystemExit("custom_account_deferred is not installed on this DB — install it first.")

company = env["res.company"].search([], limit=1)
Acc = env["account.account"].with_company(company)

exp = Acc.search([("name", "=", EXPENSE_ACCOUNT_NAME)], limit=1)
rev = Acc.search([("name", "=", REVENUE_ACCOUNT_NAME)], limit=1)
jrn = env["account.journal"].search(
    [("code", "=", JOURNAL_CODE), ("type", "=", "general"), ("company_id", "=", company.id)],
    limit=1,
)
missing = [
    label
    for label, rec in (
        (EXPENSE_ACCOUNT_NAME, exp),
        (REVENUE_ACCOUNT_NAME, rev),
        ("journal %s" % JOURNAL_CODE, jrn),
    )
    if not rec
]
if missing:
    raise SystemExit("Not found on this DB: %s" % ", ".join(missing))

log(
    "%s: expense=%s | revenue=%s | journal=%s"
    % (company.name, exp.display_name, rev.display_name, jrn.name)
)
if APPLY:
    company.write(
        {
            "deferred_expense_account_id": exp.id,
            "deferred_revenue_account_id": rev.id,
            "deferred_journal_id": jrn.id,
        }
    )
    env.cr.commit()
    log("written + committed")
else:
    log("dry run — set FIX_APPLY=1 to write")
