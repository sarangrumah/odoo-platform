# Load the EBR 2026 trial balance as summary journal entries (run via odoo shell).
#   docker cp scripts/tenants/levis/tb_ebr.csv odoo19-platform-odoo:/tmp/levis/tb_ebr.csv
#   docker exec -i odoo19-platform-odoo odoo shell -d rnd_levis --no-http < scripts/tenants/levis/60_load_tb.py
#
# Posts, for company id=1:
#   - ONE opening-balance move dated 2026-01-01 from the Beginning Balance (Des-2025) column
#   - ONE summary movement move per month from that month's D / C columns
# The TB is signed & balanced (opening sums to 0; every month sumD==sumC), so each move
# balances on its own. Idempotent: re-running skips moves whose ref already exists.
#
# Env flags:
#   TB_OPENING_ONLY=1   -> post only the opening move (then go live natively in Odoo)
#   TB_DRY=1            -> build & report, roll back instead of committing
import calendar
import csv
import os
from datetime import date

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[tb] " + m)

CSV_PATH = "/tmp/levis/tb_ebr.csv"
COMPANY_ID = 1
JOURNAL_CODE = "EBRTB"
JOURNAL_NAME = "EBR TB Load"
OPENING_ONLY = os.environ.get("TB_OPENING_ONLY") == "1"
DRY = os.environ.get("TB_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
Acc = env["account.account"].with_company(company)
rounding = company.currency_id.rounding or 0.01
log("company=%s currency=%s rounding=%s dry=%s opening_only=%s"
    % (company.name, company.currency_id.name, rounding, DRY, OPENING_ONLY))

# The TB is backdated (Jan-Jun 2026). A fiscalyear lock date silently bumps backdated
# entries to today, so temporarily lift it and ALWAYS restore the original value.
_orig_lock = company.fiscalyear_lock_date
if _orig_lock:
    log("lifting fiscalyear_lock_date %s for the load (will restore)" % _orig_lock)
    company.sudo().write({"fiscalyear_lock_date": False})

# ---- account lookup cache (account.code is company-dependent in Odoo 19) ----
_code2acc = {a.code: a for a in Acc.search([]) if a.code}
log("accounts in DB: %d" % len(_code2acc))


def resolve(code):
    a = _code2acc.get(code)
    if not a:
        raise KeyError("account code %s not found in DB (run 30_fix_coa.py first)" % code)
    return a


# ---- journal (find or create a dedicated general journal) ----
Journal = env["account.journal"]
journal = Journal.search([("code", "=", JOURNAL_CODE), ("company_id", "=", company.id)], limit=1)
if not journal:
    journal = Journal.create({
        "name": JOURNAL_NAME, "code": JOURNAL_CODE, "type": "general", "company_id": company.id,
    })
    log("created journal %s (%s)" % (journal.name, journal.code))
else:
    log("using existing journal %s (%s)" % (journal.name, journal.code))


def r(x):
    """Round to company currency."""
    return round(float(x) / rounding) * rounding


def post_move(ref, mdate, legs):
    """legs = list of (account_code, name, signed_amount)  (>0 debit, <0 credit).
    Rounds each leg and nudges the largest leg to absorb any sub-unit residual so the
    move balances exactly."""
    if env["account.move"].search_count([("ref", "=", ref), ("company_id", "=", company.id)]):
        log("SKIP %s (already exists)" % ref)
        return None
    rows = []
    for code, name, amt in legs:
        amt = r(amt)
        if amt == 0:
            continue
        rows.append([resolve(code).id, name[:200], amt])
    if not rows:
        log("SKIP %s (no nonzero lines)" % ref)
        return None
    residual = r(sum(x[2] for x in rows))
    if residual:
        big = max(rows, key=lambda x: abs(x[2]))
        big[2] = r(big[2] - residual)
    line_ids = []
    for acc_id, name, amt in rows:
        line_ids.append((0, 0, {
            "account_id": acc_id, "name": name,
            "debit": amt if amt > 0 else 0.0,
            "credit": -amt if amt < 0 else 0.0,
        }))
    move = env["account.move"].create({
        "journal_id": journal.id, "date": mdate, "ref": ref,
        "company_id": company.id, "move_type": "entry", "line_ids": line_ids,
    })
    move.action_post()
    log("posted %s : %d lines, total=%s" % (ref, len(line_ids),
        sum(l[2]["debit"] - l[2]["credit"] for l in line_ids)))
    return move


# ---- read TB ----
with open(CSV_PATH) as f:
    tb = list(csv.DictReader(f))
log("TB accounts: %d" % len(tb))

# ---- 1. opening balance move (2026-01-01) ----
opening_legs = [(row["account"], row["description"] or ("Opening %s" % row["account"]),
                 float(row["m1_beg"])) for row in tb if r(row["m1_beg"]) != 0]
post_move("EBR-TB-OPEN-2026", date(2026, 1, 1), opening_legs)

# ---- 2. monthly movement moves ----
if OPENING_ONLY:
    log("TB_OPENING_ONLY=1 -> skipping monthly movement moves")
else:
    for m in range(1, 13):
        legs = []
        for row in tb:
            d = float(row["m%d_d" % m]); c = float(row["m%d_c" % m])
            net = d - c
            if r(net) == 0:
                continue
            legs.append((row["account"], row["description"] or ("Movement %s" % row["account"]), net))
        if not legs:
            continue
        last_day = calendar.monthrange(2026, m)[1]
        post_move("EBR-TB-2026-%02d" % m, date(2026, m, last_day), legs)

# restore the original lock date on the same records we changed
if _orig_lock:
    company.sudo().write({"fiscalyear_lock_date": _orig_lock})
    log("restored fiscalyear_lock_date -> %s" % _orig_lock)

if DRY:
    env.cr.rollback()
    log("TB_DRY=1 -> rolled back, nothing committed (lock restore also rolled back)")
else:
    env.cr.commit()
    log("committed")

log("==== DONE ====")
