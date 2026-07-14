# Load the 31-Dec-2025 opening balance from the TB "Beginning Balance" column.
#
#   docker cp scripts/tenants/levis/tb_opening_2025.csv odoo19-platform-odoo:/tmp/levis/tb_opening_2025.csv
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/63_load_tb_opening.py
#
# Source: "2026 - EBR - TB and GL - BegBal Odoo.xlsx" / "Trial Balance EBR 2026", column G.
#
# Companion to 62_load_gl_2026.py, which loads MOVEMENTS only. Together:
#   opening(31-Dec-2025) + GL(Jan-Jun 2026) = TB ending June 2026.
# The P/L accounts in this opening carry their 2025 balances; the GL's "Opening Balance 2026"
# voucher closes them into retained earnings 3006100001, leaving them at zero by June.
#
# Env flags:  TB_DRY=1 -> build, report, roll back
import csv
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[tbopen] " + m)

CSV_PATH = "/tmp/levis/tb_opening_2025.csv"
COMPANY_ID = 1
REF = "EBR-TB-OPEN-2026"
OPEN_DATE = "2026-01-01"
JOURNAL = "EBRTB"
DRY = os.environ.get("TB_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
rounding = company.currency_id.rounding or 0.01

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}
journal = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", company.id)], limit=1)
if not journal:
    raise SystemExit("journal %s not found" % JOURNAL)

if Move.search_count([("ref", "=", REF), ("company_id", "=", company.id)]):
    raise SystemExit("opening entry %s already exists -- nothing to do" % REF)

saved_lock = company.fiscalyear_lock_date
if saved_lock:
    company.sudo().write({"fiscalyear_lock_date": False})
    log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)


def r(x):
    try:
        return round(float(x) / rounding) * rounding
    except (TypeError, ValueError):
        return 0.0


try:
    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    line_ids, total = [], 0.0
    for row in rows:
        acc = _code2acc.get(row["account"])
        if not acc:
            raise SystemExit("account %s not in COA" % row["account"])
        d, c = r(row.get("d")), r(row.get("c"))
        if d == 0 and c == 0:
            continue
        line_ids.append(
            (
                0,
                0,
                {
                    "account_id": acc.id,
                    "name": row.get("account_desc") or "Opening balance 31-Dec-2025",
                    "debit": d,
                    "credit": c,
                },
            )
        )
        total += d - c

    if r(total) != 0:
        raise SystemExit("opening does not balance: %s" % r(total))
    log("lines=%d balanced" % len(line_ids))

    move = Move.create(
        {
            "journal_id": journal.id,
            "date": OPEN_DATE,
            "ref": REF,
            "company_id": company.id,
            "move_type": "entry",
            "narration": "Opening balance per Trial Balance EBR 2026, column 'Beginning Balance' (31-Dec-2025)",
            "line_ids": line_ids,
        }
    )
    move.action_post()
    log("posted %s (%s) total debit %s" % (move.name, move.date, sum(l[2]["debit"] for l in line_ids)))
finally:
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": saved_lock})
        log("fiscalyear_lock_date restored to %s" % saved_lock)

if DRY:
    env.cr.rollback()
    log("TB_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
