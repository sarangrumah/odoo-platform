# -*- coding: utf-8 -*-
"""Give the ARKA-AIM trade-payable accounts the `liability_payable` type.

WHY THIS IS NEEDED
------------------
On `trn_arkaaim_begbal`, company 1 (AIM) has **zero** accounts typed
`liability_payable`. Partners point at `2103100001 Trade Payables - Third
parties`, which is typed `liability_current`. A vendor bill therefore cannot be
created at all: the counterpart line gets a due date, core sees a due date on a
non-payable account, and `_check_payable_receivable` raises

    Any journal item on a payable account must have a due date and vice versa.

That sits *upstream* of the outstanding-account blocker fixed by
``setup_payment_journals.py`` — no bill, nothing to pay.

WHICH ACCOUNTS, AND WHY THOSE
-----------------------------
The reference is **company 2 of prd_arkaaim**, the correctly-typed instance of
this same Erajaya chart. There, exactly four accounts carry the payable type::

    2103100001  Trade Payables - Third parties
    2103200001  Trade Payables - Related parties
    2103300001  Non trade payable - Third parties
    2103400001  Non trade payable - Related parties

Company 1 of prd_arkaaim is NOT a usable reference: it has `1106000001 Trade
Receivables - Third Parties` typed `liability_payable` while its own trade
payables are not — see the advisory this script prints at the end.

ONLY THE FIRST TWO ARE ENABLED BY DEFAULT, DELIBERATELY
-------------------------------------------------------
Retyping an account to payable moves every line already sitting on it into the
payable subledger — Aged Payable, partner ledgers, the payments matcher. The
two *trade* accounts are empty on the target DBs, so enabling them unblocks
vendor bills and changes nothing that is already booked. The two *non-trade*
accounts are not: on `trn_arkaaim_begbal`, `2103300001` holds ten monthly
salary accruals plus a rounding line, none with a partner, and `2103400001`
holds one intercompany line. Dragging salary accruals into Aged Payable is an
accounting decision, not a technical one, so those two stay off until Finance
says otherwise. Turn them on by moving the code into ``PAYABLE_CODES``.

WHAT THE SCRIPT REFUSES TO DO
-----------------------------
* Touch an account whose current type is anything other than
  ``liability_current`` — a different type means someone chose it on purpose.
* Touch an account used as a journal's default account: core rejects that with
  "You cannot change the type of an account set as Bank Account on a journal to
  Receivable or Payable."
* Invent a partner or a due date on lines that lack them. It reports them; it
  does not guess. A payable line without a due date will refuse the next write
  Odoo attempts on it, so that report is the thing to act on before enabling a
  non-empty account.

``reconcile`` is forced on together with the type — core requires it
(``_check_reconcile``) and a payable account that cannot reconcile is useless.

WHEN TO RUN
-----------
`trn_arkaaim_begbal` first. `prd_arkaaim` company 1 has the same trade accounts
untyped and would benefit equally, but check the advisory below first: fixing
`1106000001` there is a separate, larger decision.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d trn_arkaaim_begbal --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < fix_payable_account_types.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
# Codes to retype. Add the non-trade pair once Finance has looked at the lines
# already booked on them (the script prints those below).
PAYABLE_CODES = (
    "2103100001",  # Trade Payables - Third parties
    "2103200001",  # Trade Payables - Related parties
)
# Reported, never changed — kept here so the preview shows what was left out.
DEFERRED_CODES = (
    "2103300001",  # Non trade payable - Third parties
    "2103400001",  # Non trade payable - Related parties
)
ONLY_FROM_TYPE = "liability_current"  # refuse to retype anything else
TARGET_TYPE = "liability_payable"
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Account = env["account.account"].sudo()
Journal = env["account.journal"].sudo()
Line = env["account.move.line"].sudo()

print("=" * 92)
print("Payable account types — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 92)


def line_stats(account, company):
    lines = Line.search([("account_id", "=", account.id), ("company_id", "=", company.id)])
    return {
        "total": len(lines),
        "no_due": len(lines.filtered(lambda ln: not ln.date_maturity)),
        "no_partner": len(lines.filtered(lambda ln: not ln.partner_id)),
        "posted": len(lines.filtered(lambda ln: ln.parent_state == "posted")),
    }


def describe(account, company, stats):
    return "%s %-38s %-18s lines=%d (posted=%d, no due=%d, no partner=%d)" % (
        account.with_company(company).code,
        (account.name or "")[:38],
        account.account_type,
        stats["total"],
        stats["posted"],
        stats["no_due"],
        stats["no_partner"],
    )


changed = 0
blocked = []
warnings = []

for company in env["res.company"].sudo().search([], order="id"):
    print("\n--- company %s — %s" % (company.id, company.name))
    already = Account.search([("company_ids", "in", company.id), ("account_type", "=", TARGET_TYPE)])
    print("    payable-typed accounts today: %d" % len(already))
    for account in already:
        print("      have  %s %s" % (account.with_company(company).code, account.name))

    for code in PAYABLE_CODES:
        account = Account.with_company(company).search(
            [("code", "=", code), ("company_ids", "in", company.id)], limit=1
        )
        if not account:
            print("    SKIP  %s not in this company's CoA" % code)
            continue
        if account.account_type == TARGET_TYPE:
            print("    OK    %s already %s" % (code, TARGET_TYPE))
            continue
        if account.account_type != ONLY_FROM_TYPE:
            blocked.append("%s/%s: type is %r, expected %r" % (company.id, code, account.account_type, ONLY_FROM_TYPE))
            print("    BLOCK %s type is %r, not %r — left alone" % (code, account.account_type, ONLY_FROM_TYPE))
            continue
        used_by = Journal.search([("default_account_id", "=", account.id)], limit=1)
        if used_by:
            blocked.append("%s/%s: default account of journal %s" % (company.id, code, used_by.code))
            print("    BLOCK %s is the default account of journal %s — core forbids the change" % (code, used_by.code))
            continue

        stats = line_stats(account, company)
        print("    SET   %s" % describe(account, company, stats))
        if stats["total"]:
            # These lines join the payable subledger the moment the type flips.
            warnings.append(
                "%s/%s: %d existing line(s) move into Aged Payable (%d without a due date, %d without a partner)"
                % (company.id, code, stats["total"], stats["no_due"], stats["no_partner"])
            )
        if COMMIT:
            account.write({"account_type": TARGET_TYPE, "reconcile": True})
        changed += 1

    for code in DEFERRED_CODES:
        account = Account.with_company(company).search(
            [("code", "=", code), ("company_ids", "in", company.id)], limit=1
        )
        if not account or account.account_type == TARGET_TYPE:
            continue
        stats = line_stats(account, company)
        print("    HOLD  %s   <-- not in PAYABLE_CODES" % describe(account, company, stats))

# --- advisory: accounts typed payable that do not look like payables ------
print("\n--- advisory (reported only, never changed)")
suspects = Account.search([("account_type", "=", TARGET_TYPE)]).filtered(
    lambda a: "receivable" in (a.name or "").lower() or "piutang" in (a.name or "").lower()
)
if suspects:
    for account in suspects:
        print("    !! %s is typed %s — the name says receivable" % (account.display_name, TARGET_TYPE))
    print("       Retyping one of these is a bigger decision: it moves posted balances between")
    print("       the AR and AP subledgers. Raise it with Finance rather than folding it in here.")
else:
    print("    none")

print("-" * 92)
print("%d account(s) %s" % (changed, "updated" if COMMIT else "would change"))
for item in blocked:
    print("  BLOCKED  %s" % item)
for item in warnings:
    print("  WARNING  %s" % item)

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 92)
