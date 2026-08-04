# Execute the July-2026 clearing plan built by 78_prep_clearing_juli.py.
#
#   CLR_JSON=/tmp/clearing_juli.json \
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/79_clearing_juli.py
#
# Everything is created as DRAFT unless CLR_POST=1. Idempotent: the ref guard
# refuses to build a block twice.
#
#   S  bank statement lines July still misses (BCA 21-31, BRI 25-31 Jul), so the
#      suspense account the clearing debits is actually funded by the bank side
#   D  four 23-Jul RIREC lines of PASKAL BANDUNG that carry no OU analytic
#   A  Dr 1103000002 Bank Suspense + Dr 7104000001 MDR / Cr 1106000101..110
#      per store, one journal entry per settlement date
#   B  Dr 1103000002 + Dr 7104000001 / Cr 1106000001 -- June AR collected in July
#   C  Dr 1103019320 (ATS sweep) + Dr 7299012000 (bank charges) / Cr 1103000002
#
# Env flags:
#   CLR_JSON=<path>   plan file (required)
#   CLR_BLOCKS=SDABC  which blocks to build (default all)
#   CLR_POST=1        post the entries and reconcile the POS receivables
#   CLR_DRY=1         build, report, roll back
import json
import os
from collections import defaultdict, OrderedDict

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[clr-jul] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
REF = "EBR-CLR-JULI-2026"
ACC_SUSPENSE = "1103000002"
ACC_MDR = "7104000001"
ACC_AR = "1106000001"
ACC_BCA_MAIN = "1103019320"
ACC_BANK_CHARGE = "7299012000"

PLAN = json.load(open(os.environ["CLR_JSON"]))
BLOCKS = os.environ.get("CLR_BLOCKS", "SDABC").upper()
POST = os.environ.get("CLR_POST") == "1"
DRY = os.environ.get("CLR_DRY") == "1"

env = env(user=1)
company = env["res.company"].browse(COMPANY_ID)
env = env(context=dict(env.context, allowed_company_ids=[COMPANY_ID]))


def account(code):
    acc = env["account.account"].with_company(company).search(
        [("code", "=", code), ("company_ids", "in", COMPANY_ID)], limit=1)
    if not acc:
        raise Exception("account %s not found" % code)
    return acc


def journal(code):
    j = env["account.journal"].search([("code", "=", code), ("company_id", "=", COMPANY_ID)], limit=1)
    if not j:
        raise Exception("journal %s not found" % code)
    return j


ACC = {c: account(c) for c in (ACC_SUSPENSE, ACC_MDR, ACC_AR, ACC_BCA_MAIN, ACC_BANK_CHARGE)}
POS_ACC = {}
for n in range(1, 11):
    code = "11060001%02d" % n
    POS_ACC[code] = account(code)
GLJV = journal(JOURNAL)

analytic = {a.name: a.id for a in env["account.analytic.account"].search([])}


def an_dist(store):
    aid = analytic.get(store)
    if not aid:
        raise Exception("no analytic account for %r" % store)
    return {str(aid): 100.0}


def already(tag):
    return bool(env["account.move"].search_count(
        [("company_id", "=", COMPANY_ID), ("ref", "like", "%s-%s-%%" % (REF, tag))]))


created = OrderedDict()


# ------------------------------------------------------------------ block S
def block_s():
    rows = PLAN["block_s"]
    per_journal = defaultdict(list)
    for r in rows:
        per_journal[r["journal"]].append(r)
    made = env["account.bank.statement.line"]
    for code, lines in per_journal.items():
        jrn = journal(code)
        replace = any(r.get("replace_month") for r in lines)
        domain = [("journal_id", "=", jrn.id),
                  ("date", ">=", "2026-07-01" if replace else min(r["date"] for r in lines)),
                  ("date", "<=", "2026-07-31")]
        existing = env["account.bank.statement.line"].search(domain)
        if existing and not replace:
            log("block S: %s already has %d lines from %s -- skipped"
                % (code, len(existing), min(r["date"] for r in lines)))
            continue
        if existing:
            reconciled = existing.filtered("is_reconciled")
            if reconciled:
                raise Exception("%s: %d July lines already reconciled, refusing to replace"
                                % (code, len(reconciled)))
            statements = existing.statement_id
            log("block S: %s replacing %d incomplete July lines" % (code, len(existing)))
            existing.move_id.button_draft()
            existing.unlink()
            statements.filtered(lambda s: not s.line_ids).unlink()
        stmt = env["account.bank.statement"].create({
            "name": "%s %s..%s (clearing Juli)" % (code, lines[0]["date"], lines[-1]["date"]),
            "journal_id": jrn.id,
        })
        vals = [{
            "journal_id": jrn.id,
            "statement_id": stmt.id,
            "date": r["date"],
            "payment_ref": r["ref"] or "-",
            "amount": r["amount"],
        } for r in lines]
        made |= env["account.bank.statement.line"].create(vals)
        log("block S: %s +%d lines, net %.2f" % (code, len(vals), sum(r["amount"] for r in lines)))
    created["S"] = made


# ------------------------------------------------------------------ block D
def block_d():
    fixed = 0
    for r in PLAN["block_d"]:
        line = env["account.move.line"].browse(r["id"])
        if not line.exists() or line.analytic_distribution:
            continue
        line.write({"analytic_distribution": an_dist(r["analytic"])})
        fixed += 1
    log("block D: %d lines given an OU analytic" % fixed)


# --------------------------------------------------------- POS line matching
def open_posrec():
    """(store, date) -> [line] of still-open July POS receivable debits."""
    lines = env["account.move.line"].search([
        ("company_id", "=", COMPANY_ID),
        ("parent_state", "=", "posted"),
        ("account_id", "in", [a.id for a in POS_ACC.values()]),
        ("date", ">=", "2026-07-01"), ("date", "<=", "2026-07-31"),
        ("debit", ">", 0), ("reconciled", "=", False),
    ])
    by_id = {i: n for n, i in analytic.items()}
    out = defaultdict(list)
    for line in lines:
        aid = next(iter(line.analytic_distribution or {}), None)
        store = by_id.get(int(aid)) if aid else None
        out[(store, str(line.date))].append(line)
        _residual[line.id] = line.amount_residual
    for key in out:
        out[key].sort(key=lambda l: -l.amount_residual)
    return out


_residual = {}  # line id -> not-yet-allocated part of that debit


def allocate(pool, store, date, amount, short):
    """Spread `amount` over the open debits of that store/day, per account.

    The workbook's own tender split disagrees with X70D on a handful of
    store/day combinations, so the split follows Odoo's open lines (largest
    first) and only the store/day total comes from the workbook.
    """
    per_account = defaultdict(float)
    left = round(amount, 2)
    for line in pool.get((store, date), []):
        if left <= 0.004:
            break
        rem = _residual.get(line.id, 0.0)
        if rem <= 0.004:
            continue
        take = round(min(left, rem), 2)
        per_account[line.account_id.id] += take
        _residual[line.id] = round(rem - take, 2)
        left = round(left - take, 2)
    if left > 0.004:
        short.append((store, date, round(left, 2)))
    return per_account


# ------------------------------------------------------------------ block A
def block_a():
    if already("A"):
        log("block A already exists -- skipped")
        return
    pool = open_posrec()
    short = []
    per_date = defaultdict(list)
    for row in PLAN["block_a"]:
        per_date[row["date"]].append(row)
    moves = env["account.move"]
    for sdate in sorted(per_date):
        lines = []
        for row in per_date[sdate]:
            dist = an_dist(row["store"])
            credited = 0.0
            for c in row["credits"]:
                for acc_id, amount in allocate(pool, row["store"], c["date"], c["amount"], short).items():
                    if amount <= 0.004:
                        continue
                    credited += amount
                    lines.append((0, 0, {
                        "account_id": acc_id,
                        "name": "Settlement %s %s (%s)" % (row["bank"], c["date"], row["store"]),
                        "credit": round(amount, 2),
                        "analytic_distribution": dist,
                    }))
            if credited <= 0.004:
                continue
            mdr = round(row["mdr"] * credited / row["gross"], 2) if row["gross"] else 0.0
            lines.append((0, 0, {
                "account_id": ACC[ACC_SUSPENSE].id,
                "name": "Cash in %s %s (%s)" % (row["bank"], sdate, row["store"]),
                "debit": round(credited - mdr, 2),
                "analytic_distribution": dist,
            }))
            if mdr:
                lines.append((0, 0, {
                    "account_id": ACC[ACC_MDR].id,
                    "name": "MDR %s %s (%s)" % (row["bank"], sdate, row["store"]),
                    "debit": mdr,
                    "analytic_distribution": dist,
                }))
        if not lines:
            continue
        moves |= env["account.move"].create({
            "company_id": COMPANY_ID, "journal_id": GLJV.id, "date": sdate,
            "ref": "%s-A-%s" % (REF, sdate), "line_ids": lines,
        })
    created["A"] = moves
    total = sum(moves.mapped("line_ids").mapped("credit"))
    log("block A: %d entries, credit %.2f" % (len(moves), total))
    for s in short[:20]:
        log("   SHORT %s %s %.2f (no open POS receivable left)" % s)
    if len(short) > 20:
        log("   ... %d more short rows" % (len(short) - 20))


# ------------------------------------------------------------------ block B
def block_b():
    if already("B"):
        log("block B already exists -- skipped")
        return
    per_date = defaultdict(list)
    for row in PLAN["block_b"]:
        per_date[row["date"]].append(row)
    moves = env["account.move"]
    for sdate in sorted(per_date):
        lines = []
        for row in per_date[sdate]:
            dist = an_dist(row["store"])
            lines.append((0, 0, {
                "account_id": ACC[ACC_AR].id,
                "name": "Collection AR Juni %s %s (%s)" % (row["bank"], sdate, row["store"]),
                "credit": row["gross"], "analytic_distribution": dist,
            }))
            lines.append((0, 0, {
                "account_id": ACC[ACC_SUSPENSE].id,
                "name": "Cash in %s %s (%s)" % (row["bank"], sdate, row["store"]),
                "debit": row["cash_in"], "analytic_distribution": dist,
            }))
            if row["mdr"]:
                lines.append((0, 0, {
                    "account_id": ACC[ACC_MDR].id,
                    "name": "MDR %s %s (%s)" % (row["bank"], sdate, row["store"]),
                    "debit": row["mdr"], "analytic_distribution": dist,
                }))
        moves |= env["account.move"].create({
            "company_id": COMPANY_ID, "journal_id": GLJV.id, "date": sdate,
            "ref": "%s-B-%s" % (REF, sdate), "line_ids": lines,
        })
    created["B"] = moves
    log("block B: %d entries, credit %.2f" % (len(moves), sum(moves.mapped("line_ids").mapped("credit"))))


# ------------------------------------------------------------------ block C
def block_c():
    if already("C"):
        log("block C already exists -- skipped")
        return
    per_date = defaultdict(list)
    for row in PLAN["block_c"]:
        per_date[row["date"]].append(row)
    moves = env["account.move"]
    for sdate in sorted(per_date):
        lines = []
        for row in per_date[sdate]:
            amount = abs(row["amount"])
            target = ACC[ACC_BANK_CHARGE] if row["kind"] == "BANK ADMIN" else ACC[ACC_BCA_MAIN]
            lines.append((0, 0, {"account_id": target.id, "name": row["desc"][:120] or row["kind"],
                                 "debit": amount}))
            lines.append((0, 0, {"account_id": ACC[ACC_SUSPENSE].id,
                                 "name": "%s %s" % (row["kind"], sdate), "credit": amount}))
        moves |= env["account.move"].create({
            "company_id": COMPANY_ID, "journal_id": GLJV.id, "date": sdate,
            "ref": "%s-C-%s" % (REF, sdate), "line_ids": lines,
        })
    created["C"] = moves
    log("block C: %d entries, %.2f" % (len(moves), sum(moves.mapped("line_ids").mapped("debit"))))


ORDER = [("S", block_s), ("D", block_d), ("A", block_a), ("B", block_b), ("C", block_c)]
for tag, fn in ORDER:
    if tag in BLOCKS:
        fn()

moves = env["account.move"]
for tag, rec in created.items():
    if rec._name == "account.move":
        moves |= rec

if POST and moves:
    moves.action_post()
    log("posted %d entries" % len(moves))
    # reconcile the POS receivables per account (no partner on either side)
    for code, acc in POS_ACC.items():
        lines = env["account.move.line"].search([
            ("company_id", "=", COMPANY_ID), ("parent_state", "=", "posted"),
            ("account_id", "=", acc.id), ("reconciled", "=", False),
            ("date", ">=", "2026-07-01"), ("date", "<=", "2026-07-31"),
        ])
        if len(lines) > 1 and lines.filtered(lambda l: l.credit):
            lines.reconcile()
    log("POS receivable reconciled")
elif moves:
    log("%d entries left in DRAFT (set CLR_POST=1 to post)" % len(moves))

for code in (ACC_SUSPENSE, ACC_MDR, ACC_AR, ACC_BCA_MAIN):
    acc = ACC[code]
    env.cr.execute(
        """select coalesce(sum(debit - credit), 0) from account_move_line
           where account_id = %s and parent_state = 'posted' and date < '2026-08-01'""", (acc.id,))
    log("balance %s = %.2f" % (code, env.cr.fetchone()[0]))

env.cr.execute(
    """select coalesce(sum(aml.amount_residual), 0), count(*)
       from account_move_line aml
       where aml.account_id in %s and aml.parent_state = 'posted' and not aml.reconciled
         and aml.date between '2026-07-01' and '2026-07-31'""",
    (tuple(a.id for a in POS_ACC.values()),))
residual, count = env.cr.fetchone()
log("POS receivable Juli still open: %.2f on %d lines" % (residual, count))

if DRY:
    env.cr.rollback()
    log("DRY -- rolled back")
else:
    env.cr.commit()
    log("committed")
