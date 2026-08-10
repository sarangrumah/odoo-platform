# -*- coding: utf-8 -*-
"""Archive bank/cash journals whose default account is archived and that nobody used.

WHY THIS IS NEEDED
------------------
`trn_arkaaim_begbal` company 1 carries a journal `BNK1 "Bank"` pointing at
account `101401 Bank`, which is **archived** — both are leftovers from the
generic chart that shipped before the Erajaya chart was loaded. The real bank
journals are `BCA1` and `BCA2` on `1103019300` / `1103019290`.

A journal in that state is worse than a missing one: it looks perfectly usable
in the Register Payment dropdown, accepts the configuration every setup script
throws at it, and only fails when someone actually posts::

    UserError: The account Bank (101401) is archived.

So the journal has to go, not just be left alone.

ARCHIVE, NOT DELETE, AND ONLY WHEN COMPLETELY UNUSED
----------------------------------------------------
The script archives (`active = False`). It never unlinks: a journal is
referenced by sequences, by any entry ever posted through it, and by the audit
trail — deleting one is how you lose the ability to explain last year's books.

It archives only a journal with **zero** journal entries, **zero** journal
items, **zero** payments and **zero** bank statement lines, whose default
account also holds nothing. Anything with history is reported instead: there
the fix is to repoint the journal at a live account (a decision about which
account, which this script will not make for you), not to hide it.

The journal's own payment-method lines are left as they are. They are inert
once the journal is archived, and keeping them means un-archiving restores the
journal exactly as it was.

WHAT IT DELIBERATELY DOES NOT TOUCH
-----------------------------------
A journal whose default account is *live* but duplicated elsewhere — e.g.
`prd_arkaaim`'s `BNK1`, which shares account `1103019280` with `BCA2`. That is
untidy, not broken, and consolidating two journals that both work is a
conversation with Finance about which one people have been using.

WHEN TO RUN
-----------
`trn_arkaaim_begbal`. Harmless elsewhere — on a clean DB it reports nothing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d trn_arkaaim_begbal --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < archive_stale_bank_journals.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Journal = env["account.journal"].sudo()
Move = env["account.move"].sudo()
Line = env["account.move.line"].sudo()
Payment = env["account.payment"].sudo()
Statement = env["account.bank.statement.line"].sudo()

print("=" * 92)
print("Stale bank/cash journals — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 92)

archived_count = 0
reported = []

for company in env["res.company"].sudo().search([], order="id"):
    journals = Journal.with_company(company).search(
        [("company_id", "=", company.id), ("type", "in", ("bank", "cash")), ("active", "=", True)],
        order="id",
    )
    stale = journals.filtered(lambda j: j.default_account_id and not j.default_account_id.active)
    print(
        "\n--- company %s — %s: %d live bank/cash journal(s), %d with an archived default account"
        % (company.id, company.name, len(journals), len(stale))
    )
    if not stale:
        continue

    for journal in stale:
        account = journal.default_account_id
        usage = {
            "entries": Move.search_count([("journal_id", "=", journal.id)]),
            "items": Line.search_count([("journal_id", "=", journal.id)]),
            "payments": Payment.search_count([("journal_id", "=", journal.id)]),
            "statements": Statement.search_count([("journal_id", "=", journal.id)]),
            "account_items": Line.search_count([("account_id", "=", account.id)]),
        }
        summary = ", ".join("%s=%d" % (k, v) for k, v in usage.items())
        used = any(usage.values())
        print(
            "    %-6s %-28s default=%s (archived)  %s"
            % (journal.code, journal.name, account.with_company(company).code, summary)
        )

        if used:
            reported.append(
                "%s/%s has history (%s) — repoint it at a live account instead; that choice is Finance's"
                % (company.id, journal.code, summary)
            )
            print("      KEEP  it has history — reported, not touched")
            continue

        print("      ARCHIVE  unused everywhere; the journal, not the config, is the problem")
        if COMMIT:
            journal.active = False
        archived_count += 1

print("-" * 92)
print("%d journal(s) %s" % (archived_count, "archived" if COMMIT else "would be archived"))
for item in reported:
    print("  REPORT  %s" % item)

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 92)
