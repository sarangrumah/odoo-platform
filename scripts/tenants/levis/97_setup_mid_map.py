# Mengisi levis.bank.mid.map -- prd_levis_begbal.
#
# Dijalankan lewat odoo shell (butuh ORM):
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       --shell-interface=python < scripts/tenants/levis/97_setup_mid_map.py
#
# Env:  CONFIRM=1  -> benar-benar menulis + commit. Tanpa ini: DRY RUN
#                     (semua di-rollback di akhir, tapi ringkasannya tetap dicetak).
#
# --------------------------------------------------------------------------
# Kenapa daftar ini boleh dipercaya
# --------------------------------------------------------------------------
# Modul sengaja tidak menyemai tabel ini: nama toko pada narasi bank adalah
# SINGKATAN, bukan potongan -- "LEVIS BIP" itu Bandung Indah Plaza, "LEVIS
# GANCIT" itu Gandaria City -- dan menebak dari inisial akan menyalurkan uang ke
# toko yang salah. Jadi tiap baris di bawah berdiri di atas DUA bukti yang
# dikumpulkan dari data Juli 2026 (2.857 baris, Rp 19,14 M):
#
#   1. Nama pada narasi, dicocokkan ke daftar Operating Unit yang ada.
#   2. Kecocokan angka: gross tiap settlement dibandingkan dengan debit piutang
#      tender (levis.clearing.config.pos_receivable_account_ids) pada hari yang
#      sama +/- 2 hari. Kalau hanya satu toko yang punya angka itu, toko tersebut
#      dapat satu suara.
#
# Bukti kedua inilah yang menjawab jebakan yang paling berbahaya: BRI memotong
# nama di 13 karakter, sehingga "LEVIS SENAYA" bisa berarti Plaza Senayan ATAU
# Senayan City. TID 1999632290 mendapat 14 suara Senayan City dan nol suara Plaza
# Senayan, jadi ia Senayan City -- dan Plaza Senayan ternyata punya TID sendiri
# (1999632291, "LEVIS PL").
#
# Yang TIDAK ada di daftar ini, karena buktinya tidak cukup, sengaja dibiarkan
# tak terpetakan supaya uangnya tetap terlihat di suspense:
#
#   1999632287  Rp   1.548.533  "LEVIS GRAND"   -- satu baris, 7 Juli, nol kecocokan
#                               angka di toko mana pun. Nama dan posisi blok
#                               mengarah ke Grand Indonesia, tapi GI justru nol
#                               saldo di akun BRI. Nama saja bukan bukti.
#
# 1999632289 (Rp 556.975.475, "LEVIS PONDOK") tadinya ada di daftar itu: bukti
# angkanya tidak menolong -- 53 settlement hanya menghasilkan 3 suara, dan
# ketiganya ke toko lain. Ia sekarang dipetakan ke Pondok Indah Mall 2 atas
# KONFIRMASI Finance (11-Aug-2026), bukan atas kesimpulan skrip ini. Yang
# menguatkan: PIM 1 sudah dipegang 1999632288, dan kedua TID itu berurutan.
#
# DUA SUMBU BUKTI TAMBAHAN (11-Aug-2026) menutup tiga terminal yang tadinya di
# daftar itu. Keduanya tidak menyentuh nama sama sekali:
#
#   AKUN TENDER MENYEBUT BANKNYA. `1106000108 = POS Receivable -
#   OFFLINE_BRI_CREDIT_CARD`, jadi hanya toko dengan saldo di akun itu yang pernah
#   menerima kartu BRI. Itu menyelesaikan 1999664887 secara telak: seluruh jejak
#   BRI Grand Metropolitan Bekasi sepanjang Juli hanya SATU baris -- 14 Juli,
#   Rp 2.581.600 -- dan ketiga settlement TID ini jatuh pada 14 Juli dengan jumlah
#   persis Rp 2.581.600 (300.900 + 600.950 + 1.679.750).
#
#   NOMOR TERMINAL TERSUSUN PER WILAYAH. Blok 1999660757..763 seluruhnya Bandung
#   dan Surabaya (758 Trans Studio Bandung, 759 Summarecon Bandung, 760 Paris Van
#   Java, 761 Pakuwon Surabaya, 762 Tunjungan Plaza 3, 763 Galaxy Mall 3), dan
#   1999660757 berada di kepalanya. Bandung Indah Plaza adalah satu-satunya toko
#   Bandung tanpa terminal BRI. Ditambah 3 dari 13 baris yang punya kecocokan
#   angka, dan BIP muncul di ketiganya -- sekali justru di akun 1106000108 itu
#   sendiri (12 Juli, Rp 1.049.900).
#
# Pacific Place Mall tereliminasi dari seluruh kandidat: nol aktivitas POS Juli.
#
# Setoran tunai (475 baris, Rp 1,12 M) juga di luar cakupan skrip ini: kuncinya
# teks bebas yang diketik kasir, 224 variasi, dan sebagiannya cuma nama orang.
#
# --------------------------------------------------------------------------
# Catatan teknis
# --------------------------------------------------------------------------
# * BCA memakai MID, BRI memakai TID -- match_type-nya berbeda dan tidak boleh
#   tertukar, karena parser mengisi field yang berbeda.
# * Kunci BCA ditulis dalam bentuk panjang (885004608375). Feed kartu kredit
#   mencetak merchant yang sama tanpa prefix acquirer (4608375); _keys_match
#   menerima kecocokan sufiks >= 6 digit, jadi satu aturan menutup keduanya.
# * journal_id dibiarkan kosong supaya aturan berlaku untuk semua feed bank
#   (satu merchant id hanya milik satu toko, apa pun jurnalnya).
# * channel hanya untuk pelaporan; akun piutangnya ditemukan dari baris POS yang
#   terbuka, bukan dari field ini.

import os
import sys

CONFIRM = os.environ.get("CONFIRM") == "1"

MAP = env["levis.bank.mid.map"]
company = env.company

# (match_type, key, nama Operating Unit, channel, label)
ROWS = [
    # --- BCA -------------------------------------------------------------
    ("mid", "885004608375", "OLS SES - GRAND INDONESIA", "debit", "Grand Indonesia"),
    ("mid", "885004632717", "OLS SES - TUNJUNGAN PLAZA 3", "debit", "Tunjungan Plaza 3"),
    ("mid", "885004608391", "OLS SES - PONDOK INDAH MALL 2", "debit", "Pondok Indah Mall 2"),
    ("mid", "885004608387", "OLS SES - SENAYAN CITY", "debit", "Senayan City"),
    ("mid", "885004608403", "OLS SES - PLAZA SENAYAN", "debit", "Plaza Senayan"),
    ("mid", "885004632683", "OLS SES - PARIS VAN JAVA", "debit", "Paris Van Java"),
    ("mid", "885004608383", "OLS SES - KELAPA GADING MALL", "debit", "Kelapa Gading Mall"),
    ("mid", "885004608399", "OLS SES - CENTRAL PARK", "debit", "Central Park"),
    ("mid", "885004632721", "OLS SES - PAKUWON MALL SURABAYA", "debit", "Pakuwon Mall Surabaya"),
    ("mid", "885004632691", "OLS SES - TRANS STUDIO MALL BANDUNG", "debit", "Trans Studio Mall Bandung"),
    ("mid", "885004648635", "OLS SES - TRANS STUDIO CIBUBUR", "debit", "Trans Studio Cibubur"),
    ("mid", "885004648627", "OLS SES - AEON BSD CITY", "debit", "AEON BSD City"),
    ("mid", "885004632687", "OLS SES - SUMMARECON MALL BANDUNG", "debit", "Summarecon Mall Bandung"),
    ("mid", "885004608395", "OLS SES - PONDOK INDAH MALL 1", "debit", "Pondok Indah Mall 1"),
    ("mid", "885004648615", "OLS SES - GANDARIA CITY", "debit", "Gandaria City"),
    ("mid", "885004648619", "OLS SES - LOTTE SHOPPING AVENUE", "debit", "Lotte Shopping Avenue"),
    ("mid", "885004632695", "OLS SES - BANDUNG INDAH PLAZA", "debit", "Bandung Indah Plaza"),
    ("mid", "885004632679", "OLS SES - GALAXY MALL 3", "debit", "Galaxy Mall 3"),
    ("mid", "885004704536", "OLS SES - PASKAL BANDUNG", "debit", "Paskal Bandung"),
    ("mid", "885004648623", "OLS SES - METROPOLITAN MALL BEKASI", "debit", "Metropolitan Mall Bekasi"),
    ("mid", "885004648631", "OLS SES - GRAND METROPOLITAN BEKASI", "debit", "Grand Metropolitan Bekasi"),
    ("mid", "885004618292", "OLS SES - MALL OF INDONESIA", "debit", "Mall of Indonesia"),
    # --- BRI -------------------------------------------------------------
    ("tid", "1999639781", "OLS SES - MALL OF INDONESIA", "debit", "Mall of Indonesia"),
    ("tid", "1999660760", "OLS SES - PARIS VAN JAVA", "qris", "Paris Van Java"),
    ("tid", "1999632292", "OLS SES - KELAPA GADING MALL", "debit", "Kelapa Gading Mall"),
    ("tid", "1999632290", "OLS SES - SENAYAN CITY", "debit", "Senayan City"),
    ("tid", "1999664883", "OLS SES - GANDARIA CITY", "debit", "Gandaria City"),
    ("tid", "1999632288", "OLS SES - PONDOK INDAH MALL 1", "debit", "Pondok Indah Mall 1"),
    # Dikonfirmasi Finance 11-Aug-2026, bukan hasil pencocokan angka.
    ("tid", "1999632289", "OLS SES - PONDOK INDAH MALL 2", "debit", "Pondok Indah Mall 2"),
    ("tid", "1999664888", "OLS SES - TRANS STUDIO CIBUBUR", "debit", "Trans Studio Cibubur"),
    ("tid", "1999660763", "OLS SES - GALAXY MALL 3", "qris", "Galaxy Mall 3"),
    ("tid", "1999660758", "OLS SES - TRANS STUDIO MALL BANDUNG", "debit", "Trans Studio Mall Bandung"),
    ("tid", "1999664886", "OLS SES - AEON BSD CITY", "qris", "AEON BSD City"),
    ("tid", "1999660762", "OLS SES - TUNJUNGAN PLAZA 3", "debit", "Tunjungan Plaza 3"),
    ("tid", "1999632291", "OLS SES - PLAZA SENAYAN", "qris", "Plaza Senayan"),
    ("tid", "1999632293", "OLS SES - CENTRAL PARK", "debit", "Central Park"),
    ("tid", "1999660759", "OLS SES - SUMMARECON MALL BANDUNG", "qris", "Summarecon Mall Bandung"),
    ("tid", "1999675383", "OLS SES - PASKAL BANDUNG", "debit", "Paskal Bandung"),
    # Bukti akun tender + blok wilayah, 11-Aug-2026 -- lihat catatan di atas.
    ("tid", "1999664887", "OLS SES - GRAND METROPOLITAN BEKASI", "debit", "Grand Metropolitan Bekasi"),
    ("tid", "1999660757", "OLS SES - BANDUNG INDAH PLAZA", "debit", "Bandung Indah Plaza"),
]

NOTE = "Diisi 11-Aug-2026 dari data Juli: nama pada narasi + kecocokan gross vs piutang tender harian per toko."


def run():
    dibuat = dilewati = 0
    salah_ou = []
    for match_type, key, ou_name, channel, label in ROWS:
        # Dicari lewat NAMA, bukan id. Id analytic berbeda per database, dan id
        # yang kebetulan ada bukan berarti toko yang benar -- memetakan ke toko
        # yang salah adalah persis kesalahan yang tabel ini ada untuk mencegah.
        analytic = env["account.analytic.account"].search([("name", "=", ou_name)], limit=1)
        if not analytic:
            salah_ou.append((key, ou_name))
            continue
        # Dibandingkan dalam bentuk TERNORMALISASI, bukan string mentah. Bank
        # mencetak terminal yang sama sebagai "001999632289" dan "1999632289";
        # membandingkan apa adanya menghasilkan aturan kembar yang menunjuk toko
        # yang sama -- persis yang terjadi 11-Aug-2026 di prd_levis_begbal, saat
        # skrip ini dan sesi lain sama-sama memetakan TID 1999632289.
        wanted = MAP._normalise_key(key)
        ada = MAP.search([("company_id", "=", company.id), ("match_type", "=", match_type)]).filtered(
            lambda r: MAP._normalise_key(r.key) == wanted
        )
        if ada:
            dilewati += 1
            continue
        MAP.create(
            {
                "name": "%s (%s)" % (label, "BCA" if match_type == "mid" else "BRI"),
                "company_id": company.id,
                "match_type": match_type,
                "key": key,
                "channel": channel,
                "analytic_account_id": analytic.id,
                "note": NOTE,
            }
        )
        dibuat += 1

    if salah_ou:
        # Id analytic berbeda per database. Berhenti daripada memetakan ke toko
        # yang salah -- itu persis kesalahan yang tabel ini ada untuk mencegah.
        print("BATAL: Operating Unit tidak ditemukan: %s" % salah_ou, file=sys.stderr)
        env.cr.rollback()
        return

    total = MAP.search_count([("company_id", "=", company.id)])
    print(
        "dibuat=%d dilewati(sudah ada)=%d total aturan=%d" % (dibuat, dilewati, total),
        file=sys.stderr,
    )

    # Baca ulang narasi supaya baris statement yang sudah ada ikut mendapat OU:
    # compute-nya sengaja tidak bergantung pada tabel ini.
    lines = env["account.bank.statement.line"].search([("levis_narrative_kind", "in", ("settlement", "cash_deposit"))])
    lines.action_levis_reread_narrative()
    ber_ou = len(lines.filtered("levis_ou_analytic_id"))
    nilai = sum(lines.filtered("levis_ou_analytic_id").mapped("amount"))
    print(
        "baris settlement/cash=%d, ber-OU=%d (Rp %s)" % (len(lines), ber_ou, "{:,.0f}".format(nilai)),
        file=sys.stderr,
    )

    if CONFIRM:
        env.cr.commit()
        print("COMMIT", file=sys.stderr)
    else:
        env.cr.rollback()
        print("DRY RUN -- di-rollback. Jalankan ulang dengan CONFIRM=1 untuk menyimpan.", file=sys.stderr)


run()
