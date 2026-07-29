# Remove the duplicated June bank statement import (Opsi A).
#
# The June BCA movements were already loaded into the ledger from EBR's GL detail
# (journal BNK1, account 1103019310). The 24-Jul import of the KlikBCA Bisnis export
# booked the very same 735 movements a second time through journal IBCA, parking the
# net Rp -240.887 on 1103000002 Bank Suspense and double-counting the gross cash flow
# on 1103019310. Accounting picked option A on 29-Jul-2026: drop the statement.
#
# July statements (BRI/BNI/Mandiri/BCA) are NOT duplicates -- the EBR GL load stops at
# 30-Jun -- and are left untouched.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/68_purge_dup_bank_statement.py
#
# Env flags:  PURGE_DRY=1        -> report and roll back
#             PURGE_STATEMENT_ID -> override the statement id (default 12)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[purge-dup] " + m)

COMPANY_ID = 1
STATEMENT_ID = int(os.environ.get("PURGE_STATEMENT_ID", "12"))
EXPECT_LINES = 735
EXPECT_DATE = "2026-06-30"
EXPECT_JOURNAL = "IBCA"
DRY = os.environ.get("PURGE_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
statement = env["account.bank.statement"].browse(STATEMENT_ID).exists()
if not statement:
    raise SystemExit("statement %s not found -- nothing to do" % STATEMENT_ID)

lines = statement.line_ids
journal_code = lines[:1].journal_id.code if lines else ""
log("statement %s '%s' date=%s lines=%d journal=%s"
    % (statement.id, statement.name, statement.date, len(lines), journal_code))

# ---- guards: refuse to touch anything but the known duplicate -------------
if len(lines) != EXPECT_LINES:
    raise SystemExit("expected %d lines, found %d -- aborting" % (EXPECT_LINES, len(lines)))
if str(statement.date) != EXPECT_DATE:
    raise SystemExit("expected date %s, found %s -- aborting" % (EXPECT_DATE, statement.date))
if journal_code != EXPECT_JOURNAL:
    raise SystemExit("expected journal %s, found %s -- aborting" % (EXPECT_JOURNAL, journal_code))
reconciled = lines.filtered(lambda l: l.is_reconciled)
if reconciled:
    raise SystemExit("%d lines are reconciled -- aborting" % len(reconciled))
bad_dates = lines.filtered(lambda l: not ("2026-06-01" <= str(l.date) <= "2026-06-30"))
if bad_dates:
    raise SystemExit("%d lines fall outside June 2026 -- aborting" % len(bad_dates))

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}


def bal(code, upto=EXPECT_DATE):
    acc = _code2acc.get(code)
    if not acc:
        return 0.0
    env.cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state='posted' and m.date <= %s and l.account_id=%s and l.company_id=%s""",
        (upto, acc.id, company.id),
    )
    return round(float(env.cr.fetchone()[0]), 2)


before = {c: bal(c) for c in ("1103000002", "1103019310")}
log("before: 1103000002=%s 1103019310=%s" % (before["1103000002"], before["1103019310"]))

saved_lock = company.fiscalyear_lock_date
if saved_lock:
    company.sudo().write({"fiscalyear_lock_date": False})
    log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)

try:
    moves = lines.move_id
    log("unposting %d statement moves" % len(moves))
    moves.button_draft()
    lines.unlink()
    statement.unlink()
    log("statement %s and its lines removed" % STATEMENT_ID)

    after = {c: bal(c) for c in ("1103000002", "1103019310")}
    log("after:  1103000002=%s 1103019310=%s" % (after["1103000002"], after["1103019310"]))
    if after["1103000002"] != 0.0:
        log("WARNING 1103000002 is not zero -- other sources may exist")
    env.cr.execute(
        "select count(*) from account_bank_statement_line l "
        "join account_move m on m.id=l.move_id where m.date <= %s", (EXPECT_DATE,)
    )
    log("remaining statement lines dated <= %s: %s" % (EXPECT_DATE, env.cr.fetchone()[0]))
    env.cr.execute("select id, name, date from account_bank_statement order by id")
    for row in env.cr.fetchall():
        log("remaining statement %s %s %s" % row)
finally:
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": saved_lock})
        log("fiscalyear_lock_date restored to %s" % saved_lock)

if DRY:
    env.cr.rollback()
    log("PURGE_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
