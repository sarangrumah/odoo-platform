# -*- coding: utf-8 -*-
"""Retype company 1's COGS-Others, then point the purchase journal at it.

WHY THIS IS NEEDED
------------------
The `BILL` (Pembelian) journal of company 1 (PT Aero Inovasi Media) on
prd_arkaaim still carries ``default_account_id = 600000 "Expenses"`` — a
six-digit account from the generic chart that shipped with ``account`` and was
ARCHIVED the moment the ten-digit PSAK chart replaced it. Every active account
on this database is ten digits; the short codes are all leftovers.

An archived account is not a cosmetic problem. Core refuses **every write** to a
move that touches one (``The account ... is archived.``), so a bill that falls
back to the journal default is frozen: it can be neither posted nor edited.

Company 2 points the same journal at ``6199000000 "COGS-Others"``. Company 1
cannot simply copy that, because its own ``6199000000`` is typed **income**
while company 2's is ``expense_direct_cost`` — out of 558 accounts compared
across the two companies, only this one and ``2103300090`` differ at all, so
this is a load error in company 1's chart rather than a deliberate choice. It
also matters beyond this journal: company 1's ``ir.default`` for
``product.category.property_account_expense_categ_id`` points at that same
account, so every product expense default resolves to an income-typed account.

So the type is corrected first, and only then is the journal wired to it.

WHY THIS IS SAFE
----------------
Account 360 (``6199000000``, company 1) has **zero journal items and zero
balance** — nothing has ever been booked to it. Retyping therefore cannot move
a reported figure; the script asserts that rather than assuming it, and refuses
to touch an account that carries entries.

``6122000000 "COGS-Rental Asset"`` is typed ``income`` in **both** companies, so
it is a chart-wide question for Accounting, not company-1 drift. It is left
alone. ``2103300090`` likewise.

NOT DONE HERE
-------------
The five bank/cash journals still point ``suspense_account_id`` at the archived
``101402``, and ``res_company.transfer_account_id`` of company 1 does too.
Fixing those needs three accounts that do not exist in company 1's chart
(``1103000002``, ``9990000001``, ``9990000002``), i.e. a CoA change — pending a
decision. Payments are unaffected either way: they were moved to direct-to-bank
on 10-Aug-2026 and never traverse a suspense account.

WHEN TO RUN
-----------
Once on prd_arkaaim. Idempotent: a second run prints only OK lines.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < fix_purchase_journal_expense.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
EXPENSE_CODE = "6199000000"  # COGS-Others
WANT_TYPE = "expense_direct_cost"  # what company 2 uses for the same code
JOURNAL_CODES = ("BILL",)  # purchase journal(s) to re-point
COMPANY_ID = 1
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

company = env["res.company"].sudo().browse(COMPANY_ID)
Account = env["account.account"].sudo().with_company(company)
Journal = env["account.journal"].sudo()
AML = env["account.move.line"].sudo()

print("=" * 78)
print("Purchase journal expense wiring — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("=" * 78)

failures = []
changed = 0

account = Account.search([("code", "=", EXPENSE_CODE)], limit=1)
if not account:
    failures.append("account %s not found in company %s" % (EXPENSE_CODE, company.id))
elif not account.active:
    failures.append("account %s is archived — pick another" % EXPENSE_CODE)

# ---------------------------------------------------------------- step 1 --
print("\n--- 1. Account type " + "-" * 58)
if account and account.active:
    lines = AML.search_count([("account_id", "=", account.id)])
    if account.account_type == WANT_TYPE:
        print("OK    %s (id %s) already %s" % (EXPENSE_CODE, account.id, WANT_TYPE))
    elif lines:
        # Retyping an account that carries entries moves them between P&L
        # sections. That is a reporting change, not a config fix, and it is
        # Accounting's call — so stop rather than do it quietly.
        msg = (
            "account %s (id %s) carries %d journal item(s); retyping would move "
            "reported figures — refer to Accounting" % (EXPENSE_CODE, account.id, lines)
        )
        print("ABORT %s" % msg)
        failures.append(msg)
    else:
        print(
            "SET   %s (id %s) %s -> %s  (0 journal items, so no reported figure moves)"
            % (EXPENSE_CODE, account.id, account.account_type, WANT_TYPE)
        )
        if COMMIT:
            account.account_type = WANT_TYPE
        changed += 1

# ---------------------------------------------------------------- step 2 --
print("\n--- 2. Purchase journal default " + "-" * 46)
if account and account.active and not failures:
    journals = Journal.search(
        [
            ("company_id", "=", company.id),
            ("code", "in", list(JOURNAL_CODES)),
        ],
        order="id",
    )
    if not journals:
        msg = "no journal %s on company %s" % ("/".join(JOURNAL_CODES), company.id)
        print("FAIL  %s" % msg)
        failures.append(msg)
    for journal in journals:
        current = journal.default_account_id
        if current == account:
            print("OK    journal %-6s already defaults to %s" % (journal.code, account.code))
            continue
        print(
            "SET   journal %-6s default %s -> %s (%s)"
            % (
                journal.code,
                ("%s%s" % (current.code, "" if current.active else " [ARCHIVED]")) if current else "(none)",
                account.code,
                account.display_name,
            )
        )
        if COMMIT:
            journal.default_account_id = account.id
        changed += 1

# ---------------------------------------------------------------- step 3 --
print("\n--- 3. Verification " + "-" * 58)
if COMMIT and not failures:
    env.cr.flush()
    env.invalidate_all()
    account = Account.browse(account.id)
    checks = [
        ("account type", account.account_type == WANT_TYPE, account.account_type),
        ("account active", account.active, account.active),
        ("no journal items", AML.search_count([("account_id", "=", account.id)]) == 0, "0"),
    ]
    for journal in Journal.search([("company_id", "=", company.id), ("code", "in", list(JOURNAL_CODES))]):
        checks.append(
            (
                "journal %s default" % journal.code,
                journal.default_account_id == account,
                journal.default_account_id.code,
            )
        )
    for label, ok, value in checks:
        print("%-5s %-24s %s" % ("OK" if ok else "FAIL", label, value))
        if not ok:
            failures.append("%s = %s" % (label, value))

# Anything in company 1 still pointing at a short-code or archived account is
# reported every run, so the remaining gap stays visible instead of being
# quietly closed by this script.
print("\n--- 4. Still on a short-code or archived account " + "-" * 29)
rows = []
for journal in Journal.search([("company_id", "=", company.id)], order="id"):
    for fname in ("default_account_id", "suspense_account_id", "profit_account_id", "loss_account_id"):
        acc = journal[fname]
        if acc and (not acc.active or len(acc.with_company(company).code or "") != 10):
            rows.append(
                "journal %-6s %-20s %s%s"
                % (journal.code, fname, acc.with_company(company).code, "" if acc.active else " [ARCHIVED]")
            )
transfer = company.transfer_account_id
if transfer and (not transfer.active or len(transfer.with_company(company).code or "") != 10):
    rows.append(
        "company %-5s %-20s %s%s"
        % (
            company.id,
            "transfer_account_id",
            transfer.with_company(company).code,
            "" if transfer.active else " [ARCHIVED]",
        )
    )
if rows:
    for row in rows:
        print("      %s" % row)
    print("      (%d remaining — needs the missing 10-digit accounts, see docstring)" % len(rows))
else:
    print("OK    nothing left on a short-code or archived account")

print("\n" + "-" * 78)
print("%d record(s) %s" % (changed, "updated" if COMMIT else "would change"))

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if failures:
    print("!! %d FAILURE(S) — rolling back, nothing persisted:" % len(failures))
    for f in failures:
        print("   - %s" % f)
    env.cr.rollback()
    print("ROLLED BACK.")
elif COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
