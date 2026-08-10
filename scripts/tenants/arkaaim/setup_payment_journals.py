# -*- coding: utf-8 -*-
"""Unblock payments on ARKA-AIM by giving every bank/cash journal an outstanding account.

WHY THIS IS NEEDED
------------------
Registering a payment against a bill on prd_arkaaim fails with::

    No outstanding account could be found to make the payment

That message is raised by core ``account/models/account_payment.py::
_get_outstanding_account``. Odoo looks for the liquidity counterpart of a
payment in three places, in order:

  1. ``account.payment.method.line.payment_account_id`` of the chosen method;
  2. the chart-template ref ``<company>_account_journal_payment_debit_account_id``
     / ``..._credit_account_id`` (an ``ir.model.data`` row in module ``account``);
  3. ``res_company.transfer_account_id``.

On prd_arkaaim **all three are empty for company 1 (PT Aero Inovasi Media)**:
every payment-method line has a NULL ``payment_account_id``, the two XMLIDs only
exist for company 2, and neither company has a transfer account. Company 2
(PT Aero Reksa Kreasi Angkasa) survives on jalur 2 — it resolves to "Outstanding
Receipts" / "Outstanding Payments" (1103000003 / 1103000004) — which is why it
has posted payments while company 1 has none at all.

There is no "in payment" escape hatch here: this platform runs Odoo Community
(``account_accountant`` is not installed), so ``account.payment.create`` forces
an outstanding account on every single payment.

POSTING POLICY — DIRECT TO BANK
-------------------------------
Agreed with the client: follow the Levi's pattern, i.e. the liquidity line hits
the journal's own bank/cash GL account directly, with no in-transit account in
between. The payment therefore debits/credits the bank account immediately and
the bill goes straight to ``Paid``. This mirrors
``custom_levis_localization/models/setup.py::_set_all_outstanding``, which is
also copied inside ``custom_petty_cash`` — the same idea, one account for every
method line of a journal so nothing silently falls back.

    !! CONSEQUENCE FOR BANK RECONCILIATION. With direct-to-bank the bank GL is
    already moved by the payment. When rekening koran import (custom_bank_import)
    is switched on for ARKA, a statement line must be MATCHED against that
    existing payment entry, never posted as a fresh entry to the same bank
    account, or the bank balance doubles. prd_arkaaim has 0 bank statement lines
    today, so nothing is broken right now — but test this before enabling bank
    reconciliation. Levi's avoids the ambiguity by splitting bank-OUT (direct to
    bank) from bank-IN journals (per-bank clearing account); ARKA has not split
    its journals, and that split can be done later if reconciliation needs it.

SCOPE — COMPANY 1 ONLY, BY DEFAULT
----------------------------------
Company 2 already has 5 posted payments routed through Outstanding Receipts /
Outstanding Payments. Flipping it to direct-to-bank now would leave those two
accounts holding a balance under one policy and everything after the cutover
under another. So this script touches company 1 only. Set ``INCLUDE_ARKA = True``
if Accounting explicitly wants company 2 converted too.

PETTY CASH JOURNALS
-------------------
``PCPAY`` journals are configured here as well, pointing at their own cash
account, so a manual payment on them does not hit the same crash. Note that
``custom_petty_cash/models/petty_cash_realization.py::_configure_payment_journal``
rewrites those very lines to the *advance* account on the first realization.
That is intended, not a regression — PCPAY is a dedicated journal precisely so
that rewrite cannot touch a real bank journal.

SAFETY NET
----------
If a company has no ``transfer_account_id``, it is pointed at that company's
Bank Suspense Account. That only matters for bank journals created later by a
user through the UI, which would otherwise reproduce this exact crash before
anyone configures them. With the per-line accounts set above, jalur 3 should
never actually be used.

WHEN TO RUN
-----------
trn_arkaaim first, then prd_arkaaim. Idempotent — re-running reports "OK" for
everything already correct. Run it again after installing
``custom_payment_methods_id`` so the new Giro / Bank Transfer method lines get
their account too.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < setup_payment_journals.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False  # True to persist
INCLUDE_ARKA = False  # True to convert company 2 (ARKA) to direct-to-bank too
AIM_COMPANY_ID = 1
ARKA_COMPANY_ID = 2
# Payment methods to offer on every bank journal, when the method is installed.
# manual / check_printing ship with core; giro / bank_transfer come from
# custom_payment_methods_id and are simply skipped when absent.
BANK_METHODS = (
    ("manual", "inbound"),
    ("manual", "outbound"),
    ("check_printing", "outbound"),
    ("giro", "inbound"),
    ("giro", "outbound"),
    ("bank_transfer", "inbound"),
    ("bank_transfer", "outbound"),
)
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Journal = env["account.journal"].sudo()
Method = env["account.payment.method"].sudo()
Line = env["account.payment.method.line"].sudo()

target_ids = [AIM_COMPANY_ID] + ([ARKA_COMPANY_ID] if INCLUDE_ARKA else [])
companies = env["res.company"].sudo().browse(target_ids).exists()

print("=" * 78)
print("Payment journal outstanding accounts — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("companies: %s" % ", ".join("%s:%s" % (c.id, c.name) for c in companies))
print("=" * 78)


def account_code(account, company):
    """Odoo 19 makes ``account.code`` company-dependent; read it in scope."""
    return account.with_company(company).code or "?"


def ensure_method_lines(journal, company):
    """Create the missing method lines for ``journal``. Uninstalled methods are
    skipped silently — giro/bank_transfer only exist once
    custom_payment_methods_id is installed."""
    created = []
    if journal.type != "bank":
        # check_printing / giro / bank_transfer all declare ``type: ('bank',)``,
        # so a cash journal keeps only the manual lines it already has.
        return created
    for code, payment_type in BANK_METHODS:
        method = Method.search([("code", "=", code), ("payment_type", "=", payment_type)], limit=1)
        if not method:
            continue
        existing = Line.search(
            [("journal_id", "=", journal.id), ("payment_method_id", "=", method.id)],
            limit=1,
        )
        if existing:
            continue
        created.append("%s/%s" % (code, payment_type))
        if COMMIT:
            Line.create({"journal_id": journal.id, "payment_method_id": method.id})
    return created


touched_lines = 0
touched_journals = 0
skipped = []

for company in companies:
    journals = Journal.with_company(company).search(
        [("company_id", "=", company.id), ("type", "in", ("bank", "cash"))],
        order="id",
    )
    print("\n--- company %s (%s): %d bank/cash journal(s)" % (company.id, company.name, len(journals)))

    for journal in journals:
        account = journal.default_account_id
        if not account:
            # Never guess a liquidity account: a wrong one silently mis-posts
            # every payment on this journal.
            skipped.append("%s/%s (no default account)" % (company.id, journal.code))
            print("  SKIP  %-6s %-42s no default_account_id" % (journal.code, journal.name))
            continue

        if not account.active:
            # Configuring this journal would look like success and then fail at
            # posting time: `_check_constrains_account_id_journal_id` refuses an
            # archived account. The journal itself is the thing to fix — repoint
            # it at a live bank account, or archive it.
            skipped.append(
                "%s/%s (default account %s is archived)" % (company.id, journal.code, account_code(account, company))
            )
            print(
                "  SKIP  %-6s %-42s default account %s is ARCHIVED"
                % (journal.code, journal.name, account_code(account, company))
            )
            continue

        added = ensure_method_lines(journal, company)
        # Re-read after create so newly added lines get their account below.
        journal.invalidate_recordset(["inbound_payment_method_line_ids", "outbound_payment_method_line_ids"])
        lines = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids

        wrong = lines.filtered(lambda ln: ln.payment_account_id != account)
        state = "OK" if not wrong and not added else "SET"
        print(
            "  %-5s %-6s %-42s -> %s (%s) | lines %d, to fix %d%s"
            % (
                state,
                journal.code,
                journal.name,
                account_code(account, company),
                account.account_type,
                len(lines),
                len(wrong),
                (", new lines: " + ",".join(added)) if added else "",
            )
        )
        for line in wrong:
            was = account_code(line.payment_account_id, company) if line.payment_account_id else "NOT SET"
            print(
                "          %-24s %-8s  %s -> %s"
                % (line.name, line.payment_method_id.payment_type, was, account_code(account, company))
            )
            if COMMIT:
                line.payment_account_id = account.id
            touched_lines += 1
        if wrong or added:
            touched_journals += 1

# --- safety net: company-level fallback ----------------------------------
print("\n--- transfer account fallback")
for company in env["res.company"].sudo().search([], order="id"):
    if company.transfer_account_id:
        print(
            "  OK    company %s (%s): %s"
            % (company.id, company.name, account_code(company.transfer_account_id, company))
        )
        continue
    suspense = company.account_journal_suspense_account_id
    if not suspense:
        print("  SKIP  company %s (%s): no suspense account to fall back on" % (company.id, company.name))
        continue
    print(
        "  SET   company %s (%s): NOT SET -> %s (Bank Suspense)"
        % (company.id, company.name, account_code(suspense, company))
    )
    if COMMIT:
        company.transfer_account_id = suspense.id

print("-" * 78)
print(
    "%d journal(s) / %d method line(s) %s" % (touched_journals, touched_lines, "updated" if COMMIT else "would change")
)
if skipped:
    print("skipped (needs a default account first): %s" % ", ".join(skipped))

# odoo shell rolls back on exit, so the write only survives an explicit commit.
if COMMIT:
    env.cr.commit()
    print("COMMITTED.")
else:
    env.cr.rollback()
    print("PREVIEW only — rolled back. Set COMMIT = True to persist.")
print("=" * 78)
