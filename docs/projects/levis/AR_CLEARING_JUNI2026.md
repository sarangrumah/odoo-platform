# AR Clearing atas posisi Juni 2026 — catatan eksekusi

Catatan eksekusi `scripts/tenants/levis/69_ar_adjustments_juni.py` (script dibuat di
commit `f588f3d` bersama 67/68).

- **Dieksekusi:** 4-Aug-2026 di **kedua** DB `prd_levis_begbal` dan `prd_levis`
- **Tanggal buku: 01-Jul-2026** — angka Juni tidak boleh berubah (lihat di bawah)
- **Posisi pengukuran: 30-Jun-2026** — seluruh nilai diukur pada tutup buku Juni
- **Approval:** disetujui untuk clearing saja — entry SALESMANUAL sengaja tidak dijalankan
- **Sumber angka:** workbook FICO *EBR - Check Selisih Outstanding AR Finance vs Accounting
  Juni 2026.xlsx*, direproduksi oleh `67_rekon_ar_juni_final.py`

## Kenapa dibukukan di Juli

Eksekusi pertama pagi itu memakai tanggal 30-Jun dan sudah ter-posting. Setelah itu baru
tegas bahwa **klien tidak mau angka Juni berubah sama sekali** — Juni sudah dilaporkan.
Ketiga jurnal karena itu **dihapus** dari Juni lalu dibuat ulang bertanggal 01-Jul.

Dipilih hapus, bukan reverse: reversal memang mengembalikan saldo, tapi tetap menambah
mutasi ~1,3 M dan 152 baris GL di periode yang sudah ditutup — persis yang tidak diinginkan.
Penghapusan aman di kasus ini karena jurnalnya baru berumur beberapa jam, belum
ter-rekonsiliasi sama sekali, dan memegang nomor terakhir rangkaian Juni sehingga tidak
meninggalkan gap. Kedua syarat itu di-*enforce* oleh `78_undo_ar_adjustments_juni.py`, yang
menolak jalan kalau salah satunya tidak terpenuhi.

**Bukti Juni utuh:** total debit Juni kembali ke 56.944.332.342,84, turun tepat 677.663.944
— sama persis dengan jumlah debit ketiga jurnal. Tidak ada sisa turnover.

## Perintah yang dijalankan

Backup dulu — tidak ada backup otomatis untuk DB tenant:

```
docker exec -e PGPASSWORD="$PW" odoo19-platform-postgres pg_dump -U odoo -Fc -d <db> \
  > /opt/odoo-platform/backups/<db>_20260804_pre_move_to_july.dump
```

Lalu, dari `/opt/odoo-platform` (bukan checkout `/home` — lihat memory
`odoo-platform-checkouts`; kedua salinan script sudah identik saat itu):

```
docker exec -i odoo19-platform-odoo odoo shell -d <db> --no-http \
  < scripts/tenants/levis/78_undo_ar_adjustments_juni.py

docker exec -i -e ADJ_POST=1 -e ADJ_DATE=2026-07-01 -e ADJ_CUTOFF=2026-06-30 \
  odoo19-platform-odoo odoo shell -d <db> --no-http \
  < scripts/tenants/levis/69_ar_adjustments_juni.py
```

`ADJ_DATE` dan `ADJ_CUTOFF` sengaja dipisah. Kalau keduanya menyatu, menggeser tanggal buku
ke Juli otomatis menggeser basis perhitungan juga, dan clearing akan dihitung terhadap saldo
yang sudah bergerak. Default keduanya tetap 2026-06-30 (perilaku lama).

Kebetulan yang menolong di sini: deposit 2103100003 dan AR 1106000001 **tidak bergerak sama
sekali sepanjang Juli** (671.710.641 dan 1.025.747.288 baik per 30-Jun maupun 31-Jul), jadi
angka clearing-nya identik dengan hitungan semula. Kalau Juli sempat bergerak, `ADJ_CUTOFF`
inilah yang menjaga hasilnya tetap benar.

## Hasil

Tiga jurnal GLJV **tanggal 01-Jul-2026**, status `posted`, seluruh baris ber-Operating Unit:

| Ref | Isi | Baris | Debit |
|---|---|---|---|
| `EBR-ADJ-AR-JUNI-2026-REALOKASI` | deposit antar-OU, saldo akun tidak berubah | 10 | 9.612.964 |
| `EBR-ADJ-AR-JUNI-2026-MDR` | Dr 7104000001 / Cr 1106000001 | 30 | 527.265 |
| `EBR-ADJ-AR-JUNI-2026-CLEARING` | Dr 2103100003 / Cr 1106000001 per OU | 36 | 667.523.715 |

Nomor: `prd_levis_begbal` GLJV/2026/07/0013–0015, `prd_levis` GLJV/2026/07/0001–0003.

Saldo — **identik di kedua DB**:

| Akun | per 30-Jun (tidak berubah) | per 01-Jul |
|---|---|---|
| 1106000001 Trade Receivables | 1.025.747.288 | **357.696.308** |
| 2103100003 Deposit from customer trade | −671.710.641 | **−4.186.926** |
| 7104000001 MDR Bank | 25.971.461,73 | **26.498.726,73** |

Sisa AR 357.696.308 cocok dengan dekomposisi FICO: REKON JUL 148.813.668 + kas belum setor
7.940.708 + lag settlement akhir Juni 197.282.271 + TBFU belum ter-clear 4.186.926
− MDR 527.265.

Sisa deposit 4.186.926 hanya di dua OU, sesuai rencana: Metropolitan Mall Bekasi 4.186.925
(kena cap piutang terbuka) dan Grand Indonesia 1 (piutang tokonya nol — FICO juga mencatat −1).

TB per 30-Jun seimbang di kedua DB, selisih 0,00. Export:
`/srv/sftp-share/files/TB_Juni2026_prd_levis_begbal.xlsx`.

## Yang perlu diperhatikan

**TB Juni tetap 0-diff terhadap workbook TB EBR** yang di-upload klien, justru karena
adjustment-nya duduk di Juli (lihat memory `levis-tb-selisih-jul13-stale-export`). Yang
bergeser adalah posisi Juli: AR −668.050.980, deposit +667.523.715, MDR +527.265 per 01-Jul.

`fiscalyear_lock_date` 2026-06-30 di `prd_levis_begbal` dibuka sementara oleh kedua script
lalu dipulihkan (sudah diverifikasi pasca-eksekusi). Script 78 memerlukannya untuk menghapus
entry Juni; script 69 sebetulnya tidak lagi memerlukannya sejak tanggal buku pindah ke Juli.
`prd_levis` memang tidak punya lock date.

## Entry SALESMANUAL masih tertunda

Penjualan manual Juni yang tidak pernah masuk Odoo, **Rp 14.608.080**:

| Operating Unit | Jumlah |
|---|---|
| OLS SES - METROPOLITAN MALL BEKASI | 9.052.000 |
| OLS SES - PARIS VAN JAVA | 3.756.280 |
| OLS SES - CENTRAL PARK | 1.799.800 |

Tidak dibukukan pada eksekusi 4-Aug karena approval hanya mencakup clearing, dan dua hal
berikut **belum dijawab Accounting**:

1. **Akun pendapatan lawan mana?** Kandidat `5501000000` Sales Adjustment-manual posting
   (paling pas secara nama) atau `5199000000` Gross Sales-Others.
2. **Bagaimana perlakuan PPN-nya?** Script 69 membukukan Dr 1106000001 / Cr `<akun>`
   **flat, tanpa memisah PPN**. Kalau angka dari Finance itu gross incl PPN, PPN Keluaran
   tidak akan terbentuk dan berpotensi kurang lapor di SPT. Kalau memang harus dipisah,
   script perlu diubah — bukan sekadar mengisi `SALES_MANUAL_ACCOUNT`.

### Jangan jalankan ulang script 69

Ref-guard `EBR-ADJ-AR-JUNI-2026%` sudah `SystemExit` karena ketiga jurnal lain sudah ada,
jadi mengisi `SALES_MANUAL_ACCOUNT` lalu menjalankan ulang **tidak akan bekerja**. Entry ini
harus dibuat manual di UI atau lewat script baru yang terpisah.

### Efek kalau nanti dibukukan

Piutang MM Bekasi bertambah sehingga cap-nya longgar: clearing bisa ditambah 4.186.925
(total menjadi 671.710.640) dan sisa deposit 2103100003 tinggal Rp 1 milik Grand Indonesia.

Entry ini **juga harus bertanggal Juli, bukan Juni**, dengan alasan yang sama seperti di
atas — Juni sudah dilaporkan dan tidak boleh bergerak lagi.

Lihat juga `docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md` dan memory
`levis-june-ar-fico-final-rekon`.
