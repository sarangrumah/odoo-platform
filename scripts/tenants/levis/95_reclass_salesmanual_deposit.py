# Koreksi sisi debit reclass penjualan manual Juni 2026 -- OPSI "MM BEKASI SAJA".
#
# Permintaan Finance: hasil reclass GLJV/2026/07/0026
# (ref EBR-ADJ-AR-JUNI-2026-SALESMANUAL) seharusnya memakai
# 2103100003 Deposit from customer trade, bukan 1106000001 Trade Receivables.
# Yang disiapkan di sini hanya bagian METROPOLITAN MALL BEKASI Rp 9.052.000 --
# satu-satunya toko yang setoran Juni-nya (18.861.775) melebihi piutang Juni-nya
# (14.674.850), jadi memang ada uang masuk yang bisa dilawankan ke penjualan manual.
# PARIS VAN JAVA 3.756.280 dan CENTRAL PARK 1.799.800 TIDAK disentuh: keduanya
# tidak menyetor apa pun untuk penjualan manualnya, dan angka Outstanding-nya di
# sheet FICO (3.755.278 / 1.999.800) cocok dengan posisi AR sekarang.
#
# Bentuk koreksi = jurnal reclass satu pasang baris, BUKAN reversal 0026:
#
#     Dr 2103100003 Deposit from customer trade   9.052.000
#         Cr 1106000001 Trade Receivables             9.052.000
#
# Alasan tidak me-reverse 0026: sisi kredit 0026 (POS Receivable 1106000101..106)
# sudah DIREKONSILIASI ke baris debit POS receivable Juli. Membalik 0026 akan
# membuka lagi rekonsiliasi itu, menaikkan amount_residual, dan blok A dari
# 81_clearing_juli.py mengalokasi berdasarkan residual -- 63 draft
# EBR-CLR-JULI-2026-* yang menunggu approval bisa jadi dobel alokasi.
# Jurnal ini sengaja hanya menyentuh sisi debit.
#
# EFEK YANG HARUS DIBACA DULU SEBELUM POSTING (dilaporkan script di akhir):
#   blok SWAP saja        -> 2103100003 per 31-Jul: -200.000 menjadi +8.852.000 (DEBIT,
#                            abnormal untuk akun liability) dan AR MM Bekasi menjadi
#                            -4.186.925 (KREDIT), karena TOPUP 0027 sudah lebih dulu
#                            mendebit deposit 4.186.925 / mengkredit AR untuk uang
#                            setoran yang sama.
#   SWAP + UNTOPUP        -> AR MM Bekasi kembali 0, deposit +4.665.075 (DEBIT).
#                            4.865.075 itu memang penjualan Juni MM Bekasi yang tidak
#                            pernah disetor, jadi hakikatnya piutang, bukan deposit.
#
# Catatan jujur: secara netto AR + deposit, posisi sekarang (deposit 0, AR 4.865.075)
# dan hasil SWAP+UNTOPUP (deposit -4.865.075 alias debit, AR 0) adalah jumlah yang
# sama; yang berubah hanya penyajian antar dua akun. Kalau Finance keberatan dengan
# saldo debit di akun deposit, jangan jalankan script ini.
#
#   docker cp /opt/odoo-platform/scripts/tenants/levis/95_reclass_salesmanual_deposit.py \
#       odoo19-platform-odoo:/tmp/95.py   # (atau langsung redirect seperti di bawah)
#
#   # dry-run (default): bangun jurnal, laporkan dampaknya, rollback
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < /opt/odoo-platform/scripts/tenants/levis/95_reclass_salesmanual_deposit.py
#
#   # posting beneran
#   docker exec -i -e DEP_CONFIRM=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < /opt/odoo-platform/scripts/tenants/levis/95_reclass_salesmanual_deposit.py
#
# Env flags:
#   DEP_CONFIRM=1          -> post + commit (default: dry-run, dibuat draft lalu rollback)
#   DEP_BLOCKS=SWAP,UNTOPUP-> default "SWAP" saja; tambahkan UNTOPUP kalau Finance mau
#                             TOPUP 0027 ikut dibatalkan (lihat tabel efek di atas)
#   DEP_DATE=YYYY-MM-DD    -> tanggal buku (default 2026-07-01, sama dengan trio 92)
#   DEP_CUTOFF=YYYY-MM-DD  -> posisi yang tidak boleh bergerak (default 2026-06-30)
#   DEP_NO_RECONCILE=1     -> jangan rekonsiliasi kredit AR baru ke baris debit AR di 0026
#
# Backup dulu sebelum DEP_CONFIRM=1:
#   docker exec -e PGPASSWORD=... odoo19-platform-postgres pg_dump -U odoo -Fc \
#       -d prd_levis_begbal -f /tmp/prd_levis_begbal_pre_salesmanual_deposit.dump
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[sm-deposit] " + m)

COMPANY_ID = 1
JOURNAL = "GLJV"
DATE = os.environ.get("DEP_DATE", "2026-07-01")
CUTOFF = os.environ.get("DEP_CUTOFF", "2026-06-30")
REF_PREFIX = "EBR-ADJ-AR-JUNI-2026-SALESMANUAL-DEPOSIT"
SRC_REF = "EBR-ADJ-AR-JUNI-2026-SALESMANUAL"
TOPUP_REF = "EBR-ADJ-AR-JUNI-2026-TOPUP"
ACC_AR = "1106000001"
ACC_DEPOSIT = "2103100003"
OU_NAME = "OLS SES - METROPOLITAN MALL BEKASI"
EXPECTED_SWAP = 9052000.0  # penjualan manual Juni MM Bekasi menurut rekon FICO
EXPECTED_TOPUP = 4186925.0  # sisa deposit MM Bekasi yang dipakai TOPUP 0027

CONFIRM = os.environ.get("DEP_CONFIRM") == "1"
RECONCILE = os.environ.get("DEP_NO_RECONCILE") != "1"
ALL_BLOCKS = ["SWAP", "UNTOPUP"]
BLOCKS = [b.strip().upper() for b in os.environ.get("DEP_BLOCKS", "SWAP").split(",") if b.strip()]
for b in BLOCKS:
    if b not in ALL_BLOCKS:
        raise SystemExit("blok tidak dikenal: %s (pilihan: %s)" % (b, ", ".join(ALL_BLOCKS)))
if "UNTOPUP" in BLOCKS and "SWAP" not in BLOCKS:
    raise SystemExit("UNTOPUP tanpa SWAP akan mengembalikan piutang MM Bekasi tanpa lawannya")

company = env["res.company"].browse(COMPANY_ID)
Move = env["account.move"].with_company(company)
AML = env["account.move.line"].with_company(company)
journal = env["account.journal"].search([("code", "=", JOURNAL), ("company_id", "=", company.id)], limit=1)
if not journal:
    raise SystemExit("journal %s not found" % JOURNAL)

_code2acc = {a.code: a for a in env["account.account"].with_company(company).search([]) if a.code}
for code in (ACC_AR, ACC_DEPOSIT):
    if code not in _code2acc:
        raise SystemExit("account %s not in COA" % code)
ou = env["account.analytic.account"].search([("name", "=", OU_NAME)], limit=1)
if not ou:
    raise SystemExit("analytic account tidak ditemukan: %s" % OU_NAME)
AD = {str(ou.id): 100.0}


def line(code, name, amount):
    """amount > 0 -> debit, amount < 0 -> credit"""
    return (
        0,
        0,
        {
            "account_id": _code2acc[code].id,
            "name": name,
            "debit": amount if amount > 0 else 0.0,
            "credit": -amount if amount < 0 else 0.0,
            "analytic_distribution": dict(AD),
        },
    )


def already(suffix):
    ref = REF_PREFIX if not suffix else "%s-%s" % (REF_PREFIX, suffix)
    return bool(Move.search_count([("ref", "=", ref), ("company_id", "=", company.id)]))


def create(suffix, narration, lines):
    ref = REF_PREFIX if not suffix else "%s-%s" % (REF_PREFIX, suffix)
    if DATE != CUTOFF:
        narration += (
            " Dibukukan tanggal %s (bukan %s) karena posisi Juni sudah dilaporkan dan tidak "
            "boleh berubah; nilainya tetap diukur pada posisi %s." % (DATE, CUTOFF, CUTOFF)
        )
    move = Move.create(
        {
            "journal_id": journal.id,
            "date": DATE,
            "ref": ref,
            "company_id": company.id,
            "move_type": "entry",
            "narration": narration,
            "line_ids": lines,
        }
    )
    log("%s: %d baris, debit %s" % (ref, len(move.line_ids), sum(move.line_ids.mapped("debit"))))
    return move


def bal(code, as_of, states=("posted",)):
    env.cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state = any(%s) and m.date <= %s and l.account_id=%s and l.company_id=%s""",
        (list(states), as_of, _code2acc[code].id, company.id),
    )
    return round(float(env.cr.fetchone()[0]), 2)


def bal_ou(code, as_of):
    """saldo (debit-credit) MM Bekasi saja -- hanya baris yang ber-analytic OU ini.
    Catatan: baris GLJV EBR-RECLASS-SALES-* di 1106000001 TIDAK ber-analytic, jadi
    angka ini adalah mutasi adjustment per OU, bukan saldo piutang toko yang utuh."""
    env.cr.execute(
        """select coalesce(sum(l.debit-l.credit),0) from account_move_line l
           join account_move m on m.id=l.move_id
          where m.state='posted' and m.date <= %s and l.account_id=%s and l.company_id=%s
            and l.analytic_distribution ? %s""",
        (as_of, _code2acc[code].id, company.id, str(ou.id)),
    )
    return round(float(env.cr.fetchone()[0]), 2)


# --- baca jurnal sumber ----------------------------------------------------
src = Move.search([("ref", "=", SRC_REF), ("company_id", "=", company.id)], limit=1)
if not src:
    raise SystemExit("jurnal sumber %s tidak ditemukan" % SRC_REF)
if src.state != "posted":
    raise SystemExit("jurnal sumber %s state=%s, harus posted" % (src.name, src.state))
src_ar = src.line_ids.filtered(
    lambda l: l.account_id.id == _code2acc[ACC_AR].id and l.debit > 0 and str(ou.id) in (l.analytic_distribution or {})
)
if len(src_ar) != 1:
    raise SystemExit("baris AR %s di %s ada %d, harusnya tepat 1" % (OU_NAME, src.name, len(src_ar)))
src_ar = src_ar[0]
SWAP_AMOUNT = round(src_ar.debit, 2)
if abs(SWAP_AMOUNT - EXPECTED_SWAP) > 0.005:
    raise SystemExit(
        "baris AR %s di %s berjumlah %s, bukan %s -- angka rekon berubah, review dulu"
        % (OU_NAME, src.name, SWAP_AMOUNT, EXPECTED_SWAP)
    )
log("sumber %s baris %d: Dr %s %s (residual %s)" % (src.name, src_ar.id, ACC_AR, SWAP_AMOUNT, src_ar.amount_residual))

topup = Move.search([("ref", "=", TOPUP_REF), ("company_id", "=", company.id)], limit=1)
TOPUP_AMOUNT = 0.0
if "UNTOPUP" in BLOCKS:
    if not topup or topup.state != "posted":
        raise SystemExit("jurnal %s tidak ada / belum posted, UNTOPUP tidak bisa dijalankan" % TOPUP_REF)
    tl = topup.line_ids.filtered(
        lambda l: (
            l.account_id.id == _code2acc[ACC_DEPOSIT].id
            and l.debit > 0
            and str(ou.id) in (l.analytic_distribution or {})
        )
    )
    if len(tl) != 1:
        raise SystemExit("baris deposit %s di %s ada %d, harusnya tepat 1" % (OU_NAME, topup.name, len(tl)))
    TOPUP_AMOUNT = round(tl[0].debit, 2)
    if abs(TOPUP_AMOUNT - EXPECTED_TOPUP) > 0.005:
        raise SystemExit("top-up %s berjumlah %s, bukan %s -- review dulu" % (OU_NAME, TOPUP_AMOUNT, EXPECTED_TOPUP))

# --- posisi awal, dibaca SEBELUM apa pun dibuat ----------------------------
before = {c: (bal(c, CUTOFF), bal(c, DATE)) for c in (ACC_AR, ACC_DEPOSIT)}
before_ou = {c: bal_ou(c, DATE) for c in (ACC_AR, ACC_DEPOSIT)}
log("tanggal buku %s, posisi dikunci per %s" % (DATE, CUTOFF))
log("saldo awal per %s: AR %s | deposit %s" % (DATE, before[ACC_AR][1], before[ACC_DEPOSIT][1]))
log("mutasi adjustment %s per %s: AR %s | deposit %s" % (OU_NAME, DATE, before_ou[ACC_AR], before_ou[ACC_DEPOSIT]))

moves = []

# --- 1. SWAP: pindahkan sisi debit reclass dari AR ke deposit ---------------
if "SWAP" in BLOCKS:
    if already(""):
        log("SWAP sudah ada -> dilewati")
    else:
        moves.append(
            create(
                "",
                "Koreksi sisi debit reclass penjualan manual Juni 2026 %s: dari "
                "1106000001 Trade Receivables ke 2103100003 Deposit from customer trade, "
                "sesuai arahan Finance. Setoran bank Juni %s (18.861.775) memang melebihi "
                "piutang Juni-nya (14.674.850), jadi penjualan manual 9.052.000 dilawankan "
                "ke deposit. Sisi kredit POS Receivable di %s sengaja TIDAK disentuh karena "
                "sudah direkonsiliasi ke piutang tender Juli." % (OU_NAME, OU_NAME, src.name),
                [
                    line(ACC_DEPOSIT, "Reclass penjualan manual Juni 2026 %s ke deposit" % OU_NAME, SWAP_AMOUNT),
                    line(ACC_AR, "Reclass penjualan manual Juni 2026 %s ke deposit" % OU_NAME, -SWAP_AMOUNT),
                ],
            )
        )

# --- 2. UNTOPUP (opsional): batalkan TOPUP 0027 untuk MM Bekasi -------------
if "UNTOPUP" in BLOCKS:
    if already("UNTOPUP"):
        log("UNTOPUP sudah ada -> dilewati")
    else:
        moves.append(
            create(
                "UNTOPUP",
                "Pembatalan top-up clearing %s (%s): top-up itu dibuat semata karena "
                "penjualan manual 9.052.000 dibukukan sebagai piutang. Setelah penjualan "
                "manual dilawankan langsung ke deposit, sisa deposit 4.186.925 tidak lagi "
                "punya piutang untuk di-clear." % (OU_NAME, topup.name),
                [
                    line(ACC_AR, "Pembatalan top-up clearing Juni 2026 %s" % OU_NAME, TOPUP_AMOUNT),
                    line(ACC_DEPOSIT, "Pembatalan top-up clearing Juni 2026 %s" % OU_NAME, -TOPUP_AMOUNT),
                ],
            )
        )

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

    # rekonsiliasi kredit AR baru ke baris debit AR di 0026, supaya keduanya tidak
    # menggantung sebagai open item di aged report. Hanya menyentuh 1106000001;
    # sisi POS receivable dan draft EBR-CLR-JULI-2026-* tidak ikut bergerak.
    if RECONCILE and "SWAP" in BLOCKS and moves:
        swap_move = next((m for m in moves if m.ref == REF_PREFIX), None)
        if swap_move:
            cred = swap_move.line_ids.filtered(lambda l: l.account_id.id == _code2acc[ACC_AR].id and l.credit > 0)
            src_ar.invalidate_recordset(["amount_residual", "reconciled"])
            if src_ar.reconciled or abs(src_ar.amount_residual) < 0.005:
                log("baris AR sumber sudah ter-rekonsiliasi -> reconcile dilewati")
            elif abs(src_ar.amount_residual - SWAP_AMOUNT) > 0.005:
                log(
                    "residual baris AR sumber %s != %s -> reconcile dilewati, cek manual"
                    % (src_ar.amount_residual, SWAP_AMOUNT)
                )
            else:
                (cred | src_ar).reconcile()
                log("reconcile %s: kredit baru <-> baris %d di %s" % (SWAP_AMOUNT, src_ar.id, src.name))
    env.cr.commit()
    log("COMMIT")
elif moves:
    log("jurnal dibuat DRAFT dan akan di-rollback (set DEP_CONFIRM=1 untuk post + commit)")

# --- verifikasi ------------------------------------------------------------
# Dalam dry-run jurnalnya masih draft, dan saldo "posted+draft" tidak bisa dipakai
# sebagai pembanding karena 63 draft EBR-CLR-JULI-2026-* ikut terhitung. Dampaknya
# karena itu dihitung dari baris yang dibuat script ini saja.
delta = {}
for m in moves:
    for l in m.line_ids:
        delta[l.account_id.code] = round(delta.get(l.account_id.code, 0.0) + l.debit - l.credit, 2)
for code in (ACC_AR, ACC_DEPOSIT):
    b0, b1 = before[code]
    a0 = bal(code, CUTOFF)
    if abs(a0 - b0) > 0.005:
        raise SystemExit("posisi %s per %s berubah -- periode tertutup tidak boleh bergerak" % (code, CUTOFF))
    log(
        "saldo %s: per %s %s (tetap) | per %s %s -> %s (delta %s)"
        % (code, CUTOFF, b0, DATE, b1, round(b1 + delta.get(code, 0.0), 2), delta.get(code, 0.0))
    )
dep_after = round(before[ACC_DEPOSIT][1] + delta.get(ACC_DEPOSIT, 0.0), 2)
if dep_after > 0.005:
    log(
        "PERHATIAN: 2103100003 berakhir SALDO DEBIT %s -- akun liability dengan saldo debit. "
        "Ini konsekuensi yang sudah diketahui, bukan bug." % dep_after
    )
for code in (ACC_AR, ACC_DEPOSIT):
    log(
        "mutasi adjustment %s: %s %s -> %s"
        % (OU_NAME, code, before_ou[code], round(before_ou[code] + delta.get(code, 0.0), 2))
    )
log("selesai (%s)" % ("COMMIT" if CONFIRM else "dry-run, rollback saat shell keluar"))
