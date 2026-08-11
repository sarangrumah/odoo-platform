"""Melengkapi levis.bank.mid.map -- setoran tunai + 2 terminal BRI sisa.

Lanjutan dari ``97_setup_mid_map.py``, yang memetakan 37 merchant id kartu/QRIS
dan sengaja meninggalkan dua hal:

  * 475 baris setoran tunai (Rp 1,12 M) -- kuncinya teks bebas yang diketik
    kasir, 224 variasi, sebagiannya cuma nama orang;
  * 5 terminal BRI yang bukti angkanya waktu itu belum konklusif.

Keduanya bisa diselesaikan tanpa membaca teks, dengan dua metode di bawah.

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
        < scripts/tenants/levis/98_setup_mid_map_cash.py

Env: CONFIRM=1 -> menulis + commit. Tanpa itu DRY RUN (di-rollback, ringkasan
tetap dicetak). Idempoten: kunci yang sudah ada dilewati.

--------------------------------------------------------------------------
1. Nama kasir sebagai kunci, dipilih dengan diuji
--------------------------------------------------------------------------
Satu kasir menyetor untuk satu toko, jadi namanya adalah kunci yang stabil --
lebih stabil daripada kata tokonya, yang penulisannya berubah tiap setoran
("cash sales pvj", "stor cash ols pvj", "setoran ols pvj"). Tapi nama itu tidak
DIBACA untuk menyimpulkan tokonya; toko ditentukan oleh angka:

  gross setoran dibandingkan dengan debit PERSIS piutang tender POS yang masih
  terbuka pada hari transaksi +/- 2 hari. Kalau hanya satu toko punya angka itu,
  itu satu suara untuk toko tersebut.

Kunci diterima hanya bila suaranya BULAT dan >= 3 baris setuju. Yang tersisa
dibiarkan tak terpetakan supaya uangnya tetap terlihat di suspense: 30 kunci
suaranya kurang atau terpecah, dan 43 baris (Rp 125 jt) tidak punya nama yang bisa
dipakai sama sekali.

SUMBU YANG DIPERTAJAM (11-Aug-2026): nama akun tender menyebut tender-nya
(`1106000101 = POS Receivable - CASH`), jadi setoran tunai dicocokkan HANYA ke akun
kas -- bukan ke sepuluh akun tender seperti pengukuran pertama. Kolam menyempit dari
2.641 debit ke 396, suara palsu dari piutang kartu hilang, dan tiga kunci tambahan
jadi konklusif: RYMA NURGHAIDA FER, DIANA ANDRIYANI, ARYO ANGGA RUSMANA (Rp 11,2 jt,
masing-masing 3 suara bulat). Yang menenangkan: NOL kunci lama hilang dan NOL kunci
berubah toko, jadi sumbu yang lebih tajam ini murni lebih baik, bukan pertukaran.
Sumbu ini datang dari sesi bank-reconcile, dan ia juga membongkar defect di
`_allocate` yang dulu membiarkan setoran tunai melunasi piutang kartu.

Jebakan yang harus dijaga: aturan keyword cocok secara SUBSTRING. "SOPIAN
PERMANA" ada di dalam "SMB SOPIAN PERMANA" -- satu kasir, dua toko Bandung -- jadi
sebelum sebuah kunci diterima, SEMUA baris yang akan tersambar olehnya diperiksa;
kalau ada yang memilih toko lain, kunci itu ditolak.

Cek-silang yang menguatkan (dipakai untuk MEMBENARKAN, bukan menyimpulkan):
sesudah angka memilih toko, singkatan di teksnya cocok delapan kali berturut --
pvj=Paris Van Java, CP=Central Park, tp3=Tunjungan Plaza 3, p kwn=Pakuwon,
GI=Grand Indonesia, SMBD=Summarecon Mall Bandung, Pim 1=Pondok Indah Mall 1,
Aeon=AEON BSD City.

--------------------------------------------------------------------------
2. Eliminasi lewat sisa piutang per toko
--------------------------------------------------------------------------
Untuk terminal besar yang tidak mendapat suara. Setelah semua yang lain
dialokasikan, hitung (piutang terbuka - yang terkonsumsi) per toko; toko yang
menyisakan sebesar terminal itu adalah pemiliknya.

  TID 001999660761 "LEVIS PAK"     Rp 19,6 jt
      -> Pakuwon menyisakan Rp 18,9 jt.

Terminal kedua yang dulu ada di sini, 1999632289 "LEVIS PONDOK" (Rp 557,0 jt),
sekarang dipetakan oleh skrip 97 atas KONFIRMASI Finance, dan barisnya di sini
sudah dicabut supaya satu terminal tidak dipetakan oleh dua skrip. Yang
menenangkan: eliminasi di sini sampai pada toko yang SAMA lebih dulu, murni dari
buku besar -- PIM 2 menyisakan Rp 551,8 jt sementara toko berikutnya hanya
Rp 157 jt, dan PIM 1 sudah dipegang 1999632288. Jadi bukti angka dan konfirmasi
Finance saling menguatkan, bukan bertabrakan.

Divalidasi lewat PREDIKSI, bukan kecocokan saja: setelah dipetakan, sisa PIM 2
runtuh dari 551.823.858 ke -1.000 dan Pakuwon dari 18.932.897 ke 0. Kalau sisa
sebuah toko TIDAK runtuh setelah terminalnya dipetakan, pemetaannya salah.

Tiga TID yang tetap dibiarkan: 1999660757 "LEVIS BANDUNG" (Rp 16,4 jt, ada empat
toko Bandung), 1999664887 "LEVIS GR" (Rp 2,6 jt) dan 1999632287 "LEVIS GRAND"
(Rp 1,5 jt) -- Grand Indonesia atau Grand Metropolitan, sisanya tidak memisahkan
keduanya.

--------------------------------------------------------------------------
Hasil di prd_levis_begbal sesudah 97 + 98 (Compute Juli 2026)
--------------------------------------------------------------------------
teralokasi Rp 16,52 M (dari 11,16 M), unmapped Rp 242 jt / 135 baris (dari
4,27 M / 743), short Rp 35 jt / 14 baris (dari 5,64 M / 1.052), dan MDR simulasi
Rp 94.009.131 lawan Rp 94.186.099 dari jalur workbook EBR -- selisih 0,19%, yaitu
dua metode independen yang saling mengonfirmasi.

Toko di-resolve lewat NAMA, bukan id: id analytic berbeda per database, dan id
yang kebetulan ada bukan berarti toko yang benar.
"""

import os
import sys

env = env  # noqa: F821

CONFIRM = os.environ.get("CONFIRM") == "1"
MAP = env["levis.bank.mid.map"]
company = env.company

# (match_type, key, nama Operating Unit, channel)
ROWS = [
    ("tid", "001999660761", "OLS SES - PAKUWON MALL SURABAYA", "debit"),
    # --- setoran tunai: kunci = nama kasir --------------------------------
    ("keyword", "PARADILA ANDINI", "OLS SES - AEON BSD CITY", "cash"),
    ("keyword", "RADEA CIPTA PRADAN", "OLS SES - AEON BSD CITY", "cash"),
    ("keyword", "SITI MASITOH", "OLS SES - CENTRAL PARK", "cash"),
    ("keyword", "LIDYA AYU OCTAVIAN", "OLS SES - GALAXY MALL 3", "cash"),
    ("keyword", "RYMA NURGHAIDA FER", "OLS SES - GALAXY MALL 3", "cash"),
    ("keyword", "LINA KUMALA PUTRI", "OLS SES - GALAXY MALL 3", "cash"),
    ("keyword", "ADAM SURYONO", "OLS SES - GRAND INDONESIA", "cash"),
    ("keyword", "HELDA SELVY ANGGRA", "OLS SES - GRAND INDONESIA", "cash"),
    ("keyword", "MIFTAHUL JANNAH", "OLS SES - GRAND INDONESIA", "cash"),
    ("keyword", "IIN PITURIA", "OLS SES - KELAPA GADING MALL", "cash"),
    ("keyword", "TAUFAN SAPUTRA", "OLS SES - KELAPA GADING MALL", "cash"),
    ("keyword", "DIAN ANGGRAINI", "OLS SES - LOTTE SHOPPING AVENUE", "cash"),
    ("keyword", "DIANA ANDRIYANI", "OLS SES - LOTTE SHOPPING AVENUE", "cash"),
    ("keyword", "GRACE SALONIKA", "OLS SES - MALL OF INDONESIA", "cash"),
    ("keyword", "OCTAVIA EKA SARWAN", "OLS SES - MALL OF INDONESIA", "cash"),
    ("keyword", "ANISA NURUL NABILA", "OLS SES - METROPOLITAN MALL BEKASI", "cash"),
    ("keyword", "ARYO ANGGA RUSMANA", "OLS SES - METROPOLITAN MALL BEKASI", "cash"),
    ("keyword", "ANIS NUR HOLIPAH", "OLS SES - PAKUWON MALL SURABAYA", "cash"),
    ("keyword", "KINANTI EKA PUSPA", "OLS SES - PAKUWON MALL SURABAYA", "cash"),
    ("keyword", "NOVITA DEVI PURWAN", "OLS SES - PAKUWON MALL SURABAYA", "cash"),
    ("keyword", "ENDANG SAHLAN", "OLS SES - PARIS VAN JAVA", "cash"),
    ("keyword", "KEYSA SABIYANI", "OLS SES - PARIS VAN JAVA", "cash"),
    ("keyword", "RESTI FAJAR WATI", "OLS SES - PARIS VAN JAVA", "cash"),
    ("keyword", "OVIE DAYANI MARLIN", "OLS SES - PLAZA SENAYAN", "cash"),
    ("keyword", "SYARAH SILVIANA", "OLS SES - PLAZA SENAYAN", "cash"),
    ("keyword", "TRI HANDOYO", "OLS SES - PLAZA SENAYAN", "cash"),
    ("keyword", "CINDANA AMADHEA", "OLS SES - PONDOK INDAH MALL 1", "cash"),
    ("keyword", "NOFIAN ANUGRAH PUT", "OLS SES - PONDOK INDAH MALL 1", "cash"),
    ("keyword", "RIZKA NURAMELIA", "OLS SES - PONDOK INDAH MALL 1", "cash"),
    ("keyword", "ELING PURWATI", "OLS SES - PONDOK INDAH MALL 2", "cash"),
    ("keyword", "PIM MALINA ROFIKA", "OLS SES - PONDOK INDAH MALL 2", "cash"),
    ("keyword", "ROSYANA DHEA", "OLS SES - PONDOK INDAH MALL 2", "cash"),
    ("keyword", "ADE HERAWATI", "OLS SES - SENAYAN CITY", "cash"),
    ("keyword", "RETNO TRISTANTI", "OLS SES - SENAYAN CITY", "cash"),
    ("keyword", "SISILIA AGUSTIN", "OLS SES - SENAYAN CITY", "cash"),
    ("keyword", "ARINTA MAUDIANA", "OLS SES - SUMMARECON MALL BANDUNG", "cash"),
    ("keyword", "IGA NUGRAHA SUTRIA", "OLS SES - SUMMARECON MALL BANDUNG", "cash"),
    ("keyword", "CECE RIDWAN ALAWI", "OLS SES - TRANS STUDIO CIBUBUR", "cash"),
    ("keyword", "NOVIA MARCELLINA", "OLS SES - TRANS STUDIO MALL BANDUNG", "cash"),
    ("keyword", "SOPIAN PERMANA", "OLS SES - TRANS STUDIO MALL BANDUNG", "cash"),
    ("keyword", "VINNA FEBRIYANTI", "OLS SES - TRANS STUDIO MALL BANDUNG", "cash"),
    ("keyword", "MOCHAMAD ARSYAH", "OLS SES - TUNJUNGAN PLAZA 3", "cash"),
    ("keyword", "RANI BUDI LESTARI", "OLS SES - TUNJUNGAN PLAZA 3", "cash"),
]

NOTE_TID = (
    "Diisi 11-Aug-2026. Eliminasi: setelah semua terminal lain dialokasikan, toko ini "
    "satu-satunya yang menyisakan piutang sebesar terminal ini. Divalidasi lewat prediksi "
    "-- sisanya runtuh ke ~0 setelah dipetakan."
)
NOTE_KEYWORD = (
    "Diisi 11-Aug-2026. Kunci = nama kasir (satu kasir menyetor untuk satu toko). Toko "
    "ditentukan oleh kecocokan gross vs debit piutang tender terbuka, bulat dan >= 3 baris "
    "setuju, dan kunci sudah diuji tidak menyambar setoran toko lain."
)


def run():
    Analytic = env["account.analytic.account"]
    dibuat = dilewati = 0
    tidak_ketemu = []

    for match_type, key, ou_name, channel in ROWS:
        analytic = Analytic.search([("name", "=", ou_name)], limit=1)
        if not analytic:
            tidak_ketemu.append((key, ou_name))
            continue
        # Dibandingkan TERNORMALISASI, bukan string mentah. Bank mencetak terminal
        # yang sama sebagai "001999632289" dan "1999632289"; membandingkan apa
        # adanya melahirkan aturan kembar yang menunjuk toko yang sama -- itu
        # terjadi 11-Aug-2026 di prd_levis_begbal, saat skrip ini dan skrip 97
        # sama-sama memetakan TID yang sama dengan leading zero berbeda.
        # Kunci keyword tetap dibandingkan apa adanya: ia teks, bukan nomor.
        if match_type == "keyword":
            sudah_ada = MAP.search_count(
                [("company_id", "=", company.id), ("match_type", "=", "keyword"), ("key", "=", key)]
            )
        else:
            wanted = MAP._normalise_key(key)
            sudah_ada = bool(
                MAP.search([("company_id", "=", company.id), ("match_type", "=", match_type)]).filtered(
                    lambda r: MAP._normalise_key(r.key) == wanted
                )
            )
        if sudah_ada:
            dilewati += 1
            continue
        MAP.create(
            {
                "name": ("Setoran tunai -- %s" if match_type == "keyword" else "Terminal BRI -- %s")
                % analytic.display_name,
                "company_id": company.id,
                "match_type": match_type,
                "key": key,
                "channel": channel,
                "analytic_account_id": analytic.id,
                "sequence": 20 if match_type == "keyword" else 10,
                "note": NOTE_KEYWORD if match_type == "keyword" else NOTE_TID,
            }
        )
        dibuat += 1

    if tidak_ketemu:
        # Berhenti daripada memetakan ke toko yang salah -- itu persis kesalahan
        # yang tabel ini ada untuk mencegah.
        print("BATAL: Operating Unit tidak ditemukan: %s" % tidak_ketemu, file=sys.stderr)
        env.cr.rollback()
        return

    print(
        "dibuat=%d dilewati(sudah ada)=%d total aturan=%d"
        % (dibuat, dilewati, MAP.search_count([("company_id", "=", company.id)])),
        file=sys.stderr,
    )

    # Baca ulang narasi supaya baris statement yang sudah ada ikut mendapat OU:
    # compute-nya sengaja tidak bergantung pada tabel ini.
    lines = env["account.bank.statement.line"].search([("levis_narrative_kind", "in", ("settlement", "cash_deposit"))])
    lines.action_levis_reread_narrative()
    ber_ou = lines.filtered("levis_ou_analytic_id")
    print(
        "baris settlement/cash=%d, ber-OU=%d (Rp %s), tanpa OU=%d (Rp %s)"
        % (
            len(lines),
            len(ber_ou),
            "{:,.0f}".format(sum(ber_ou.mapped("amount"))),
            len(lines) - len(ber_ou),
            "{:,.0f}".format(sum((lines - ber_ou).mapped("amount"))),
        ),
        file=sys.stderr,
    )

    if CONFIRM:
        env.cr.commit()
        print("COMMIT", file=sys.stderr)
    else:
        env.cr.rollback()
        print("DRY RUN -- di-rollback. Jalankan ulang dengan CONFIRM=1 untuk menyimpan.", file=sys.stderr)


run()
