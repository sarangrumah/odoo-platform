# Restructure the June sales block to match EBR accounting's book presentation,
# with one adjustment entry PER TRADING DAY (accounting requirement 13-Jul-2026):
#
#   1. POS receivable 1106000112  -> Trade Receivables 1106000001
#      (their books carry a single trade-receivables account; combined balance
#       must land at their figure, e.g. 1.025.747.288 per 10-Jul books)
#   2. Sales Return 53xxx         -> the matching Gross Sales 512xxxx account
#      (their books net returns into gross sales; analytic/OU is preserved
#       line-by-line so per-store P&L stays correct)
#
# July sales are on HOLD: this script only touches posted entries dated <= 2026-06-30
# and creates adjustment entries on those same dates.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/66_reclass_sales_structure.py
#
# Env flags:  RECLASS_DRY=1 -> build, report, roll back
import os
from collections import defaultdict

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[reclass] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
REF_PREFIX = "EBR-RECLASS-SALES"
CUTOFF = "2026-06-30"  # sales after this date are held, do not touch
RECV_FROM, RECV_TO = "1106000112", "1106000001"
RETURN_MAP = {  # sales return -> gross sales (netted in EBR's books)
    "5320010001": "5120010001",
    "5320010003": "5120010003",
    "5320010004": "5120010004",
}
DRY = os.environ.get("RECLASS_DRY") == "1"

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
Aml = env["account.move.line"].with_company(company)
rounding = company.currency_id.rounding or 0.01
r = lambda x: round(float(x) / rounding) * rounding

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}
journal = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", company.id)], limit=1)
if not journal:
    raise SystemExit("journal %s not found" % JOURNAL)

if Move.search_count([("ref", "like", REF_PREFIX + "%"), ("company_id", "=", company.id)]):
    raise SystemExit("reclass entries (%s*) already exist -- nothing to do" % REF_PREFIX)

acc_recv_from, acc_recv_to = _code2acc.get(RECV_FROM), _code2acc.get(RECV_TO)
if not acc_recv_from or not acc_recv_to:
    raise SystemExit("receivable accounts %s/%s not in COA" % (RECV_FROM, RECV_TO))

base_dom = [
    ("company_id", "=", company.id),
    ("parent_state", "=", "posted"),
    ("date", "<=", CUTOFF),
]

# ---- collect what must move, grouped by date ------------------------------
# receivable: net amount per date
recv_by_date = defaultdict(float)
for line in Aml.search(base_dom + [("account_id", "=", acc_recv_from.id)]):
    recv_by_date[str(line.date)] += line.debit - line.credit

# returns: keep line granularity so analytic (OU) follows the value
ret_by_date = defaultdict(list)  # date -> [(from_acc, to_acc, net, analytic_distribution)]
for code_from, code_to in RETURN_MAP.items():
    af, at = _code2acc.get(code_from), _code2acc.get(code_to)
    if not af or not at:
        continue
    for line in Aml.search(base_dom + [("account_id", "=", af.id)]):
        net = r(line.debit - line.credit)
        if net:
            ret_by_date[str(line.date)].append((af, at, net, line.analytic_distribution))

dates = sorted(set(recv_by_date) | set(ret_by_date))
log("dates with adjustments: %d" % len(dates))

saved_lock = company.fiscalyear_lock_date
if saved_lock:
    company.sudo().write({"fiscalyear_lock_date": False})
    log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)

try:
    total_recv = total_ret = 0.0
    for day in dates:
        lines = []
        amt = r(recv_by_date.get(day, 0.0))
        if amt:
            # zero the POS receivable, move balance to trade receivables
            lines.append((0, 0, {
                "account_id": acc_recv_from.id, "name": "Reklas piutang POS -> Trade Receivables",
                "debit": -amt if amt < 0 else 0.0, "credit": amt if amt > 0 else 0.0,
            }))
            lines.append((0, 0, {
                "account_id": acc_recv_to.id, "name": "Reklas piutang POS -> Trade Receivables",
                "debit": amt if amt > 0 else 0.0, "credit": -amt if amt < 0 else 0.0,
            }))
            total_recv += amt
        for af, at, net, analytic in ret_by_date.get(day, []):
            # move the return (debit balance) into gross sales, same OU
            lines.append((0, 0, {
                "account_id": af.id, "name": "Reklas retur penjualan -> %s" % at.code,
                "debit": -net if net < 0 else 0.0, "credit": net if net > 0 else 0.0,
                "analytic_distribution": analytic,
            }))
            lines.append((0, 0, {
                "account_id": at.id, "name": "Reklas retur penjualan (net ke gross sales)",
                "debit": net if net > 0 else 0.0, "credit": -net if net < 0 else 0.0,
                "analytic_distribution": analytic,
            }))
            total_ret += net
        if not lines:
            continue
        move = Move.create({
            "journal_id": journal.id,
            "date": day,
            "ref": "%s-%s" % (REF_PREFIX, day),
            "company_id": company.id,
            "move_type": "entry",
            "narration": "Penyesuaian struktur penyajian per pembukuan EBR (piutang POS & retur), per tanggal %s" % day,
            "line_ids": lines,
        })
        move.action_post()
        log("posted %s %s (recv %s, ret-lines %d)" % (move.name, day, r(recv_by_date.get(day, 0.0)), len(ret_by_date.get(day, []))))
    log("moved receivable total %s, returns total %s" % (r(total_recv), r(total_ret)))

    # ---- verify final balances -------------------------------------------
    def bal(code):
        acc = _code2acc[code]
        env.cr.execute(
            """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
               join account_move m on m.id=l.move_id
               where m.state='posted' and l.account_id=%s and l.company_id=%s""",
            (acc.id, company.id))
        return r(env.cr.fetchone()[0])

    for code in [RECV_FROM] + list(RETURN_MAP):
        if code in _code2acc:
            b = bal(code)
            log("balance %s = %s %s" % (code, b, "OK (zeroed)" if b == 0 else "<-- NOT ZERO"))
    for code in [RECV_TO] + sorted(set(RETURN_MAP.values())):
        if code in _code2acc:
            log("balance %s = %s" % (code, bal(code)))
finally:
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": saved_lock})
        log("fiscalyear_lock_date restored to %s" % saved_lock)

if DRY:
    env.cr.rollback()
    log("RECLASS_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
