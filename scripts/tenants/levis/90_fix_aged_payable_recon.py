# Perbaikan open item Aged Payable -- prd_levis_begbal.
#
# Dijalankan lewat odoo shell (butuh ORM untuk .reconcile()):
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       --shell-interface=python < scripts/tenants/levis/90_fix_aged_payable_recon.py
#
# Env:  CONFIRM=1      -> benar-benar menulis + commit per kelompok.
#                         Tanpa ini: DRY RUN, rollback tiap kelompok.
#       DATE_TO=...     -> tanggal cut-off pelaporan (default 2026-07-31).
#       SKIP_EBRGL=1    -> lewati tahap B.
#       SKIP_PAYMENT=1  -> lewati tahap C.
#
# --------------------------------------------------------------------------
# Latar
# --------------------------------------------------------------------------
# Accounting melaporkan Aged Payable per 31/07/2026 tidak pernah "meniadakan"
# tagihan yang sudah dibayar: nomor bill dan nomor pembayarannya berdiri sebagai
# dua baris terpisah yang saling plus-minus, dan pada satu kasus pembayarannya
# berdiri sendiri sebagai AP minus. Penyebabnya bukan report: baris-baris itu
# memang tidak pernah direkonsiliasi satu sama lain di dalam Odoo, sehingga
# keduanya sah-sah saja tampil sebagai open item.
#
# Skrip ini HANYA merekonsiliasi baris yang sudah ada. Tidak ada jurnal baru,
# tidak ada nilai yang berubah, jadi saldo Trial Balance tidak bergeser sama
# sekali -- yang berubah hanya status open/close tiap baris.
#
# --------------------------------------------------------------------------
# Tiga tahap
# --------------------------------------------------------------------------
# A. LAPOR SAJA -- jurnal draft yang masih memegang rekonsiliasi.
#    Ditemukan satu: 8282/2026/07/042 (draft) reconciled ke bill posted
#    BILL/NT/EBR/2026/07/00040 sebesar Rp 75.405.550. Bill-nya jadi hilang dari
#    aging padahal TB (posted-only) masih mencatatnya -- persis sebesar selisih
#    itu. Skrip TIDAK menyentuhnya: memilih antara "post entry-nya" dan "batalkan
#    rekonsiliasinya" mengubah angka TB, jadi itu keputusan Finance.
#
# B. EBR-GL -- upload beginning balance memuat sisi tagihan (BILL/2026/06/xxxx)
#    dan sisi bank (BNK1/2026/xxxxx) dua-duanya ke akun payable tanpa pernah
#    saling direkonsiliasi. Net per 31/07/2026 = Rp 0,00 persis, jadi ini bukan
#    hutang terbuka, hanya sampah open item. Direkonsiliasi per partner, dengan
#    pengaman: kelompok yang net-nya bukan nol DILEWATI, tidak dipaksa.
#
# C. Pembayaran menggantung -- jurnal manual (move_type='entry') yang men-debit
#    akun payable tapi tidak pernah di-match ke bill mana pun:
#      8282/2026/07/009  Rp  69.090.728  PT Summarecon Investment Property
#      8282/2026/07/016  Rp 142.956.000  PT Metropolitan Land Tbk.
#      8282/2026/07/017  Rp  83.071.050  PT Bintang Bangun Mandiri
#    009 dan 017 punya lawan bill dengan nominal cocok persis, jadi direkonsiliasi.
#    016 TIDAK disentuh: bill-nya sudah lunas oleh 8282/2026/07/045 yang bernominal
#    sama persis, jadi 016 adalah kandidat dobel-catat (atau deposit) yang harus
#    diputuskan Finance -- lihat skrip 91 untuk laporannya.

import os
import sys
import traceback
from collections import defaultdict
from datetime import date

CONFIRM = os.environ.get("CONFIRM") == "1"
DATE_TO = date.fromisoformat(os.environ.get("DATE_TO", "2026-07-31"))
SKIP_EBRGL = os.environ.get("SKIP_EBRGL") == "1"
SKIP_PAYMENT = os.environ.get("SKIP_PAYMENT") == "1"

# Pasangan pembayaran -> bill untuk tahap C. Sengaja dituliskan eksplisit dan
# bukan dicocokkan otomatis by-amount: menebak pasangan atas nama Finance justru
# yang membuat kekacauan ini sulit ditelusuri.
PAIRS = [
    (
        "8282/2026/07/009",
        ["BILL/NT/EBR/2026/07/00086", "BILL/NT/EBR/2026/07/00087", "BILL/NT/EBR/2026/07/00088"],
    ),
    ("8282/2026/07/017", ["BILL/NT/EBR/2026/07/00014"]),
]

# 016 sengaja tidak masuk PAIRS. Didaftarkan di sini supaya tetap muncul di
# ringkasan sebagai "butuh keputusan", bukan diam-diam terlewat.
NEEDS_DECISION = {"8282/2026/07/016": "8282/2026/07/045"}

RP = "{:>18,.2f}".format


def rupiah(v):
    return RP(v).replace(",", "#").replace(".", ",").replace("#", ".")


env = env  # noqa: F821  -- disediakan odoo shell
AML = env["account.move.line"]

payable = env["account.account"].search([("account_type", "=", "liability_payable")])
if not payable:
    sys.exit("tidak ada akun bertipe liability_payable di database ini")

print("Perbaikan open item Aged Payable -- %s" % env.cr.dbname)
print("cut-off %s   mode %s" % (DATE_TO, "CONFIRM (menulis)" if CONFIRM else "DRY RUN"))
print("=" * 78)

lock = env.company.fiscalyear_lock_date
if lock and lock >= DATE_TO:
    print(
        "PERINGATAN: fiscalyear_lock_date = %s menutup periode cut-off. Rekonsiliasi\n"
        "murni tidak membuat jurnal, tapi kalau Odoo perlu selisih kurs / write-off\n"
        "ia akan ditolak. Kelompok yang ditolak akan dilaporkan, bukan dipaksa." % lock
    )

ringkasan = []


def jalankan(nama, fn):
    """Satu kelompok = satu transaksi. Commit hanya kalau CONFIRM."""
    env.cr.execute("SAVEPOINT grp")
    try:
        hasil = fn()
    except Exception as exc:  # noqa: BLE001 -- kelompok gagal tidak boleh menghentikan sisanya
        env.cr.execute("ROLLBACK TO SAVEPOINT grp")
        print("    GAGAL %s: %s" % (nama, exc))
        traceback.print_exc()
        return None
    if CONFIRM:
        env.cr.execute("RELEASE SAVEPOINT grp")
        env.cr.commit()
    else:
        env.cr.execute("ROLLBACK TO SAVEPOINT grp")
    return hasil


# --------------------------------------------------------------------------
# A. Jurnal draft yang memegang rekonsiliasi -- LAPOR SAJA
# --------------------------------------------------------------------------
print("\nA. Jurnal belum posted yang masih memegang rekonsiliasi")
print("-" * 78)
env.cr.execute(
    """
    select am.name, am.state, aml.id, aml.debit, aml.credit,
           coalesce(am2.name, '?') as lawan, p.amount
      from account_move_line aml
      join account_move am on am.id = aml.move_id
      join account_partial_reconcile p
        on p.debit_move_id = aml.id or p.credit_move_id = aml.id
      join account_move_line aml2
        on aml2.id = case when p.debit_move_id = aml.id
                          then p.credit_move_id else p.debit_move_id end
      left join account_move am2 on am2.id = aml2.move_id
     where am.state <> 'posted'
     order by am.name
    """
)
draft_rows = env.cr.fetchall()
if not draft_rows:
    print("    (tidak ada)")
else:
    for nama, state, lid, dr, cr_, lawan, amount in draft_rows:
        print(
            "    %-22s %-7s aml %-8s Dr %s  ter-match ke %s sebesar %s"
            % (nama, state, lid, rupiah(dr), lawan, rupiah(amount))
        )
    print(
        "    -> TIDAK diubah oleh skrip ini. Selama entry ini draft, TB (posted-only)\n"
        "       dan aging akan selisih persis sebesar nilai di atas. Finance harus\n"
        "       memutuskan: posting entry-nya, atau batalkan rekonsiliasinya."
    )
ringkasan.append(("A. draft memegang rekonsiliasi (lapor saja)", len(draft_rows), 0.0))


# --------------------------------------------------------------------------
# B. EBR-GL beginning balance
# --------------------------------------------------------------------------
def tahap_b():
    lines = AML.search(
        [
            ("account_id", "in", payable.ids),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("date", "<=", DATE_TO),
            ("move_id.ref", "=like", "EBR-GL%"),
        ]
    )
    per_partner = defaultdict(lambda: AML.browse())
    for line in lines:
        per_partner[(line.partner_id.id, line.account_id.id)] |= line

    direkon = 0
    dilewati = []
    for (pid, aid), grup in sorted(per_partner.items()):
        net = sum(grup.mapped("amount_residual"))
        nama = grup[:1].partner_id.display_name or "(tanpa partner)"
        if env.company.currency_id.compare_amounts(net, 0.0) != 0:
            dilewati.append((nama, len(grup), net))
            continue
        if not (any(l.amount_residual > 0 for l in grup) and any(l.amount_residual < 0 for l in grup)):
            # Satu sisi saja: tidak ada yang bisa dilawankan.
            dilewati.append((nama, len(grup), net))
            continue
        grup.reconcile()
        direkon += len(grup)
        print("    %-45s %3d baris  net %s  -> reconciled" % (nama[:45], len(grup), rupiah(net)))

    if dilewati:
        print("    DILEWATI (net bukan nol / satu sisi saja -- mungkin hutang sungguhan):")
        for nama, n, net in dilewati:
            print("      %-45s %3d baris  net %s" % (nama[:45], n, rupiah(net)))
    return direkon, len(lines)


if SKIP_EBRGL:
    print("\nB. EBR-GL -- DILEWATI (SKIP_EBRGL=1)")
else:
    print("\nB. EBR-GL beginning balance -- rekonsiliasi pasangan per partner")
    print("-" * 78)
    hasil_b = jalankan("tahap B", tahap_b)
    if hasil_b:
        direkon, total = hasil_b
        print("    %d dari %d baris EBR-GL direkonsiliasi" % (direkon, total))
        ringkasan.append(("B. baris EBR-GL direkonsiliasi", direkon, 0.0))


# --------------------------------------------------------------------------
# C. Pembayaran menggantung
# --------------------------------------------------------------------------
def payable_lines(move_name):
    move = env["account.move"].search([("name", "=", move_name)], limit=1)
    if not move:
        raise ValueError("move %s tidak ditemukan" % move_name)
    if move.state != "posted":
        raise ValueError("move %s state=%s, bukan posted" % (move_name, move.state))
    return move.line_ids.filtered(lambda l: l.account_id in payable)


def tahap_c():
    dipasangkan = 0
    nilai = 0.0
    for bayar_nama, bill_nama_list in PAIRS:
        bayar = payable_lines(bayar_nama)
        bills = AML.browse()
        for bn in bill_nama_list:
            bills |= payable_lines(bn)
        grup = bayar | bills
        terbuka = grup.filtered(lambda l: not l.reconciled and l.amount_residual)
        if len(terbuka) < 2:
            print("    %-22s sudah beres (tidak ada yang perlu di-match)" % bayar_nama)
            continue
        net = sum(terbuka.mapped("amount_residual"))
        partner = terbuka.mapped("partner_id")
        if len(partner) != 1:
            print("    %-22s DILEWATI: partner tidak seragam (%s)" % (bayar_nama, partner.mapped("name")))
            continue
        terbuka.reconcile()
        sisa = sum(terbuka.mapped("amount_residual"))
        dipasangkan += 1
        nilai += abs(sum(l.amount_residual for l in bayar))
        print(
            "    %-22s <-> %-60s"
            % (bayar_nama, ", ".join(bill_nama_list))
        )
        print(
            "        %s  net sebelum %s  sisa sesudah %s"
            % (partner.display_name[:40], rupiah(net), rupiah(sisa))
        )
    return dipasangkan, nilai


if SKIP_PAYMENT:
    print("\nC. Pembayaran menggantung -- DILEWATI (SKIP_PAYMENT=1)")
else:
    print("\nC. Pembayaran menggantung -- rekonsiliasi ke bill lawannya")
    print("-" * 78)
    hasil_c = jalankan("tahap C", tahap_c)
    if hasil_c:
        dipasangkan, nilai = hasil_c
        ringkasan.append(("C. pasangan bayar<->bill direkonsiliasi", dipasangkan, nilai))

    print("\n    BUTUH KEPUTUSAN FINANCE (tidak disentuh skrip):")
    for bayar_nama, kembar in NEEDS_DECISION.items():
        m = env["account.move"].search([("name", "in", [bayar_nama, kembar])])
        for mv in m.sorted("name"):
            pl = mv.line_ids.filtered(lambda l: l.account_id in payable)
            print(
                "      %-22s %s  Dr %s  residual %s  %s"
                % (
                    mv.name,
                    mv.date,
                    rupiah(sum(pl.mapped("debit"))),
                    rupiah(sum(pl.mapped("amount_residual"))),
                    "sudah reconciled" if all(l.reconciled for l in pl) else "MASIH TERBUKA",
                )
            )
        print(
            "      -> nominal keduanya sama persis. Salah satunya kemungkinan dobel-catat,\n"
            "         atau %s memang deposit yang belum ada tagihannya." % bayar_nama
        )


# --------------------------------------------------------------------------
print("\n" + "=" * 78)
print("RINGKASAN")
for nama, n, nilai in ringkasan:
    print("  %-45s %5d  %s" % (nama, n, rupiah(nilai) if nilai else ""))
if not CONFIRM:
    print("\n  DRY RUN -- semua perubahan sudah di-rollback. Set CONFIRM=1 untuk menulis.")
