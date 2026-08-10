# Post the July-2026 clearing drafts in prd_levis_begbal.
#
#   docker exec -i [-e CLR_POST=1] [-e CLR_DRY=1] odoo19-platform-odoo \
#     odoo shell -d prd_levis_begbal --no-http < 90_post_clearing_juli.py
#
# Why this exists instead of re-running 81 with CLR_POST=1: every block in 81
# returns early when its ref already exists, so `created` stays empty and the
# `if POST and moves:` branch never fires -- 81 can only post entries it built in
# the same run. The 63 drafts are already on disk, so posting needs this.
#
# Env:
#   CLR_POST=1   actually post + reconcile (default: report only, no writes)
#   CLR_DRY=1    post in-transaction then roll back, to rehearse the numbers
import os

COMPANY_ID = 1
REF = "EBR-CLR-JULI-2026-"
DFROM, DTO = "2026-07-01", "2026-07-31"
POST = os.environ.get("CLR_POST") == "1"
DRY = os.environ.get("CLR_DRY") == "1"

# expected end state, from the 7-Aug baseline review (July window only)
EXPECT = {
    "1103000002": 1530199113.09,  # bank suspense
    "7104000001": 94186098.68,  # MDR
    "1106000001": 2949900.00,  # AR EBR
}
EXPECT_OPEN = 490494449.00  # POS receivable July still open after clearing


def log(msg):
    print("[clearing-juli] %s" % msg)


env = env(user=1)
company = env["res.company"].browse(COMPANY_ID)
env = env(context=dict(env.context, allowed_company_ids=[COMPANY_ID]))


def acc(code):
    # account.code is company-dependent in Odoo 19 -- must read with_company
    a = (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", COMPANY_ID)], limit=1)
    )
    if not a:
        raise Exception("account %s not found" % code)
    return a


POS_ACC = {c: acc(c) for c in ["11060001%02d" % i for i in range(1, 11)]}

if company.fiscalyear_lock_date and str(company.fiscalyear_lock_date) >= DFROM:
    raise Exception("fiscalyear_lock_date %s closes July -- refusing" % company.fiscalyear_lock_date)

moves = env["account.move"].search([("company_id", "=", COMPANY_ID), ("ref", "like", REF + "%")])
draft = moves.filtered(lambda m: m.state == "draft")
posted = moves.filtered(lambda m: m.state == "posted")
log("found %d clearing entries: %d draft, %d posted" % (len(moves), len(draft), len(posted)))
if posted:
    log("WARNING: %s already posted" % ", ".join(sorted(posted.mapped("ref"))))
if not draft:
    log("nothing to post")

for m in draft:
    if not (DFROM <= str(m.date) <= DTO):
        raise Exception("%s dated %s is outside July" % (m.ref, m.date))
    delta = sum(m.line_ids.mapped("debit")) - sum(m.line_ids.mapped("credit"))
    if abs(delta) > 0.005:
        raise Exception("%s is out of balance by %.2f" % (m.ref, delta))
log("all drafts balanced and inside July")


def report(stage):
    # the checks below read through raw SQL, so the ORM has to hit the database
    # first -- without this the post-reconcile counts come back pre-reconcile
    env.flush_all()
    for code in ("1103000002", "7104000001", "1106000001"):
        env.cr.execute(
            """select coalesce(sum(debit - credit), 0) from account_move_line
               where account_id = %s and parent_state = 'posted' and date < '2026-08-01'""",
            (acc(code).id,),
        )
        bal = env.cr.fetchone()[0]
        tail = ""
        if stage == "after":
            tail = "  (expected %.2f, delta %.2f)" % (EXPECT[code], bal - EXPECT[code])
        log("%-6s balance %s = %.2f%s" % (stage, code, bal, tail))
    env.cr.execute(
        """select coalesce(sum(amount_residual), 0), count(*) from account_move_line
           where account_id in %s and parent_state = 'posted' and not reconciled
             and date between %s and %s""",
        (tuple(a.id for a in POS_ACC.values()), DFROM, DTO),
    )
    residual, count = env.cr.fetchone()
    tail = "  (expected %.2f, delta %.2f)" % (EXPECT_OPEN, residual - EXPECT_OPEN) if stage == "after" else ""
    log("%-6s POS receivable July open: %.2f on %d lines%s" % (stage, residual, count, tail))


report("before")

if POST and draft:
    draft.action_post()
    log("posted %d entries: %s .. %s" % (len(draft), min(draft.mapped("name")), max(draft.mapped("name"))))
    for code, a in POS_ACC.items():
        lines = env["account.move.line"].search(
            [
                ("company_id", "=", COMPANY_ID),
                ("parent_state", "=", "posted"),
                ("account_id", "=", a.id),
                ("reconciled", "=", False),
                ("date", ">=", DFROM),
                ("date", "<=", DTO),
            ]
        )
        if len(lines) > 1 and lines.filtered(lambda l: l.credit):
            lines.reconcile()
            log("reconciled %s: %d lines" % (code, len(lines)))
    report("after")
elif draft:
    log("report only -- set CLR_POST=1 to post")

if DRY or not POST:
    env.cr.rollback()
    log("rolled back -- no changes committed")
else:
    env.cr.commit()
    log("committed")
