# Lanjutan adjustment AR Juni 2026 -- tiga jurnal yang belum dibuat oleh
# 69_ar_adjustments_juni.py, semuanya sudah dikonfirmasi Accounting di sheet
# "Ringkasan & Ulasan" (Drive 1I3fFgYMP5dXMAleudW288MTBFZXs5kHR).
#
# Jangan pakai script 69 untuk ini: ref-guard EBR-ADJ-AR-JUNI-2026% di sana langsung
# SystemExit karena REALOKASI/MDR/CLEARING sudah ter-posting 4-Aug-2026.
#
#   1. SALESMANUAL  Rp 14.608.080 -- reclass, BUKAN pendapatan baru.
#      Penjualan manual Juni tersetor ke bank di Juni, tapi store menginput ulang
#      penjualannya di X24DN pada Juli. Jadi penjualannya sudah ada di Odoo sebagai
#      POS Receivable Juli 1106000101..110 (melebur di total harian per toko).
#      Membukukannya Dr AR / Cr Sales akan mendobel pendapatan dan PPN Keluaran Juli.
#          Dr 1106000001 per OU / Cr 1106000101..110 per OU
#      Sisi kredit dialokasikan ke tender yang sisanya MASIH TERBUKA setelah 63 draft
#      EBR-CLR-JULI-2026-* diposting -- kalau mengambil baris yang akan disettle blok A,
#      blok A jadi SHORT. Alokasi largest-residual-first, dihitung dari ledger.
#
#   2. TOPUP        Rp 4.186.925 -- melunasi cap clearing MM Bekasi.
#      Clearing 4-Aug berhenti di 667.523.715 (bukan 671.710.640) karena piutang
#      MM Bekasi belum memuat penjualan manual 9.052.000, sehingga depositnya
#      18.861.775 kena cap piutang 14.674.850. Harus dijalankan SESUDAH blok 1.
#          Dr 2103100003 / Cr 1106000001, per OU, sisa deposit dibatasi sales manual
#
#   3. ADJ          Rp 260.660 -- jurnal baru di sheet, dipecah per OU sesuai
#      sheet "6. Sisa selisih".
#          Dr 1106000001 / Cr 2103100003 200.000 (Central Park, deposit baru Juli)
#                        / Cr 7104000001  50.170 (TSM Bandung, kelebihan charge MDR)
#                        / Cr 7699000000  10.490 (rounding per toko)
#
# Tanggal buku 01-Jul-2026 seperti trio 4-Aug: Juni sudah dilaporkan dan tidak boleh
# bergerak sama sekali (lihat ADJ_CUTOFF). fiscalyear_lock_date 2026-06-30 tetap
# terpasang; script hanya membukanya kalau tanggal buku memang jatuh di periode terkunci.
#
#   docker exec -i -e ADJ_CONFIRM=1 odoo19-platform-odoo \
#       odoo shell -d prd_levis_begbal --no-http \
#       < /opt/odoo-platform/scripts/tenants/levis/92_ar_juni_lanjutan.py
#
# Env flags:  (default = dry-run, build + report + rollback)
#   ADJ_CONFIRM=1          -> post + commit
#   ADJ_BLOCKS=            -> subset blok, mis. "SALESMANUAL,TOPUP" (default ketiganya)
#   ADJ_DATE=YYYY-MM-DD    -> tanggal buku (default 2026-07-01)
#   ADJ_CUTOFF=YYYY-MM-DD  -> posisi pengukuran yang tidak boleh berubah (default 2026-06-30)
#   ADJ_NO_RECONCILE=1     -> jangan rekonsiliasi kredit blok 1 ke debit POS receivable
#
# Catatan untuk siapa pun yang meregenerasi draft Juli lewat 80/81 SETELAH script ini
# jalan: blok A di 81 mengalokasi berdasarkan amount_residual baris debit. Blok 1 di sini
# merekonsiliasi kreditnya (kecuali ADJ_NO_RECONCILE=1) supaya residual ikut turun dan
# 81 tidak mengalokasi dua kali ke baris yang sama.
import os
from collections import OrderedDict

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[ar-lanjutan] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
DATE = os.environ.get("ADJ_DATE", "2026-07-01")
CUTOFF = os.environ.get("ADJ_CUTOFF", "2026-06-30")
REF_PREFIX = "EBR-ADJ-AR-JUNI-2026"
ACC_AR = "1106000001"
ACC_DEPOSIT = "2103100003"
ACC_MDR = "7104000001"
ACC_OTHER_INCOME = "7699000000"
POS_FROM, POS_TO = "1106000101", "1106000110"
# jendela tempat POS receivable Juli dicari untuk alokasi sisi kredit blok 1
ALLOC_FROM, ALLOC_TO = "2026-07-01", "2026-07-31"

CONFIRM = os.environ.get("ADJ_CONFIRM") == "1"
RECONCILE = os.environ.get("ADJ_NO_RECONCILE") != "1"
ALL_BLOCKS = ["SALESMANUAL", "TOPUP", "ADJ"]
BLOCKS = [b.strip().upper() for b in os.environ.get("ADJ_BLOCKS", ",".join(ALL_BLOCKS)).split(",") if b.strip()]
for b in BLOCKS:
    if b not in ALL_BLOCKS:
        raise SystemExit("blok tidak dikenal: %s (pilihan: %s)" % (b, ", ".join(ALL_BLOCKS)))

# --- angka FICO ------------------------------------------------------------
# penjualan manual versi rekon Finance (kolom X), sama dengan SALES_MANUAL di script 69
SALES_MANUAL = OrderedDict(
    [
        ("OLS SES - METROPOLITAN MALL BEKASI", 9052000),
        ("OLS SES - PARIS VAN JAVA", 3756280),
        ("OLS SES - CENTRAL PARK", 1799800),
    ]
)
# sheet "6. Sisa selisih": deposit baru Juli yang digantung, per OU
ADJ_DEPOSIT = OrderedDict([("OLS SES - CENTRAL PARK", 200000)])
# kelebihan charge MDR Juni yang dikoreksi di Juli
ADJ_MDR = OrderedDict([("OLS SES - TRANS STUDIO MALL BANDUNG", 50170)])
# rounding, positif = piutang naik / other income kredit
ADJ_ROUNDING = OrderedDict(
    [
        ("OLS SES - KELAPA GADING MALL", 7505),
        ("OLS SES - GALAXY MALL 3", 2000),
        ("OLS SES - TUNJUNGAN PLAZA 3", 1450),
        ("OLS SES - PONDOK INDAH MALL 2", 1000),
        ("OLS SES - AEON BSD CITY", 625),
        ("OLS SES - GRAND INDONESIA", 1),
        ("OLS SES - SENAYAN CITY", -39),
        ("OLS SES - PARIS VAN JAVA", -1002),
        ("OLS SES - PLAZA SENAYAN", -1050),
    ]
)
ADJ_TOTAL = sum(ADJ_DEPOSIT.values()) + sum(ADJ_MDR.values()) + sum(ADJ_ROUNDING.values())
if ADJ_TOTAL != 260660:
    raise SystemExit("rincian blok ADJ berjumlah %s, seharusnya 260.660" % ADJ_TOTAL)

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
journal = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", company.id)], limit=1)
if not journal:
    raise SystemExit("journal %s not found" % JOURNAL)

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}
for code in (ACC_AR, ACC_DEPOSIT, ACC_MDR, ACC_OTHER_INCOME):
    if code not in _code2acc:
        raise SystemExit("account %s not in COA" % code)
POS_CODES = sorted(c for c in _code2acc if POS_FROM <= c <= POS_TO)
if not POS_CODES:
    raise SystemExit("tidak ada akun POS receivable %s..%s di COA" % (POS_FROM, POS_TO))

_ou = {a.name: a for a in env["account.analytic.account"].search([])}
missing = [o for o in set(list(SALES_MANUAL) + list(ADJ_DEPOSIT) + list(ADJ_MDR) + list(ADJ_ROUNDING)) if o not in _ou]
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


def already(suffix):
    return bool(Move.search_count([("ref", "=", "%s-%s" % (REF_PREFIX, suffix)), ("company_id", "=", company.id)]))


def create(suffix, narration, lines):
    if not lines:
        return None
    if DATE != CUTOFF:
        narration += (
            " Dibukukan tanggal %s (bukan %s) karena angka Juni sudah dilaporkan dan tidak boleh "
            "berubah; seluruh nilai tetap diukur pada posisi %s." % (DATE, CUTOFF, CUTOFF)
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
    ar_net = sum(l.debit - l.credit for l in move.line_ids if l.account_id.code == ACC_AR)
    log(
        "%s: %d baris, debit %s, netto ke %s %s"
        % (suffix, len(move.line_ids), sum(move.line_ids.mapped("debit")), ACC_AR, round(ar_net, 2))
    )
    return move


def bal(code, as_of):
    env.cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state='posted' and m.date <= %s and l.account_id=%s and l.company_id=%s""",
        (as_of, _code2acc[code].id, company.id),
    )
    return round(float(env.cr.fetchone()[0]), 2)


def bal_per_ou(code, as_of):
    """saldo (debit-credit) per Operating Unit, posted saja"""
    env.cr.execute(
        """select coalesce(aa.name->>'en_US','(tanpa OU)'), round(sum(l.debit-l.credit)::numeric,2)
             from account_move_line l
             join account_move m on m.id=l.move_id
             left join lateral (select (jsonb_object_keys(l.analytic_distribution))::int aid) k on true
             left join account_analytic_account aa on aa.id=k.aid
            where l.account_id=%s and l.company_id=%s and m.state='posted' and m.date <= %s
            group by 1""",
        (_code2acc[code].id, company.id, as_of),
    )
    return {name: float(amt) for name, amt in env.cr.fetchall()}


def pos_open_per_ou_account():
    """sisa POS receivable Juli yang tetap terbuka setelah semua draft diposting:
    debit posted - credit posted - credit draft, per (OU, kode akun)."""
    env.cr.execute(
        """select coalesce(aa.name->>'en_US','(tanpa OU)'), l.account_id,
                  round(sum(case when m.state='posted' then l.debit-l.credit
                                 when m.state='draft'  then -l.credit else 0 end)::numeric,2)
             from account_move_line l
             join account_move m on m.id=l.move_id
             left join lateral (select (jsonb_object_keys(l.analytic_distribution))::int aid) k on true
             left join account_analytic_account aa on aa.id=k.aid
            where l.account_id = any(%s) and l.company_id=%s
              and m.state in ('posted','draft') and m.date between %s and %s
            group by 1,2""",
        ([_code2acc[c].id for c in POS_CODES], company.id, ALLOC_FROM, ALLOC_TO),
    )
    _id2code = {_code2acc[c].id: c for c in POS_CODES}
    out = {}
    for name, acc_id, amt in env.cr.fetchall():
        out.setdefault(name, {})[_id2code[acc_id]] = float(amt)
    return out


# --- posisi awal, dibaca SEBELUM apa pun dibuat/diposting -------------------
deposit_before = bal_per_ou(ACC_DEPOSIT, DATE)
pos_open = pos_open_per_ou_account()
before = {c: (bal(c, CUTOFF), bal(c, DATE)) for c in (ACC_AR, ACC_DEPOSIT, ACC_MDR, ACC_OTHER_INCOME)}
log("tanggal buku %s, posisi diukur per %s" % (DATE, CUTOFF))
log(
    "saldo awal per %s: AR %s | deposit %s | MDR %s"
    % (DATE, before[ACC_AR][1], before[ACC_DEPOSIT][1], before[ACC_MDR][1])
)

moves = []
sm_credit_lines = []  # (kode akun, OU, jumlah) -- untuk rekonsiliasi setelah posting

# --- 1. SALESMANUAL: reclass POS receivable Juli -> AR Juni -----------------
if "SALESMANUAL" in BLOCKS:
    if already("SALESMANUAL"):
        log("SALESMANUAL sudah ada -> dilewati")
    else:
        sm_lines = []
        for ou, amt in SALES_MANUAL.items():
            avail = {c: v for c, v in pos_open.get(ou, {}).items() if v > 0}
            total_avail = round(sum(avail.values()), 2)
            if total_avail < amt:
                raise SystemExit(
                    "sisa POS receivable Juli %s hanya %s, kurang dari penjualan manual %s -- "
                    "reclass akan membuat blok A clearing Juli SHORT" % (ou, total_avail, amt)
                )
            sm_lines.append(line(ACC_AR, "Penjualan manual Juni 2026 %s (input ulang X24DN Juli)" % ou, amt, ou))
            sisa = amt
            for code in sorted(avail, key=lambda c: -avail[c]):
                if sisa <= 0:
                    break
                take = round(min(sisa, avail[code]), 2)
                sm_lines.append(line(code, "Reclass penjualan manual Juni 2026 %s" % ou, -take, ou))
                sm_credit_lines.append((code, ou, take))
                log("  alokasi %s %s <- %s (sisa terbuka %s)" % (ou, take, code, avail[code]))
                sisa = round(sisa - take, 2)
            if sisa > 0:
                raise SystemExit("alokasi %s masih kurang %s" % (ou, sisa))
        moves.append(
            create(
                "SALESMANUAL",
                "Reclass penjualan manual Juni 2026 dari POS Receivable Juli ke Trade Receivables. "
                "Uangnya tersetor ke bank di Juni, penjualannya diinput ulang store di X24DN pada "
                "Juli, sehingga di Odoo terbaca sebagai piutang tender Juli. Bukan pendapatan baru "
                "-- pendapatan dan PPN Keluaran-nya sudah terbentuk dari impor X24DN Juli.",
                sm_lines,
            )
        )

# --- 2. TOPUP: melunasi cap clearing ---------------------------------------
if "TOPUP" in BLOCKS:
    if already("TOPUP"):
        log("TOPUP sudah ada -> dilewati")
    else:
        topup_lines = []
        total_topup = 0.0
        for ou, sm in SALES_MANUAL.items():
            avail = round(-deposit_before.get(ou, 0.0), 2)  # deposit = saldo kredit
            if avail <= 0:
                continue
            amt = round(min(avail, sm), 2)
            if amt <= 0:
                continue
            if amt < avail:
                log("cap %s: top-up %s dari sisa deposit %s (penjualan manual %s)" % (ou, amt, avail, sm))
            topup_lines.append(line(ACC_DEPOSIT, "Clearing piutang penjualan Juni 2026 %s (top-up)" % ou, amt, ou))
            topup_lines.append(line(ACC_AR, "Clearing piutang penjualan Juni 2026 %s (top-up)" % ou, -amt, ou))
            total_topup += amt
        if topup_lines:
            moves.append(
                create(
                    "TOPUP",
                    "Top-up clearing piutang Juni 2026: sisa Deposit from customer trade yang "
                    "4-Aug-2026 kena cap piutang, karena penjualan manual belum tercatat. Setelah "
                    "reclass penjualan manual, piutangnya cukup untuk di-clear penuh.",
                    topup_lines,
                )
            )
            log("total top-up clearing %s" % round(total_topup, 2))
        else:
            log("TOPUP: tidak ada sisa deposit yang bisa di-clear -> tidak ada jurnal")

# --- 3. ADJ: sisa selisih yang dikonfirmasi Accounting ---------------------
if "ADJ" in BLOCKS:
    if already("ADJ"):
        log("ADJ sudah ada -> dilewati")
    else:
        adj_lines = []
        for ou, amt in ADJ_DEPOSIT.items():
            adj_lines.append(line(ACC_AR, "Adj bank Juni 2026 %s (deposit digantung ke Juli)" % ou, amt, ou))
            adj_lines.append(line(ACC_DEPOSIT, "Adj bank Juni 2026 %s (deposit digantung ke Juli)" % ou, -amt, ou))
        for ou, amt in ADJ_MDR.items():
            adj_lines.append(line(ACC_AR, "Koreksi kelebihan charge MDR Juni 2026 %s" % ou, amt, ou))
            adj_lines.append(line(ACC_MDR, "Koreksi kelebihan charge MDR Juni 2026 %s" % ou, -amt, ou))
        for ou, amt in ADJ_ROUNDING.items():
            adj_lines.append(line(ACC_AR, "Rounding rekon AR Juni 2026 %s" % ou, amt, ou))
            adj_lines.append(line(ACC_OTHER_INCOME, "Rounding rekon AR Juni 2026 %s" % ou, -amt, ou))
        moves.append(
            create(
                "ADJ",
                "Sisa selisih rekon AR Juni 2026 (sheet '6. Sisa selisih'): adj bank Central Park "
                "200.000 yang digantung sebagai deposit Juli, kelebihan charge MDR TSM Bandung "
                "50.170, dan rounding 10.490 ke other operating income.",
                adj_lines,
            )
        )

moves = [m for m in moves if m]
if not moves:
    log("tidak ada jurnal baru yang perlu dibuat")

# --- posting ---------------------------------------------------------------
if CONFIRM and moves:
    saved_lock = company.fiscalyear_lock_date
    lift = bool(saved_lock) and str(saved_lock) >= DATE
    if lift:
        company.sudo().write({"fiscalyear_lock_date": False})
        log("fiscalyear_lock_date %s -> dibuka sementara (dipulihkan di akhir)" % saved_lock)
    try:
        for m in moves:
            m.action_post()
            log("posted %s (%s)" % (m.name, m.ref))
    finally:
        if lift:
            company.sudo().write({"fiscalyear_lock_date": saved_lock})
            log("fiscalyear_lock_date dipulihkan ke %s" % saved_lock)

    # rekonsiliasi kredit blok 1 ke baris debit POS receivable Juli, largest-residual-first,
    # supaya amount_residual ikut turun dan 81 blok A tidak mengalokasi dua kali
    if RECONCILE and sm_credit_lines:
        AML = env["account.move.line"].with_company(company)
        sm_move = next(m for m in moves if m.ref.endswith("-SALESMANUAL"))
        for code, ou, amt in sm_credit_lines:
            acc = _code2acc[code]
            cred = sm_move.line_ids.filtered(
                lambda l, a=acc.id, v=amt: l.account_id.id == a and abs(l.credit - v) < 0.005
            )
            if not cred:
                raise SystemExit("baris kredit %s %s %s tidak ditemukan" % (code, ou, amt))
            cred = cred[0]
            debits = AML.search(
                [
                    ("account_id", "=", acc.id),
                    ("company_id", "=", company.id),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                    ("debit", ">", 0),
                    ("date", ">=", ALLOC_FROM),
                    ("date", "<=", ALLOC_TO),
                ]
            ).filtered(lambda l, o=_ou[ou].id: str(o) in (l.analytic_distribution or {}))
            debits = debits.sorted(key=lambda l: -abs(l.amount_residual))
            take, batch = amt, AML.browse()
            for d in debits:
                if take <= 0.004:
                    break
                batch |= d
                take = round(take - abs(d.amount_residual), 2)
            if take > 0.004:
                raise SystemExit("residual debit %s %s kurang %s untuk direkonsiliasi" % (code, ou, take))
            (cred | batch).reconcile()
            log("reconcile %s %s %s <-> %d baris debit" % (ou, code, amt, len(batch)))
elif moves:
    log("jurnal dibuat DRAFT (set ADJ_CONFIRM=1 untuk post + commit)")

# --- verifikasi ------------------------------------------------------------
for code in (ACC_AR, ACC_DEPOSIT, ACC_MDR, ACC_OTHER_INCOME):
    b0, b1 = before[code]
    a0, a1 = bal(code, CUTOFF), bal(code, DATE)
    flag = "" if abs(a0 - b0) < 0.005 else "  <<< BERUBAH, TIDAK BOLEH!"
    log("saldo %s: per %s %s -> %s%s | per %s %s -> %s" % (code, CUTOFF, b0, a0, flag, DATE, b1, a1))
    if flag:
        raise SystemExit("posisi %s per %s berubah -- periode tertutup tidak boleh bergerak" % (code, CUTOFF))

# Saldo AR per toko TIDAK bisa diderive dari Odoo -- baris GLJV EBR-RECLASS-SALES-* di
# 1106000001 tidak ber-analytic_distribution, jadi bal_per_ou(ACC_AR) hanya memuat sisi
# adjustment dan akan tampak negatif. Angka per toko harus dibaca dari sheet FICO.
# Yang bisa diverifikasi di sini: mutasi ber-OU yang dibuat script ini sendiri.
ar_delta = {}
for m in moves:
    for l in m.line_ids:
        if l.account_id.code != ACC_AR:
            continue
        for aid in l.analytic_distribution or {}:
            name = env["account.analytic.account"].browse(int(aid)).name
            ar_delta[name] = round(ar_delta.get(name, 0.0) + l.debit - l.credit, 2)
for ou in sorted(ar_delta, key=lambda o: -abs(ar_delta[o])):
    log("mutasi %s ke %s: %s" % (ACC_AR, ou, ar_delta[ou]))
log("total mutasi %s dari script ini: %s" % (ACC_AR, round(sum(ar_delta.values()), 2)))

left = pos_open_per_ou_account()
neg = [(ou, c, v) for ou, d in left.items() for c, v in d.items() if v < -0.004]
log(
    "POS receivable Juli yang tetap terbuka setelah semua draft: %s"
    % round(sum(sum(d.values()) for d in left.values()), 2)
)
if neg:
    raise SystemExit("sisa POS receivable negatif (blok A akan SHORT): %s" % neg)

if CONFIRM:
    env.cr.commit()
    log("committed")
else:
    env.cr.rollback()
    log("dry-run -> rolled back")
