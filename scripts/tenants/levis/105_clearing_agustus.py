# Execute the August-2026 clearing plan built by 104_prep_clearing_agustus.py.
#
#   CLR_JSON=/tmp/clearing_agustus.json \
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/105_clearing_agustus.py
#
# Everything is created as DRAFT unless CLR_POST=1. Idempotent: the ref guard
# refuses to build a block twice.
#
#   A  settlement of August sales
#      Dr 1103000002 Bank Suspense + Dr 7104000001 MDR / Cr 1106000101..110
#      one entry per settlement date, credits taken from the OPEN AUGUST lines
#      of that store and transaction date
#   B  collection in August of the July receivable still open
#      same posting, but the credit is taken from the OPEN JULY lines of that
#      store -- July's leftovers all carry a 30/31-Jul date after the July
#      clearing reconciled per account, so matching on the transaction date
#      would find nothing
#
# No block C: Finance booked the August ATS sweep by hand (ref "ATS ...",
# Rp 13.918.328.412,70). No block S: the August bank statements are complete.
#
# Env flags:
#   CLR_JSON=<path>   plan file (required)
#   CLR_BLOCKS=AB     which blocks to build (default both)
#   CLR_POST=1        post the entries and reconcile the POS receivables
#   CLR_DRY=1         build, report, roll back
import json
import os
from collections import defaultdict, OrderedDict

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[clr-agu] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
REF = "EBR-CLR-AGUSTUS-2026"
ACC_SUSPENSE = "1103000002"
ACC_MDR = "7104000001"
AUG = ("2026-08-01", "2026-08-31")
JUL = ("2026-07-01", "2026-07-31")

PLAN = json.load(open(os.environ["CLR_JSON"]))
BLOCKS = os.environ.get("CLR_BLOCKS", "AB").upper()
POST = os.environ.get("CLR_POST") == "1"
DRY = os.environ.get("CLR_DRY") == "1"

env = env(user=1)
company = env["res.company"].browse(COMPANY_ID)
env = env(context=dict(env.context, allowed_company_ids=[COMPANY_ID]))


def account(code):
    acc = (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", COMPANY_ID)], limit=1)
    )
    if not acc:
        raise Exception("account %s not found" % code)
    return acc


ACC = {c: account(c) for c in (ACC_SUSPENSE, ACC_MDR)}
POS_ACC = {"11060001%02d" % n: account("11060001%02d" % n) for n in range(1, 11)}
GLJV = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", COMPANY_ID)], limit=1)
if not GLJV:
    raise Exception("journal %s not found" % JOURNAL)

analytic = {a.name: a.id for a in env["account.analytic.account"].search([])}


def an_dist(store):
    aid = analytic.get(store)
    if not aid:
        raise Exception("no analytic account for %r" % store)
    return {str(aid): 100.0}


def already(tag):
    return bool(
        env["account.move"].search_count([("company_id", "=", COMPANY_ID), ("ref", "like", "%s-%s-%%" % (REF, tag))])
    )


created = OrderedDict()
_residual = {}  # line id -> not-yet-allocated part of that debit


def open_posrec(window, by_date):
    """Open POS receivable debits, keyed by (store, date) or by store alone."""
    lines = env["account.move.line"].search(
        [
            ("company_id", "=", COMPANY_ID),
            ("parent_state", "=", "posted"),
            ("account_id", "in", [a.id for a in POS_ACC.values()]),
            ("date", ">=", window[0]),
            ("date", "<=", window[1]),
            ("debit", ">", 0),
            ("reconciled", "=", False),
        ]
    )
    by_id = {i: n for n, i in analytic.items()}
    pool = defaultdict(list)
    for line in lines:
        aid = next(iter(line.analytic_distribution or {}), None)
        store = by_id.get(int(aid)) if aid else None
        pool[(store, str(line.date)) if by_date else store].append(line)
        _residual[line.id] = line.amount_residual
    for key in pool:
        pool[key].sort(key=lambda l: -l.amount_residual)
    return pool


def allocate(pool, key, amount, short, label):
    """Spread `amount` over the open debits behind `key`, split per account.

    The workbook's own tender split disagrees with X70D on a handful of
    store/day combinations, so the split follows Odoo's open lines (largest
    first) and only the total comes from the workbook.
    """
    per_account = defaultdict(float)
    left = round(amount, 2)
    for line in pool.get(key, []):
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
        short.append((label, round(left, 2)))
    return per_account


def build(tag, rows, pool, key_of, label_of, note):
    """One journal entry per settlement date; MDR follows what we could credit."""
    if already(tag):
        log("block %s already exists -- skipped" % tag)
        return
    short = []
    per_date = defaultdict(list)
    for row in rows:
        per_date[row["date"]].append(row)
    moves = env["account.move"]
    for sdate in sorted(per_date):
        lines = []
        for row in per_date[sdate]:
            dist = an_dist(row["store"])
            credited = 0.0
            for c in row["credits"]:
                found = allocate(pool, key_of(row, c), c["amount"], short, label_of(row, c))
                for acc_id, amount in found.items():
                    if amount <= 0.004:
                        continue
                    credited += amount
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "account_id": acc_id,
                                "name": "%s %s %s (%s)" % (note, row["bank"], c["date"], row["store"]),
                                "credit": round(amount, 2),
                                "analytic_distribution": dist,
                            },
                        )
                    )
            if credited <= 0.004:
                continue
            mdr = round(row["mdr"] * credited / row["gross"], 2) if row["gross"] else 0.0
            lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": ACC[ACC_SUSPENSE].id,
                        "name": "Cash in %s %s (%s)" % (row["bank"], sdate, row["store"]),
                        "debit": round(credited - mdr, 2),
                        "analytic_distribution": dist,
                    },
                )
            )
            if mdr:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "account_id": ACC[ACC_MDR].id,
                            "name": "MDR %s %s (%s)" % (row["bank"], sdate, row["store"]),
                            "debit": mdr,
                            "analytic_distribution": dist,
                        },
                    )
                )
        if not lines:
            continue
        moves |= env["account.move"].create(
            {
                "company_id": COMPANY_ID,
                "journal_id": GLJV.id,
                "date": sdate,
                "ref": "%s-%s-%s" % (REF, tag, sdate),
                "line_ids": lines,
            }
        )
    created[tag] = moves
    log("block %s: %d entries, credit %.2f" % (tag, len(moves), sum(moves.mapped("line_ids").mapped("credit"))))
    for s in short[:20]:
        log("   SHORT %s %.2f (no open POS receivable left)" % s)
    if len(short) > 20:
        log("   ... %d more short rows, total %.2f" % (len(short) - 20, sum(s[1] for s in short)))


if "A" in BLOCKS:
    build(
        "A",
        PLAN["block_a"],
        open_posrec(AUG, True),
        lambda row, c: (row["store"], c["date"]),
        lambda row, c: "%s %s" % (row["store"], c["date"]),
        "Settlement",
    )
if "B" in BLOCKS:
    build(
        "B",
        PLAN["block_b"],
        open_posrec(JUL, False),
        lambda row, c: row["store"],
        lambda row, c: "%s (AR Juli %s)" % (row["store"], c["date"]),
        "Collection AR Juli",
    )

moves = env["account.move"]
for rec in created.values():
    moves |= rec

if POST and moves:
    moves.action_post()
    log("posted %d entries" % len(moves))
    for tag, window in (("A", AUG), ("B", JUL)):
        rec = created.get(tag)
        if not rec:
            continue
        for acc in POS_ACC.values():
            credits = rec.line_ids.filtered(lambda l, a=acc: l.account_id == a and l.credit)
            if not credits:
                continue
            debits = env["account.move.line"].search(
                [
                    ("company_id", "=", COMPANY_ID),
                    ("parent_state", "=", "posted"),
                    ("account_id", "=", acc.id),
                    ("date", ">=", window[0]),
                    ("date", "<=", window[1]),
                    ("debit", ">", 0),
                    ("reconciled", "=", False),
                ]
            )
            if debits:
                (credits | debits).reconcile()
        log("block %s: POS receivable reconciled" % tag)
elif moves:
    log("%d entries left in DRAFT (set CLR_POST=1 to post)" % len(moves))

env.flush_all()  # the reports below read raw SQL; ORM writes must hit the cursor first

for code in (ACC_SUSPENSE, ACC_MDR):
    env.cr.execute(
        """select coalesce(sum(debit - credit), 0) from account_move_line
           where account_id = %s and parent_state = 'posted' and date <= '2026-08-31'""",
        (ACC[code].id,),
    )
    log("balance %s per 31-Agu = %.2f" % (code, env.cr.fetchone()[0]))

for name, window in (("Juli", JUL), ("Agustus", AUG)):
    env.cr.execute(
        """select coalesce(sum(amount_residual), 0), count(*) from account_move_line
           where account_id in %s and parent_state = 'posted' and not reconciled
             and debit > 0 and date between %s and %s""",
        (tuple(a.id for a in POS_ACC.values()), window[0], window[1]),
    )
    residual, count = env.cr.fetchone()
    log("POS receivable %s masih open: %.2f pada %d baris" % (name, residual, count))

if DRY:
    env.cr.rollback()
    log("DRY -- rolled back")
else:
    env.cr.commit()
    log("committed")
