# AR Clearing Juni 2026 — catatan eksekusi

Catatan eksekusi `scripts/tenants/levis/69_ar_adjustments_juni.py` (script dibuat di
commit `f588f3d` bersama 67/68).

- **Dieksekusi:** 4-Aug-2026, `ADJ_POST=1`, di **kedua** DB `prd_levis_begbal` dan `prd_levis`
- **Approval:** disetujui untuk clearing saja — entry SALESMANUAL sengaja tidak dijalankan
- **Sumber angka:** workbook FICO *EBR - Check Selisih Outstanding AR Finance vs Accounting
  Juni 2026.xlsx*, direproduksi oleh `67_rekon_ar_juni_final.py`

## Perintah yang dijalankan

Backup dulu — tidak ada backup otomatis untuk DB tenant:

```
docker exec -e PGPASSWORD="$PW" odoo19-platform-postgres pg_dump -U odoo -Fc -d <db> \
  > /opt/odoo-platform/backups/<db>_20260804_pre_ar_clearing.dump
```

Lalu, dari `/opt/odoo-platform` (bukan checkout `/home` — lihat memory
`odoo-platform-checkouts`; kedua salinan script sudah identik saat itu):

```
docker exec -i -e ADJ_POST=1 odoo19-platform-odoo odoo shell -d <db> --no-http \
  < scripts/tenants/levis/69_ar_adjustments_juni.py
```

## Hasil

Tiga jurnal GLJV tanggal 30-Jun-2026, status `posted`, seluruh baris ber-Operating Unit:

| Ref | Isi | Baris | Debit |
|---|---|---|---|
| `EBR-ADJ-AR-JUNI-2026-REALOKASI` | deposit antar-OU, saldo akun tidak berubah | 10 | 9.612.964 |
| `EBR-ADJ-AR-JUNI-2026-MDR` | Dr 7104000001 / Cr 1106000001 | 30 | 527.265 |
| `EBR-ADJ-AR-JUNI-2026-CLEARING` | Dr 2103100003 / Cr 1106000001 per OU | 36 | 667.523.715 |

Nomor: `prd_levis_begbal` GLJV/2026/06/0032–0034, `prd_levis` GLJV/2026/06/0031–0033.

Saldo per 30-Jun sesudahnya — **identik di kedua DB**:

| Akun | Sebelum | Sesudah |
|---|---|---|
| 1106000001 Trade Receivables | 1.025.747.288 | **357.696.308** |
| 2103100003 Deposit from customer trade | −671.710.641 | **−4.186.926** |
| 7104000001 MDR Bank | 25.971.461,73 | **26.498.726,73** |

Sisa AR 357.696.308 cocok dengan dekomposisi FICO: REKON JUL 148.813.668 + kas belum setor
7.940.708 + lag settlement akhir Juni 197.282.271 + TBFU belum ter-clear 4.186.926
− MDR 527.265.

Sisa deposit 4.186.926 hanya di dua OU, sesuai rencana: Metropolitan Mall Bekasi 4.186.925
(kena cap piutang terbuka) dan Grand Indonesia 1 (piutang tokonya nol — FICO juga mencatat −1).

TB per 30-Jun seimbang di kedua DB: begbal 80.304.377.756,66 dan prd_levis
78.239.608.771,76, selisih 0,00. Export:
`/srv/sftp-share/files/TB_Juni2026_prd_levis_begbal.xlsx`.

## Yang perlu diperhatikan

**TB Juni Odoo sekarang sengaja berbeda dari workbook TB EBR** yang di-upload klien —
sebelumnya 0-diff (lihat memory `levis-tb-selisih-jul13-stale-export`). Deviasinya persis
tiga akun di atas: AR −668.050.980, deposit +667.523.715, MDR +527.265. Itu hasil yang
diharapkan, bukan gejala masalah.

`fiscalyear_lock_date` 2026-06-30 di `prd_levis_begbal` dibuka sementara oleh script lalu
dipulihkan (sudah diverifikasi pasca-eksekusi). `prd_levis` memang tidak punya lock date.

## Entry SALESMANUAL masih tertunda

Rp 14.608.080 — MM Bekasi 9.052.000 / Paris van Java 3.756.280 / Central Park 1.799.800.
Belum dibukukan karena **akun pendapatan lawan + perlakuan PPN belum ditandatangani
Accounting**. Kandidat: `5501000000` Sales Adjustment-manual posting atau `5199000000`
Gross Sales-Others. Script tidak memisah PPN, jadi kalau angka Finance itu gross incl PPN,
PPN Keluaran tidak akan terbentuk.

**Jangan jalankan ulang script 69 untuk ini** — ref-guard `EBR-ADJ-AR-JUNI-2026%` akan
menolak (`SystemExit`) karena ketiga jurnal sudah ada. Entry ini harus dibuat manual atau
lewat script terpisah. Kalau dibukukan, clearing MM Bekasi bisa ditambah 4.186.925 sehingga
total clearing menjadi 671.710.640.

Lihat juga `docs/projects/levis/CONFIG_FOLLOWUPS_STATUS.md` dan memory
`levis-june-ar-fico-final-rekon`.
