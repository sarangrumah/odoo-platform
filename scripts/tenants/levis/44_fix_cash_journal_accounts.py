"""Give every POS cash journal its own dedicated cash account.

The EBR chart (``ebr_coa.csv``) defines only seven ``1102*`` accounts::

    1102000001 Cash on hand IDR      1102000008 Cash on hand - RA
    1102000002 Cash on hand USD      1102000009 Cash clearing acc
    1102000003 Cash on hand MYR      1102000099 Petty Cash clearing
    1102000004 Cash on hand SGD

It has no per-store cash account. When ``21_seed_pos.py`` created the 22 store
POS configs, ``point_of_sale`` auto-created a cash journal for each and let Odoo
pick its default account by walking the ``1102`` code block. The walk collided
with the six genuine EBR accounts above, so six store journals ended up posting
into them instead of into an account of their own:

    Cash - OLS SES - TUNJUNGAN PLAZA 3    -> 1102000001 Cash on hand IDR
    Cash - OLS SES - PONDOK INDAH MALL 1  -> 1102000002 Cash on hand USD
    Cash - OLS SES - PONDOK INDAH MALL 2  -> 1102000003 Cash on hand MYR
    Cash - OLS SES - KELAPA GADING MALL   -> 1102000004 Cash on hand SGD
    Cash - OLS SES - CENTRAL PARK         -> 1102000008 Cash on hand - RA
    Cash - OLS SES - LOTTE SHOPPING AVE   -> 1102000009 Cash clearing acc

The remaining sixteen got their own auto-created ``Cash - OLS SES - <store>``
account (codes ``1102000005..23``), which is what all 22 should look like. The
``Petty Cash`` journal has the same defect: it posts into ``Cash on hand IDR``
even though ``1102000024 Petty Cash`` exists.

This script gives each of the seven a dedicated account (created at the next free
code in the ``1102`` block), reclasses the handful of already-posted lines that
landed on an EBR account through one of those journals, and archives the two
unused ``Cash (POS) (copy)`` accounts left behind by a journal duplication.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/44_fix_cash_journal_accounts.py

Dry-run by default (``RUN_DRY=1``). Idempotent. Run after ``43_align_pos_naming.py``
-- the target account name is the journal name, which ``43`` fixes.

Reclassing writes ``account_move_line.account_id`` in SQL because the ORM refuses
to move a posted line. It is guarded three ways: the line must be unreconciled,
its move's journal must be the very cash journal being repointed, and debit/credit
are untouched, so every move stays balanced. Anything that fails a guard is left
in place and reported.
"""

import os
import sys

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")
CODE_PREFIX = "1102"
CODE_WIDTH = 10
ORPHAN_ACCOUNT_NAME = "Cash (POS) (copy)"

env = env  # noqa: F821  injected by `odoo shell`
cr = env.cr
log = []
out = sys.stderr

Account = env["account.account"].with_context(active_test=False)


def _codes_in_use(company):
    accounts = Account.search([("company_ids", "in", company.id)])
    return {a.with_company(company).code for a in accounts if a.with_company(company).code}


_used = {}


def _next_code(company):
    """Lowest free ``1102………`` code for ``company``."""
    if company.id not in _used:
        _used[company.id] = _codes_in_use(company)
    used = _used[company.id]
    n = 1
    while True:
        code = CODE_PREFIX + str(n).zfill(CODE_WIDTH - len(CODE_PREFIX))
        if code not in used:
            used.add(code)
            return code
        n += 1


def _find_or_create(company, name):
    """The ``asset_cash`` account called ``name``, created at the next free code."""
    existing = Account.search(
        [("name", "=", name), ("account_type", "=", "asset_cash"), ("company_ids", "in", company.id)],
        limit=1,
    )
    if existing:
        return existing
    code = _next_code(company)
    account = Account.with_company(company).create(
        {"name": name, "code": code, "account_type": "asset_cash", "company_ids": [(4, company.id)]}
    )
    log.append("  CREATE account %-6s %s  %s" % (account.id, code, name))
    return account


def _reclass(journal, old_account, new_account):
    """Move ``journal``'s posted lines off ``old_account``. Returns (moved, stuck)."""
    cr.execute(
        """
        SELECT l.id, l.full_reconcile_id IS NOT NULL OR l.matching_number IS NOT NULL
          FROM account_move_line l
          JOIN account_move m ON m.id = l.move_id
         WHERE l.account_id = %s AND m.journal_id = %s
        """,
        (old_account.id, journal.id),
    )
    rows = cr.fetchall()
    movable = [lid for lid, reconciled in rows if not reconciled]
    stuck = [lid for lid, reconciled in rows if reconciled]
    if movable:
        cr.execute(
            "UPDATE account_move_line SET account_id = %s WHERE id = ANY(%s)",
            (new_account.id, movable),
        )
        log.append(
            "  RECLASS %d line(s) %s -> %s (via %s)"
            % (len(movable), old_account.with_company(journal.company_id).code,
               new_account.with_company(journal.company_id).code, journal.name)
        )
    if stuck:
        out.write(
            "!! %d reconciled line(s) left on %s via %s: %s\n"
            % (len(stuck), old_account.display_name, journal.name, stuck)
        )
    return len(movable), len(stuck)


def _repoint(journal, target_name):
    """Point ``journal`` at its own ``target_name`` account, moving posted lines along."""
    company = journal.company_id
    current = journal.default_account_id
    if current and current.name == target_name:
        return False
    target = _find_or_create(company, target_name)
    if current:
        _reclass(journal, current, target)
    log.append(
        "  %-42s %s -> %s"
        % (journal.name, current.display_name if current else "(none)", target.display_name)
    )
    journal.default_account_id = target.id
    return True


# --------------------------------------------------------------------------
# 1. Per-store POS cash journals
# --------------------------------------------------------------------------
log.append("== POS cash journals ==")
seen = set()
for config in env["pos.config"].with_context(active_test=False).search([]).sorted("id"):
    for method in config.payment_method_ids.filtered("is_cash_count"):
        journal = method.journal_id
        if not journal or journal.id in seen:
            continue
        seen.add(journal.id)
        _repoint(journal, "Cash - %s" % config.name)

# --------------------------------------------------------------------------
# 2. Petty Cash journal -> the Petty Cash account
# --------------------------------------------------------------------------
log.append("== Petty Cash ==")
for journal in env["account.journal"].with_context(active_test=False).search(
    [("type", "=", "cash"), ("name", "=", "Petty Cash")]
):
    _repoint(journal, "Petty Cash")

# --------------------------------------------------------------------------
# 3. Archive the orphan "(copy)" accounts left by a journal duplication
# --------------------------------------------------------------------------
log.append("== Orphan accounts ==")
for account in Account.search([("name", "=", ORPHAN_ACCOUNT_NAME), ("active", "=", True)]):
    cr.execute("SELECT count(*) FROM account_move_line WHERE account_id = %s", (account.id,))
    if cr.fetchone()[0]:
        out.write("!! %s has journal items, not archived\n" % account.display_name)
        continue
    cr.execute(
        """
        SELECT count(*) FROM account_journal
         WHERE %s IN (default_account_id, suspense_account_id, profit_account_id, loss_account_id)
        """,
        (account.id,),
    )
    if cr.fetchone()[0]:
        out.write("!! %s is still a journal default, not archived\n" % account.display_name)
        continue
    account.active = False
    log.append("  ARCHIVE account %-6s %s" % (account.id, account.display_name))

env.invalidate_all()

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
out.write("\n".join(log) + "\n\n")
out.write("Cash journals after the fix:\n")
bad = 0
for journal in env["account.journal"].with_context(active_test=False).search(
    [("type", "=", "cash")], order="id"
):
    account = journal.default_account_id
    code = account.with_company(journal.company_id).code if account else "-"
    shared = env["account.journal"].with_context(active_test=False).search_count(
        [("type", "=", "cash"), ("default_account_id", "=", account.id)]
    ) if account else 0
    flag = ""
    if not account or account.name != journal.name:
        flag = "   <-- NOT DEDICATED"
        bad += 1
    elif shared > 1:
        flag = "   <-- SHARED BY %d JOURNALS" % shared
        bad += 1
    out.write("  %-42s %-11s %s%s\n" % (journal.name, code, account.name if account else "-", flag))
out.write("\n%d journal(s) still wrong\n" % bad)

if DRY:
    cr.rollback()
    out.write("\nDRY RUN — rolled back. Re-run with RUN_DRY=0 to apply.\n")
else:
    cr.commit()
    out.write("\nCOMMITTED.\n")
out.flush()
