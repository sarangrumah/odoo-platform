# Build the June-2026 AR adjustment entries agreed with FICO/Accounting on 29-Jul-2026.
#
# Four entries, all dated 30-Jun-2026, all created as DRAFT so Accounting can review
# them before posting. Idempotent: refuses to run twice via the ref guard.
#
#   1. CLEARING   Dr 2103100003 / Cr 1106000001 per Operating Unit
#   2. REALOKASI  move deposit between OUs (no effect on any account balance):
#                 head office bank-in without store info -> the 3 stores Finance
#                 identified, and 2 settlements booked against the wrong store
#   3. MDR        Dr 7104000001 / Cr 1106000001 -- MDR Accounting had not journalised
#   4. SALESMANUAL Dr 1106000001 / Cr <revenue account> -- manual sales per Finance's
#                 reconciliation. Skipped unless SALES_MANUAL_ACCOUNT is given, because
#                 the counter account (and VAT treatment) needs Accounting's sign-off.
#
# The per-store figures come from FICO's workbook
# "EBR - Check Selisih Outstanding AR Finance vs Accounting Juni 2026.xlsx" and are
# reproduced by scripts/tenants/levis/67_rekon_ar_juni_final.py.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/69_ar_adjustments_juni.py
#
# Env flags:  ADJ_DRY=1              -> build, report, roll back
#             ADJ_POST=1             -> also post the entries (clears/restores the lock date)
#             SALES_MANUAL_ACCOUNT=  -> revenue account code for entry 4
#             ADJ_DATE=YYYY-MM-DD    -> posting date (default 2026-06-30)
#             ADJ_CUTOFF=YYYY-MM-DD  -> as-of date for reading the ledger (default = ADJ_DATE)
#
# ADJ_DATE and ADJ_CUTOFF are separate on purpose. The client may want June left
# untouched and the adjustment recognised in a later period -- but the figures must
# still be measured at the June close, not at the posting date, or the clearing would
# be computed against balances that have moved on since.
import os
from collections import OrderedDict

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[ar-adj] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
DATE = os.environ.get("ADJ_DATE", "2026-06-30")
CUTOFF = os.environ.get("ADJ_CUTOFF", DATE)
REF_PREFIX = "EBR-ADJ-AR-JUNI-2026"
ACC_AR = "1106000001"
ACC_DEPOSIT = "2103100003"
ACC_MDR = "7104000001"
NO_STORE_OU = "EBR - HEAD OFFICE"

DRY = os.environ.get("ADJ_DRY") == "1"
POST = os.environ.get("ADJ_POST") == "1"
SALES_MANUAL_ACCOUNT = os.environ.get("SALES_MANUAL_ACCOUNT", "").strip()

# --- FICO figures ----------------------------------------------------------
# bank-in Finance could not attribute to a store by the 9-Jul closing deadline
NO_STORE_SPLIT = OrderedDict(
    [
        ("OLS SES - GANDARIA CITY", 5140545),
        ("OLS SES - TRANS STUDIO CIBUBUR", 1798898),
        ("OLS SES - GRAND INDONESIA", 1),
    ]
)
# settlements booked against the wrong store (FICO column Z): (from, to, amount)
PLUS_MINUS = [
    ("OLS SES - METROPOLITAN MALL BEKASI", "OLS SES - GRAND METROPOLITAN BEKASI", 1397725),
    ("OLS SES - TRANS STUDIO CIBUBUR", "OLS SES - TRANS STUDIO MALL BANDUNG", 1275795),
]
# MDR Accounting had not journalised in June (FICO column V)
MDR = OrderedDict(
    [
        ("OLS SES - CENTRAL PARK", 110355),
        ("OLS SES - SENAYAN CITY", 69225),
        ("OLS SES - GALAXY MALL 3", 58595),
        ("OLS SES - PONDOK INDAH MALL 2", 54142),
        ("OLS SES - PAKUWON MALL SURABAYA", 42472),
        ("OLS SES - PONDOK INDAH MALL 1", 39613),
        ("OLS SES - GANDARIA CITY", 38880),
        ("OLS SES - PLAZA SENAYAN", 37706),
        ("OLS SES - PARIS VAN JAVA", 33431),
        ("OLS SES - SUMMARECON MALL BANDUNG", 19304),
        ("OLS SES - KELAPA GADING MALL", 17033),
        ("OLS SES - TRANS STUDIO CIBUBUR", 2702),
        ("OLS SES - GRAND METROPOLITAN BEKASI", 2100),
        ("OLS SES - TUNJUNGAN PLAZA 3", 881),
        ("OLS SES - BANDUNG INDAH PLAZA", 826),
    ]
)
# manual sales per Finance's reconciliation (FICO column X)
SALES_MANUAL = OrderedDict(
    [
        ("OLS SES - METROPOLITAN MALL BEKASI", 9052000),
        ("OLS SES - PARIS VAN JAVA", 3756280),
        ("OLS SES - CENTRAL PARK", 1799800),
    ]
)
# trade receivable per store per Accounting (FICO column J) -- caps the clearing
AR_PER_OU = OrderedDict(
    [
        ("OLS SES - PONDOK INDAH MALL 2", 201520007),
        ("OLS SES - TUNJUNGAN PLAZA 3", 171268254),
        ("OLS SES - SENAYAN CITY", 143248146),
        ("OLS SES - SUMMARECON MALL BANDUNG", 79738328),
        ("OLS SES - TRANS STUDIO MALL BANDUNG", 68961541),
        ("OLS SES - TRANS STUDIO CIBUBUR", 63976787),
        ("OLS SES - PARIS VAN JAVA", 61844775),
        ("OLS SES - CENTRAL PARK", 47490708),
        ("OLS SES - PAKUWON MALL SURABAYA", 26483815),
        ("OLS SES - GANDARIA CITY", 23746492),
        ("OLS SES - PLAZA SENAYAN", 23082597),
        ("OLS SES - KELAPA GADING MALL", 22955539),
        ("OLS SES - PONDOK INDAH MALL 1", 21089507),
        ("OLS SES - GALAXY MALL 3", 18066675),
        ("OLS SES - METROPOLITAN MALL BEKASI", 14674850),
        ("OLS SES - MALL OF INDONESIA", 9497475),
        ("OLS SES - AEON BSD CITY", 9167382),
        ("OLS SES - LOTTE SHOPPING AVENUE", 7517015),
        ("OLS SES - BANDUNG INDAH PLAZA", 6464970),
        ("OLS SES - GRAND METROPOLITAN BEKASI", 4952425),
        ("OLS SES - GRAND INDONESIA", 0),
    ]
)

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
journal = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", company.id)], limit=1)
if not journal:
    raise SystemExit("journal %s not found" % JOURNAL)
if Move.search_count([("ref", "like", REF_PREFIX + "%"), ("company_id", "=", company.id)]):
    raise SystemExit("adjustment entries (%s*) already exist -- nothing to do" % REF_PREFIX)

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}
for code in (ACC_AR, ACC_DEPOSIT, ACC_MDR):
    if code not in _code2acc:
        raise SystemExit("account %s not in COA" % code)

_ou = {a.name: a for a in env["account.analytic.account"].search([])}
missing = [
    o
    for o in set(
        list(NO_STORE_SPLIT)
        + list(MDR)
        + list(SALES_MANUAL)
        + list(AR_PER_OU)
        + [NO_STORE_OU]
        + [x for p in PLUS_MINUS for x in p[:2]]
    )
    if o not in _ou
]
if missing:
    raise SystemExit("analytic accounts not found: %s" % ", ".join(sorted(missing)))
ad = lambda ou: {str(_ou[ou].id): 100.0}


def line(code, name, amount, ou=None):
    """amount > 0 -> debit, amount < 0 -> credit"""
    vals = {
        "account_id": _code2acc[code].id,
        "name": name,
        "debit": amount if amount > 0 else 0.0,
        "credit": -amount if amount < 0 else 0.0,
    }
    if ou:
        vals["analytic_distribution"] = ad(ou)
    return (0, 0, vals)


def create(suffix, narration, lines):
    if not lines:
        return None
    if DATE != CUTOFF:
        narration += (
            " Dibukukan tanggal %s (bukan %s) karena angka Juni tidak boleh berubah; "
            "seluruh nilai tetap diukur pada posisi %s." % (DATE, CUTOFF, CUTOFF)
        )
    move = Move.create(
        {
            "journal_id": journal.id,
            "date": DATE,
            "ref": "%s-%s" % (REF_PREFIX, suffix),
            "company_id": company.id,
            "move_type": "entry",
            "narration": narration,
            "line_ids": lines,
        }
    )
    # draft moves have no sequence number yet -- fall back to the ref
    log(
        "%s %s: %d lines, debit %s"
        % (suffix, move.name or move.ref, len(move.line_ids), sum(move.line_ids.mapped("debit")))
    )
    return move


# --- corrected TBFU per OU, from the ledger + FICO's re-assignments ---------
env.cr.execute(
    """select coalesce(aa.name->>'en_US','(tanpa OU)'), round(sum(l.credit-l.debit)::numeric,2)
         from account_move_line l
         join account_account a on a.id=l.account_id
         join account_move m on m.id=l.move_id
         left join lateral (select (jsonb_object_keys(l.analytic_distribution))::int aid) k on true
         left join account_analytic_account aa on aa.id=k.aid
        where l.account_id=%s and m.state='posted' and m.date <= %s
        group by 1""",
    (_code2acc[ACC_DEPOSIT].id, CUTOFF),
)
tbfu = {name: float(amt) for name, amt in env.cr.fetchall()}
log("posting date %s, figures measured as of %s" % (DATE, CUTOFF))
log("deposit per OU read from ledger: %d OU, total %s" % (len(tbfu), round(sum(tbfu.values()), 2)))

for ou, amt in NO_STORE_SPLIT.items():
    tbfu[ou] = tbfu.get(ou, 0.0) + amt
    tbfu[NO_STORE_OU] = tbfu.get(NO_STORE_OU, 0.0) - amt
for src, dst, amt in PLUS_MINUS:
    tbfu[src] = tbfu.get(src, 0.0) - amt
    tbfu[dst] = tbfu.get(dst, 0.0) + amt

moves = []

# --- 2. reallocation (built first so the clearing reads a corrected picture) --
realokasi_lines = []
for ou, amt in NO_STORE_SPLIT.items():
    realokasi_lines.append(line(ACC_DEPOSIT, "Realokasi bank-in tanpa info toko", amt, NO_STORE_OU))
    realokasi_lines.append(line(ACC_DEPOSIT, "Realokasi bank-in tanpa info toko -> %s" % ou, -amt, ou))
for src, dst, amt in PLUS_MINUS:
    realokasi_lines.append(line(ACC_DEPOSIT, "Koreksi toko settlement (dari %s)" % src, amt, src))
    realokasi_lines.append(line(ACC_DEPOSIT, "Koreksi toko settlement (ke %s)" % dst, -amt, dst))
moves.append(
    create(
        "REALOKASI",
        "Realokasi Operating Unit atas Deposit from customer trade sesuai rekon final FICO "
        "(bank-in tanpa info toko + settlement tercatat di toko yang salah). "
        "Tidak mengubah saldo akun mana pun.",
        realokasi_lines,
    )
)

# --- 3. MDR ---------------------------------------------------------------
mdr_lines = []
for ou, amt in MDR.items():
    mdr_lines.append(line(ACC_MDR, "MDR Juni 2026 %s" % ou, amt, ou))
    mdr_lines.append(line(ACC_AR, "MDR Juni 2026 %s" % ou, -amt, ou))
moves.append(
    create(
        "MDR",
        "MDR Juni 2026 yang belum dijurnal Accounting karena file rekonsiliasi AR dari Finance "
        "baru diterima setelah deadline closing 9-Jul-2026.",
        mdr_lines,
    )
)

# --- 4. manual sales ------------------------------------------------------
if SALES_MANUAL_ACCOUNT:
    if SALES_MANUAL_ACCOUNT not in _code2acc:
        raise SystemExit("SALES_MANUAL_ACCOUNT %s not in COA" % SALES_MANUAL_ACCOUNT)
    sm_lines = []
    for ou, amt in SALES_MANUAL.items():
        sm_lines.append(line(ACC_AR, "Penjualan manual Juni 2026 %s" % ou, amt, ou))
        sm_lines.append(line(SALES_MANUAL_ACCOUNT, "Penjualan manual Juni 2026 %s" % ou, -amt, ou))
    moves.append(
        create(
            "SALESMANUAL",
            "Penjualan manual Juni 2026 sesuai rekon Finance yang belum tercatat di Odoo.",
            sm_lines,
        )
    )
else:
    log(
        "SALES_MANUAL_ACCOUNT not set -> entry 4 skipped (total %s pending Accounting sign-off)"
        % sum(SALES_MANUAL.values())
    )

# --- 1. clearing ----------------------------------------------------------
clearing_lines = []
total_clearing = 0.0
for ou in sorted(tbfu, key=lambda o: -tbfu[o]):
    avail = round(tbfu[ou], 2)
    if avail <= 0:
        continue
    if ou not in AR_PER_OU:
        raise SystemExit("OU %s has deposit %s but no AR figure from FICO" % (ou, avail))
    ar_adj = AR_PER_OU[ou] + (SALES_MANUAL.get(ou, 0) if SALES_MANUAL_ACCOUNT else 0) - MDR.get(ou, 0)
    amt = round(min(avail, ar_adj), 2)
    if amt <= 0:
        log("skip %s: piutang terbuka %s < TBFU %s" % (ou, ar_adj, avail))
        continue
    if amt < avail:
        log("cap  %s: clearing %s dari TBFU %s (piutang terbuka %s)" % (ou, amt, avail, ar_adj))
    clearing_lines.append(line(ACC_DEPOSIT, "Clearing piutang penjualan Juni 2026 %s" % ou, amt, ou))
    clearing_lines.append(line(ACC_AR, "Clearing piutang penjualan Juni 2026 %s" % ou, -amt, ou))
    total_clearing += amt
moves.append(
    create(
        "CLEARING",
        "Clearing piutang penjualan Juni 2026 terhadap uang yang sudah diterima "
        "(Deposit from customer trade), per Operating Unit, sesuai rekon final FICO.",
        clearing_lines,
    )
)
log("total clearing %s" % round(total_clearing, 2))

moves = [m for m in moves if m]

if POST:
    saved_lock = company.fiscalyear_lock_date
    if saved_lock:
        company.sudo().write({"fiscalyear_lock_date": False})
        log("fiscalyear_lock_date %s -> cleared (restored at end)" % saved_lock)
    try:
        for m in moves:
            m.action_post()
            log("posted %s" % m.name)
    finally:
        if saved_lock:
            company.sudo().write({"fiscalyear_lock_date": saved_lock})
            log("fiscalyear_lock_date restored to %s" % saved_lock)
else:
    log("entries left in DRAFT (set ADJ_POST=1 to post)")


def bal(code, as_of):
    env.cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state='posted' and m.date <= %s and l.account_id=%s and l.company_id=%s""",
        (as_of, _code2acc[code].id, company.id),
    )
    return round(float(env.cr.fetchone()[0]), 2)


# When the posting date is later than the cut-off, the cut-off balance is what the
# client sees for the closed period -- it must come out unchanged -- and the posting-date
# balance is where the adjustment actually lands.
for code in (ACC_AR, ACC_DEPOSIT, ACC_MDR):
    if DATE == CUTOFF:
        log("balance %s = %s" % (code, bal(code, DATE)))
    else:
        log(
            "balance %s: per %s = %s (harus tidak berubah) | per %s = %s"
            % (code, CUTOFF, bal(code, CUTOFF), DATE, bal(code, DATE))
        )

if DRY:
    env.cr.rollback()
    log("ADJ_DRY=1 -> rolled back")
else:
    env.cr.commit()
    log("committed")
