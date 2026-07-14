# Load the EBR 2026 GENERAL LEDGER (Jan-Jun) detail as per-voucher journal entries.
#
#   docker cp scripts/tenants/levis/gl_ebr_2026.csv odoo19-platform-odoo:/tmp/levis/gl_ebr_2026.csv
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/62_load_gl_2026.py
#
# Source: "2026 - EBR - TB and GL - BegBal Odoo.xlsx" / sheet "GL EBR 2026".
#
# Differs from 61_load_gl.py, which grouped vouchers by Document No. In this workbook only
# 150 of 3199 lines carry a Document No; the real voucher key is the "No" column (filled
# down over its lines). Grouped that way all 1185 vouchers balance to zero exactly.
#
# The GL carries MOVEMENTS ONLY -- TB_beginning(31-Dec-2025) + GL(Jan-Jun) = TB_ending(Jun).
# It contains no revenue (4xxx): the sales side lives in the POS/retail-import entries.
#
# Env flags:
#   GL_DRY=1        -> build, report, roll back
#   GL_DROP_EBRTB=1 -> delete the pre-existing aggregate EBRTB entries first
#   GL_LIMIT=<n>    -> only the first n vouchers
import csv
import os
from collections import OrderedDict
from datetime import datetime

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[gl2026] " + m)

CSV_PATH = "/tmp/levis/gl_ebr_2026.csv"
COMPANY_ID = 1
REF_PREFIX = "EBR-GL-2026/"
DRY = os.environ.get("GL_DRY") == "1"
DROP_EBRTB = os.environ.get("GL_DROP_EBRTB") == "1"
LIMIT = int(os.environ.get("GL_LIMIT") or 0)

JOURNAL_BY_TYPE = {
    "Opening Balance 2026": "EBRTB",
    "General Journal": "GLJV",
    "Purchase Invoice Non-Trade": "BILL",
    "Purchase Invoice Trade": "BILL",
    "Purchase Payment": "BNK1",
    "Cash & Bank": "BNK1",
    "Sales Receipt": "BNK1",
}
DEFAULT_JOURNAL = "GLJV"

# GL store label -> analytic account name seeded by 40_setup_trade_ou.py / 41_normalize_ou.py.
STORE_TO_ANALYTIC = {
    "Head Quarter": "EBR - HEAD OFFICE",
    "Galaxy Mall 3 Surabaya": "OLS SES - GALAXY MALL 3",
    "Paris Van Java Bandung": "OLS SES - PARIS VAN JAVA",
    "Tunjungan Plaza 3 Surabaya": "OLS SES - TUNJUNGAN PLAZA 3",
}

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
rounding = company.currency_id.rounding or 0.01

_code2acc = {}
for a in env["account.account"].with_company(company).search([]):
    if a.code:
        _code2acc[a.code] = a
_journals = {j.code: j for j in env["account.journal"].search([("company_id", "=", company.id)])}
_analytics = {a.name: a.id for a in env["account.analytic.account"].search([])}

log(
    "accounts=%d journals=%d analytics=%d dry=%s drop_ebrtb=%s"
    % (len(_code2acc), len(_journals), len(_analytics), DRY, DROP_EBRTB)
)

# ---- unlock the period (restored in the finally block) ----
saved_lock = company.fiscalyear_lock_date
if saved_lock:
    company.sudo().write({"fiscalyear_lock_date": False})
    log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)


def restore_lock():
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": saved_lock})
        log("fiscalyear_lock_date restored to %s" % saved_lock)


try:
    # ---- drop the aggregate TB entries the GL detail supersedes ----
    if DROP_EBRTB:
        ebrtb = _journals.get("EBRTB")
        old = Move.search([("journal_id", "=", ebrtb.id), ("company_id", "=", company.id)]) if ebrtb else Move
        if old:
            log("deleting %d pre-existing EBRTB entries: %s" % (len(old), ", ".join(old.mapped("name"))))
            old.filtered(lambda m: m.state == "posted").button_draft()
            old.write({"name": "/"})  # avoid the sequence-gap guard on unlink
            old.unlink()

    def parse_date(s):
        s = (s or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        return None

    def r(x):
        try:
            return round(float(x) / rounding) * rounding
        except (TypeError, ValueError):
            return 0.0

    _partner_cache = {}

    def resolve_partner(name):
        name = (name or "").strip()
        if not name:
            return False
        disp = name.split(" - ", 1)[1] if " - " in name and name.split(" - ", 1)[0].strip().isdigit() else name
        key = disp.lower()
        if key not in _partner_cache:
            p = env["res.partner"].search([("name", "=", disp)], limit=1)
            if not p:
                p = env["res.partner"].create({"name": disp, "company_id": False})
            _partner_cache[key] = p.id
        return _partner_cache[key]

    _warned_store = set()

    def resolve_analytic(store):
        store = (store or "").strip()
        if not store:
            return None
        name = STORE_TO_ANALYTIC.get(store, "OLS SES - " + store.upper())
        aid = _analytics.get(name)
        if not aid and store not in _warned_store:
            _warned_store.add(store)
            log("WARN no analytic for store %r (-> %r); lines posted without analytic" % (store, name))
        return aid

    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))
    groups = OrderedDict()
    for row in rows:
        groups.setdefault(row["voucher"], []).append(row)
    log("GL rows=%d vouchers=%d" % (len(rows), len(groups)))

    items = list(groups.items())
    if LIMIT:
        items = items[:LIMIT]

    posted = skipped = 0
    for vno, glines in items:
        ref = REF_PREFIX + str(vno)
        mdate = parse_date(glines[0].get("posting_date")) or parse_date(glines[0].get("doc_date"))
        txn_type = glines[0].get("txn_type", "")
        if not mdate:
            log("SKIP %s: no posting date" % ref)
            skipped += 1
            continue
        if Move.search_count([("ref", "=", ref), ("company_id", "=", company.id)]):
            skipped += 1
            continue

        line_ids, total, missing = [], 0.0, None
        for row in glines:
            acc = _code2acc.get(row["account"])
            if not acc:
                missing = row["account"]
                break
            amt = r(row.get("d")) - r(row.get("c"))
            if amt == 0:
                continue
            vals = {
                "account_id": acc.id,
                "name": (row.get("notes") or row.get("account_desc") or "/")[:200],
                "debit": amt if amt > 0 else 0.0,
                "credit": -amt if amt < 0 else 0.0,
            }
            pid = resolve_partner(row.get("business_partner"))
            if pid:
                vals["partner_id"] = pid
            aid = resolve_analytic(row.get("store"))
            if aid:
                vals["analytic_distribution"] = {str(aid): 100.0}
            line_ids.append((0, 0, vals))
            total += amt

        if missing:
            log("SKIP %s: account %s not in COA" % (ref, missing))
            skipped += 1
            continue
        if not line_ids:
            skipped += 1
            continue
        if r(total) != 0:
            log("SKIP %s: unbalanced by %s (txn=%r)" % (ref, r(total), txn_type))
            skipped += 1
            continue

        jcode = JOURNAL_BY_TYPE.get(txn_type, DEFAULT_JOURNAL)
        journal = _journals.get(jcode) or _journals[DEFAULT_JOURNAL]
        doc = (glines[0].get("doc_no") or "").strip()
        move = Move.create(
            {
                "journal_id": journal.id,
                "date": mdate,
                "ref": ref,
                "company_id": company.id,
                "move_type": "entry",
                "narration": "%s | voucher %s%s" % (txn_type, vno, (" | doc " + doc) if doc else ""),
                "line_ids": line_ids,
            }
        )
        move.action_post()
        posted += 1
        if posted % 200 == 0:
            log("... posted %d" % posted)

    log("==== SUMMARY: posted=%d skipped=%d ====" % (posted, skipped))
finally:
    restore_lock()

if DRY:
    env.cr.rollback()
    log("GL_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
