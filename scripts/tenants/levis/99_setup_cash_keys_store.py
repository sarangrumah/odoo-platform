"""Kunci setoran tunai yang MENYEBUT NAMA TOKO -- levis.bank.mid.map.

Pelengkap ``98_setup_mid_map_cash.py``, dan sengaja terpisah karena KELAS
BUKTINYA BERBEDA:

  * Skrip 98 memetakan nama KASIR. Orangnya bisa pindah toko, jadi tiap kunci
    harus dieliminasi lewat buku besar sebelum boleh dipercaya.
  * Skrip ini memetakan teks yang diketik kasir yang MENYEBUT TOKONYA SENDIRI
    ("setoran cash bip", "cash ols paskal", "Setoran Ols Gancit"). Itu pernyataan
    asal-usul langsung -- bukan singkatan yang dipotong bank seperti pada narasi
    kartu, di mana menebak dari inisial memang berbahaya.

Perbedaan itu penting: yang membuat nama toko pada narasi KARTU tidak boleh
dipercaya adalah bahwa bank yang menuliskannya, terpotong dan tanpa konteks.
Di sini justru orang yang menyetorkan uang yang mengetiknya, dan ia tahu ia
menyetor untuk toko mana.

Sekalipun begitu, tiap baris di bawah tetap DIKUATKAN bukti angka: jumlah
setoran dicocokkan dengan debit piutang KAS (1106000101) toko tersebut pada
hari yang sama +/- 3 hari. Nama dan angka sepakat di kesebelasnya.

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \\
        --shell-interface=python < scripts/tenants/levis/99_setup_cash_keys_store.py

Env:  CONFIRM=1 -> menulis + commit. Tanpa itu: DRY RUN (rollback di akhir).

--------------------------------------------------------------------------
Cakupan
--------------------------------------------------------------------------
Dari 130 baris setoran tunai yang belum terpetakan (74 kunci, Rp 247.345.748):

    token       baris        nilai  toko                      suara angka
    ols tp3        18   97.607.907  Tunjungan Plaza 3              15
    tsc            47   51.468.544  Trans Studio Cibubur           19
    bip            17   17.039.872  Bandung Indah Plaza            12
    gancit          4    6.704.500  Gandaria City                   2
    paskal          2    5.853.300  Paskal Bandung                  2
    sency           2    5.330.300  Senayan City                    2
    ols cp          1    5.100.200  Central Park                    1
    levis c p       1    4.550.525  Central Park                    1
    pakuwon         1    1.702.750  Pakuwon Mall Surabaya           1
    aeon            2      100.000  AEON BSD City                   4
    setor cp        1       50.000  Central Park                    1

Total 96 baris, Rp 195.507.898.

SENGAJA TIDAK DIMASUKKAN -- ``mmb``, 7 baris, Rp 8.744.000. Namanya jelas
mengarah ke Metropolitan Mall Bekasi ("Sales Cash Ols MMB Tgl"), tetapi
satu-satunya suara angka justru jatuh ke Senayan City. Satu suara dari tujuh
baris terlalu lemah ke dua arah. Dibiarkan di suspense sampai ada yang bisa
memutuskan.

Sisa 27 baris (Rp 43.093.850) tidak menyebut toko sama sekali -- itu tetap
wilayah skrip 98.

--------------------------------------------------------------------------
Catatan teknis
--------------------------------------------------------------------------
* Token pendek seperti ``bip`` aman KARENA ``_resolve`` sekarang memenangkan
  kunci TERPANJANG yang cocok (PR #138). Aturan kasir yang lebih spesifik tetap
  menang bila keduanya cocok pada satu narasi. Sebelum perbaikan itu, yang
  memutuskan adalah urutan alfabet.
* Penjaga tabrakan pada model menolak kunci yang identik dengan aturan yang
  sudah ada, jadi menjalankan ulang skrip ini tidak bisa melahirkan kembar.
* Kunci disimpan huruf kecil; pencocokan memang case-insensitive.
"""

import os
import sys

CONFIRM = os.environ.get("CONFIRM") == "1"

MAP = env["levis.bank.mid.map"]
company = env.company

# (kunci, nama Operating Unit, label)
ROWS = [
    ("ols tp3", "OLS SES - TUNJUNGAN PLAZA 3", "Tunjungan Plaza 3"),
    ("tsc", "OLS SES - TRANS STUDIO CIBUBUR", "Trans Studio Cibubur"),
    ("bip", "OLS SES - BANDUNG INDAH PLAZA", "Bandung Indah Plaza"),
    ("gancit", "OLS SES - GANDARIA CITY", "Gandaria City"),
    ("paskal", "OLS SES - PASKAL BANDUNG", "Paskal Bandung"),
    ("sency", "OLS SES - SENAYAN CITY", "Senayan City"),
    ("ols cp", "OLS SES - CENTRAL PARK", "Central Park"),
    ("levis c p", "OLS SES - CENTRAL PARK", "Central Park"),
    ("setor cp", "OLS SES - CENTRAL PARK", "Central Park"),
    ("pakuwon", "OLS SES - PAKUWON MALL SURABAYA", "Pakuwon Mall Surabaya"),
    ("aeon", "OLS SES - AEON BSD CITY", "AEON BSD City"),
]

NOTE = (
    "Diisi 11-Aug-2026: narasi setoran menyebut tokonya sendiri, dikuatkan kecocokan "
    "jumlah setoran dengan piutang kas (1106000101) toko itu pada hari yang sama."
)


def run():
    dibuat = dilewati = ditolak = 0
    hilang = []
    for key, ou_name, label in ROWS:
        analytic = env["account.analytic.account"].search([("name", "=", ou_name)], limit=1)
        if not analytic:
            hilang.append((key, ou_name))
            continue
        # Perbandingan case-insensitive: kunci keyword adalah teks, dan
        # _normalise_key (yang dipakai untuk MID/TID) akan menghabiskannya jadi
        # kosong karena ia hanya menyisakan digit.
        ada = MAP.search([("company_id", "=", company.id), ("match_type", "=", "keyword")]).filtered(
            lambda r, k=key: (r.key or "").strip().lower() == k
        )
        if ada:
            dilewati += 1
            continue
        try:
            MAP.create(
                {
                    "name": "%s (setoran tunai)" % label,
                    "company_id": company.id,
                    "match_type": "keyword",
                    "key": key,
                    "channel": "cash",
                    "analytic_account_id": analytic.id,
                    "note": NOTE,
                }
            )
            dibuat += 1
        except Exception as exc:  # penjaga tabrakan pada model
            ditolak += 1
            print("DITOLAK '%s': %s" % (key, str(exc)[:150]), file=sys.stderr)

    if hilang:
        print("BATAL: Operating Unit tidak ditemukan: %s" % hilang, file=sys.stderr)
        env.cr.rollback()
        return

    print(
        "dibuat=%d dilewati(sudah ada)=%d ditolak=%d total aturan=%d"
        % (dibuat, dilewati, ditolak, MAP.search_count([("company_id", "=", company.id)])),
        file=sys.stderr,
    )

    lines = env["account.bank.statement.line"].search([("levis_narrative_kind", "in", ("settlement", "cash_deposit"))])
    lines.action_levis_reread_narrative()
    ber = lines.filtered("levis_ou_analytic_id")
    print(
        "baris settlement/kas=%d, ber-OU=%d (Rp %s)"
        % (len(lines), len(ber), "{:,.0f}".format(sum(ber.mapped("amount")))),
        file=sys.stderr,
    )

    if CONFIRM:
        env.cr.commit()
        print("COMMIT", file=sys.stderr)
    else:
        env.cr.rollback()
        print("DRY RUN -- di-rollback. Jalankan ulang dengan CONFIRM=1 untuk menyimpan.", file=sys.stderr)


run()
