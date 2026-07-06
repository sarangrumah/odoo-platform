# Load the EBR 2026 GENERAL LEDGER detail as per-voucher journal entries (run via odoo shell).
#   docker cp scripts/tenants/levis/gl_ebr.csv odoo19-platform-odoo:/tmp/levis/gl_ebr.csv
#   docker exec -i odoo19-platform-odoo odoo shell -d rnd_levis --no-http < scripts/tenants/levis/61_load_gl.py
#
# IMPORTANT — data prerequisite:
#   The original "GL EBR 2026" sheet is SINGLE-SIDED: each row carries only a debit OR a
#   credit, the contra account is absent (sum of debits != sum of credits), and only ~5% of
#   rows have a Document No. Such data CANNOT form balanced Odoo journal entries.
#   This script expects a CORRECTED 2-sided export where every voucher (grouped by Document
#   No) carries both legs and nets to zero. Each voucher -> one balanced account.move.
#
# Fallback: if a corrected export is unavailable, set GL_ALLOW_FALLBACK=1 to synthesize the
#   missing contra leg from CONTRA_MAP (per Transaction Type). Reconstructed, not original —
#   confirm the mapping with finance before relying on it.
#
# Env flags:
#   GL_DRY=1              -> build & report, roll back instead of committing
#   GL_ALLOW_FALLBACK=1   -> synthesize contra legs for unbalanced vouchers via CONTRA_MAP
#   GL_LIMIT=<n>          -> only process the first n vouchers (smoke test)
import csv
import os
from collections import defaultdict, OrderedDict
from datetime import datetime

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[gl] " + m)

CSV_PATH = "/tmp/levis/gl_ebr.csv"
COMPANY_ID = 1
DRY = os.environ.get("GL_DRY") == "1"
ALLOW_FALLBACK = os.environ.get("GL_ALLOW_FALLBACK") == "1"
LIMIT = int(os.environ.get("GL_LIMIT") or 0)

# Journal per Transaction Type. Values are journal CODES already present in the DB
# (custom_levis_localization seeds sale/purchase/bank/general journals). Adjust to taste.
JOURNAL_BY_TYPE = {
    "Sales Invoice": "INV",
    "Sales Receipt": "BNK1",
    "Purchase Invoice Non-Trade": "BILL",
    "Purchase Invoice Trade": "BILL",
    "Purchase Payment": "BNK1",
    "Cash & Bank": "BNK1",
    "General Journal": "MISC",
    "Opening Balance 2026": "EBRTB",
}
DEFAULT_JOURNAL = "MISC"

# Fallback contra account CODE per Transaction Type (only used with GL_ALLOW_FALLBACK=1).
# CONFIRM WITH FINANCE before enabling.
CONTRA_MAP = {
    "Sales Invoice": "4101000001",        # revenue  (credit side of a receivable debit)
    "Sales Receipt": "1106000001",        # trade receivable (credit side of a bank debit)
    "Purchase Invoice Non-Trade": "2103300001",  # non-trade payable
    "Purchase Payment": "1103019320",     # main bank
    "Cash & Bank": "1103019320",          # main bank
}

company = env["res.company"].browse(COMPANY_ID)
Acc = env["account.account"].with_company(company)
rounding = company.currency_id.rounding or 0.01
_code2acc = {a.code: a for a in Acc.search([]) if a.code}
_journals = {j.code: j for j in env["account.journal"].search([("company_id", "=", company.id)])}
log("accounts=%d journals=%s dry=%s fallback=%s"
    % (len(_code2acc), sorted(_journals), DRY, ALLOW_FALLBACK))


def resolve_acc(code):
    a = _code2acc.get(code)
    if not a:
        raise KeyError("account %s not found (run 30_fix_coa.py first)" % code)
    return a


def resolve_journal(txn_type):
    code = JOURNAL_BY_TYPE.get(txn_type, DEFAULT_JOURNAL)
    j = _journals.get(code) or _journals.get(DEFAULT_JOURNAL)
    if not j:
        raise KeyError("no journal for %r (code %s) and no %s fallback" % (txn_type, code, DEFAULT_JOURNAL))
    return j


# ---- business partner cache (match by name, else create) ----
_partner_cache = {}


def resolve_partner(name):
    name = (name or "").strip()
    if not name:
        return False
    # strip leading vendor code like "1060 - PT Era Sukses A"
    disp = name.split(" - ", 1)[1] if " - " in name and name.split(" - ", 1)[0].strip().isdigit() else name
    key = disp.lower()
    if key in _partner_cache:
        return _partner_cache[key]
    p = env["res.partner"].search([("name", "=", disp)], limit=1)
    if not p:
        p = env["res.partner"].create({"name": disp, "company_id": False})
    _partner_cache[key] = p.id
    return p.id


# ---- store -> analytic account (reuse per-store analytic seeded by 40_setup_trade_ou.py) ----
_analytic_cache = {}
AnalyticModel = env["account.analytic.account"] if "account.analytic.account" in env else None


def resolve_analytic(store):
    store = (store or "").strip()
    if not store or store.lower() == "head quarter" or AnalyticModel is None:
        return None
    if store in _analytic_cache:
        return _analytic_cache[store]
    a = AnalyticModel.search([("name", "=", store)], limit=1)
    _analytic_cache[store] = a.id if a else None
    if not a:
        log("WARN no analytic for store %r (line posted without analytic)" % store)
    return _analytic_cache[store]


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


# ---- read + group GL by document ----
with open(CSV_PATH) as f:
    rows = list(csv.DictReader(f))
log("GL rows: %d" % len(rows))

groups = OrderedDict()
for i, row in enumerate(rows):
    doc = (row.get("doc_no") or "").strip()
    key = doc or ("__noDoc__%s_%s" % (row.get("period", ""), i))  # ungrouped rows -> own voucher
    groups.setdefault(key, []).append(row)
log("vouchers (grouped by Document No): %d" % len(groups))

posted = skipped = fallback_used = 0
items = list(groups.items())
if LIMIT:
    items = items[:LIMIT]

for key, glines in items:
    ref = key if not key.startswith("__noDoc__") else (glines[0].get("invoice_ref") or key)
    txn_type = glines[0].get("txn_type", "")
    mdate = parse_date(glines[0].get("posting_date")) or parse_date(glines[0].get("doc_date"))
    if not mdate:
        log("SKIP %s: no posting date" % ref); skipped += 1; continue
    if env["account.move"].search_count([("ref", "=", ref), ("company_id", "=", company.id)]):
        skipped += 1; continue

    legs = []          # (account_id, name, signed_amount, analytic_id, partner_id)
    total = 0.0
    try:
        for row in glines:
            amt = r(row.get("d")) - r(row.get("c"))
            if amt == 0:
                continue
            legs.append([
                resolve_acc(row["account"]).id,
                (row.get("notes") or row.get("account_desc") or "")[:200],
                amt,
                resolve_analytic(row.get("store")),
                resolve_partner(row.get("business_partner")),
            ])
            total += amt
    except KeyError as e:
        log("SKIP %s: %s" % (ref, e)); skipped += 1; continue

    total = r(total)
    if total != 0:
        if ALLOW_FALLBACK and txn_type in CONTRA_MAP:
            legs.append([resolve_acc(CONTRA_MAP[txn_type]).id,
                         "Contra (%s)" % txn_type, -total, None, False])
            fallback_used += 1
        else:
            log("SKIP %s: unbalanced by %s (txn=%r; set GL_ALLOW_FALLBACK=1 to synthesize)"
                % (ref, total, txn_type))
            skipped += 1
            continue

    line_ids = []
    for acc_id, name, amt, an_id, pid in legs:
        vals = {"account_id": acc_id, "name": name or "/",
                "debit": amt if amt > 0 else 0.0, "credit": -amt if amt < 0 else 0.0}
        if pid:
            vals["partner_id"] = pid
        if an_id:
            vals["analytic_distribution"] = {str(an_id): 100.0}
        line_ids.append((0, 0, vals))

    move = env["account.move"].create({
        "journal_id": resolve_journal(txn_type).id, "date": mdate, "ref": ref,
        "company_id": company.id, "move_type": "entry", "line_ids": line_ids,
    })
    move.action_post()
    posted += 1
    if posted % 200 == 0:
        env.cr.commit(); log("... posted %d" % posted)

log("==== SUMMARY: posted=%d skipped=%d fallback_contra=%d ====" % (posted, skipped, fallback_used))
if DRY:
    env.cr.rollback(); log("GL_DRY=1 -> rolled back")
else:
    env.cr.commit(); log("committed")
