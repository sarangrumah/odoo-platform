# Point the Cash Advance / petty cash types at the cash-side COA pair Finance
# asked for on 10-Sep-2026:
#
#     disburse:  Dr 1102000099 Petty Cash clearing
#                   Cr 1102000001 Cash on hand IDR
#
#   docker exec -i [-e PCA_COMMIT=1] odoo19-platform-odoo \
#     odoo shell -d <db> --no-http < 106_setup_cash_advance_cash_accounts.py
#
# WHY A SCRIPT AND NOT A MIGRATION
# --------------------------------
# custom_petty_cash is a SHARED addon carried by six DBs; these two account
# codes belong to one tenant's chart. Same reasoning as
# 101_setup_petty_cash_store_float.py -- the module ships the engine, the
# script opts one tenant in.
#
# WHAT IT DOES (idempotent, PREVIEW unless PCA_COMMIT=1)
#   1. makes the clearing account reconcilable -- petty.cash.type.advance_account_id
#      is domain-filtered on reconcile=True, and settlement reconciles the
#      advance leg down to zero;
#   2. finds (or repoints, or creates) a *cash* Bank-Out journal whose
#      default_account_id is Cash on hand -- _disburse_via_entry credits exactly
#      that account;
#   3. writes advance_account_id + bank_out_journal_id on every petty.cash.type
#      of the company, and on the res.company fallback fields behind them.
#
# NOT TOUCHED, deliberately: the Payment journal (PCPAY) outstanding accounts.
# petty.cash.realization._configure_payment_journal rewrites every payment-method
# line of that journal to the advance account each time a third-party bill is
# paid, so any clearing account parked there is both overwritten and, until it
# is, wrong -- the payment must credit the advance, not a clearing account.
#
# Env:
#   PCA_COMMIT=1        write (default: report only, nothing is written)
#   PCA_CLEARING=code   clearing / advance account code (default 1102000099)
#   PCA_CASH=code       cash-on-hand account code      (default 1102000001)
#   PCA_JOURNAL=code    journal code to use/create     (default CSH1)
import os

COMMIT = os.environ.get("PCA_COMMIT") == "1"
CLEARING_CODE = os.environ.get("PCA_CLEARING") or "1102000099"
CASH_CODE = os.environ.get("PCA_CASH") or "1102000001"
JOURNAL_CODE = os.environ.get("PCA_JOURNAL") or "CSH1"

Account = env["account.account"]
Journal = env["account.journal"]
Type = env["petty.cash.type"]
Line = env["account.move.line"]

print("=" * 72)
print("Cash Advance cash accounts -- %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("clearing / advance : %s" % CLEARING_CODE)
print("cash on hand       : %s" % CASH_CODE)
print("=" * 72)

for company in env["res.company"].search([]):
    print("\n--- %s (id %s) ---" % (company.name, company.id))
    # account.code is company-dependent in Odoo 19: read it with_company or the
    # search silently misses every account of the other companies.
    scoped = Account.with_company(company)
    clearing = scoped.search([("code", "=", CLEARING_CODE)], limit=1)
    cash = scoped.search([("code", "=", CASH_CODE)], limit=1)
    if not clearing or not cash:
        print("  SKIP: %s missing from this company's chart." % (CLEARING_CODE if not clearing else CASH_CODE))
        continue
    print("  clearing : %s %s" % (CLEARING_CODE, clearing.name))
    print("  cash     : %s %s" % (CASH_CODE, cash.name))

    if clearing.reconcile:
        print("  = clearing already reconcilable")
    else:
        print("  + set reconcile=True on %s" % CLEARING_CODE)
        if COMMIT:
            clearing.reconcile = True

    # 1. a cash journal that already credits the cash account -- reuse it.
    journal = Journal.search(
        [("company_id", "=", company.id), ("type", "=", "cash"), ("default_account_id", "=", cash.id)],
        limit=1,
    )
    if journal:
        print("  = bank-out journal %s (id %s) already books to %s" % (journal.code, journal.id, CASH_CODE))
    else:
        # 2. the named journal, if it has never been posted to -- repointing a
        #    journal that carries entries would restate them.
        journal = Journal.search([("company_id", "=", company.id), ("code", "=", JOURNAL_CODE)], limit=1)
        if journal and Line.search_count([("journal_id", "=", journal.id)]):
            print("  ! journal %s carries entries -- creating a separate one instead" % JOURNAL_CODE)
            journal = Journal.browse()
        if journal:
            print("  + repoint journal %s (id %s) default account -> %s" % (journal.code, journal.id, CASH_CODE))
            if COMMIT:
                journal.default_account_id = cash.id
        else:
            # 3. nothing reusable.
            code = (
                JOURNAL_CODE
                if not Journal.search_count([("company_id", "=", company.id), ("code", "=", JOURNAL_CODE)])
                else "CSHA"
            )
            print("  + create cash journal %s booking to %s" % (code, CASH_CODE))
            if COMMIT:
                journal = Journal.create(
                    {
                        "name": "Cash Advance - Cash on Hand",
                        "code": code,
                        "type": "cash",
                        "company_id": company.id,
                        "default_account_id": cash.id,
                    }
                )

    types = Type.with_context(active_test=False).search([("company_id", "=", company.id)])
    print("  types: %s" % (len(types) or "none"))
    for rec in types:
        before = "advance=%s bank_out=%s" % (
            rec.advance_account_id.code or rec.advance_account_id.id,
            rec.bank_out_journal_id.code or "-",
        )
        done = rec.advance_account_id == clearing and rec.bank_out_journal_id == journal
        print("  %s %-20s %s" % ("=" if done else "+", rec.name, before))
        if COMMIT and not done:
            rec.write({"advance_account_id": clearing.id, "bank_out_journal_id": journal.id})

    # The res.company fields are the bottom of the request -> type -> company
    # chain; leaving them on the old pair would surprise any type added later.
    print(
        "  %s company fallback advance=%s bank_out=%s"
        % (
            "=" if company.petty_cash_advance_account_id == clearing else "+",
            company.petty_cash_advance_account_id.code or "-",
            company.petty_cash_bank_out_journal_id.code or "-",
        )
    )
    if COMMIT:
        company.write(
            {
                "petty_cash_advance_account_id": clearing.id,
                "petty_cash_bank_out_journal_id": journal.id if journal else False,
            }
        )

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPREVIEW only -- nothing written. Re-run with PCA_COMMIT=1.")
