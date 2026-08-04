# Begbal ARKA & AIM — detail (bukan agregat)

Status: **selesai diterapkan di `prd_arkaaim` 4-Aug-2026**, setelah diuji di
`trn_arkaaim_begbal`. Backup pra-eksekusi: `/home/odoo-erp/backups/arkaaim/prd_arkaaim-prebegbal-20260804-1740.dump`.

## Sumber data

| File | Drive id | Dipakai untuk |
|---|---|---|
| `imports/arka_aim/TB_Detail_AIM_ARKA_052026_040826.xlsx` | `1yAjLxAWqBNXRCQS3NvZ1s3nPy23PDhZI` | TB + GL detail per akun (sheet `TB/BS/PL` × AIM/ARKA) |
| `imports/arka_aim/Template_Begbal_AIM_ARKA_0408261700.xlsx` | `10Ew3-1A7pdL45WrhTGLnjmZj3UZGexfJ` | sheet `Aset Tetap` (kolom penyusutan hasil hitung) |

Sheet lain di workbook template (AR, AP, Persediaan, Bank & Kas, Uang Muka,
Perpajakan, Neraca Saldo Awal) masih berisi baris contoh bawaan template dan
**tidak dipakai** — konsisten dengan TB kedua company yang memang tidak punya
saldo AR/AP dagang maupun persediaan.

## Yang berubah

**Saldo tidak berubah.** TB per 31-Mei-2026 identik dengan yang sudah diposting
sebelumnya: AIM Rp 43.264.095.721,50 dan ARKA Rp 5.054.276.231. Yang berubah
adalah granularitasnya.

| | Sebelum | Sesudah |
|---|---|---|
| Jurnal AIM | move 15, 27 baris (1 per akun), journal MISC | move 120, **265 baris** per transaksi, journal MISC |
| Jurnal ARKA | move 16, 12 baris, journal **BILL1 (pembelian)** | move 121, **61 baris**, journal **JM (umum)** |
| Ref | `Saldo Awal 31 Mei 2026` | `Saldo Awal Detail 31 Mei 2026` |
| Register aset | 3.329 unit, tanggal seragam 30-Jan-2025, 1 group | **3.590 unit**, tanggal perolehan riil, 3 group |

Seluruh baris tetap bertanggal 31-Mei-2026. Tanggal transaksi asli, nomor
dokumen dan nama lawan transaksi disimpan di label baris (`account.move.line`
tidak punya field tanggal sendiri), mis.
`2026-01-19 | CA-IING RISYANTO | PAYMENT CA PEMBELIAN ALAT PENUNJANG DRONE | Iing Ristyanto`.

Perbedaan saldo satu-satunya versus jurnal lama adalah **desimal**: jurnal
agregat membulatkan ke rupiah, detail ini membawa angka TB apa adanya
(mis. 1103019270 dari 2.470.000 → 2.470.000,12).

## Kode akun ARKA yang dipetakan

Sheet detail ARKA memakai kode yang tidak ada di CoA. Nominalnya cocok persis,
jadi dipetakan ke kode TB yang dipakai sistem:

| Kode di sheet detail | Dipetakan ke | Akun |
|---|---|---|
| 1103019870 | 1103019290 | BCA - IDR-268.262.6268 |
| 1103019900 | 1103019300 | BCA - IDR-268.222.9595 |
| 1105020003 | 1105020007 | Time Deposit BRI |

**Perlu dikonfirmasi ke klien** kode mana yang benar untuk CoA final.

## Register aset tetap

| Populasi | Unit | Nilai perolehan | Penyusutan |
|---|---:|---:|---|
| AIM `Registered` — Device | 1.500 | 22.641.197.295 | 48 bln garis lurus |
| AIM `Registered` — Komponen Drone | 1.680 | 4.468.934.094 | 48 bln garis lurus |
| AIM `Unregistered` (spare, di-reclass ke Office Supplies 31-Mei-26) | 144 | 42.101.540 | tidak disusutkan, tanpa GL |
| ARKA `Unregistered` — Alat Pendukung | 266 | 98.637.293 | tidak disusutkan, tanpa GL |

- Registered = 3.180 unit, total **27.110.131.389,12** vs GL `1205104000`
  27.110.131.391 → selisih Rp 1,88 (pembulatan per unit; sheet sendiri
  menunjukkan selisih Rp 1).
- Akum. penyusutan s/d 31-Mei-2026 hasil register **6.776.493.733,92** vs GL
  `1205203000` 6.776.493.894,83 → selisih **Rp 160,91**. Penyebabnya jadwal
  penyusutan membulatkan angsuran bulanan ke 2 desimal per unit (≈ Rp 0,05/unit
  × 3.180 unit). Immaterial, tidak dikoreksi ke GL.
- Baris penyusutan s/d **30-Jun-2026** ditandai `posted=True` tanpa `move_id`:
  Juni sudah dijurnal manual (`Depre-0626`), jadi cron bulanan mulai dari
  **Juli-2026** dan tidak membukukan Juni dua kali.
- Penyusutan bulanan ke depan **564.794.390,59** vs `Depre-0626` 564.794.404 →
  beda Rp 13,41/bulan (register lama sebelumnya beda Rp 728.680).
- 410 unit `Unregistered` tidak punya kode aset di sheet (`-`); kode
  `AS-AIM-xxxx` / `AS-ARKA-xxxx` di-generate dan ditandai `code_generated=1`
  di CSV supaya mudah diganti bila klien menyusulkan kode resmi.

## Pertanyaan lama yang terjawab file ini

Merujuk daftar 34 pertanyaan (`Template_Begbal_Odoo AIM.xlsx`, 3-Aug-2026):

- **D.12** nilai perolehan FA = 27.110.131.391 = pembelian PT Sinar Eka Selaras
  13-Jun-25 Rp 27.145.108.699 + Damoda Drone DMD-M400W-V3 22-Okt-25
  Rp 120.753.052 + APAR 19-Jan-26 Rp 3.768.450 − reclass ke Office Supplies
  31-Mei-26 Rp 42.101.554.
- **C.6/C.7/C.8/C.10** penyusutan: 48 bulan garis lurus, mulai bulan perolehan
  (Jun-2025 untuk armada utama), sisa umur 36 bulan per cutover.
- **D.14** akum. penyusutan terurai per bulan Jun-25…Mei-26 + reclass Rp 9.648.273.
- **E.16–E.19** aset ARKA = `Unregistered`, tanpa penyusutan, tidak dijurnal.
- **G.26/G.27** selisih unit = 144 spare AIM `Unregistered`.
- **A.3/B.4** TB final tidak berubah; cutover tetap 31-Mei-2026.

**Masih terbuka:** sel "Tanggal Cutover" kosong di seluruh sheet (diasumsikan
31-Mei-2026); kode aset resmi untuk 410 unit (F.20); serial number, lokasi dan
custodian per unit (F.22–F.24); kode akun bank ARKA mana yang benar; approval
Finance dan pengaktifan lock date (H.32–H.33).

## Cara menjalankan ulang

```bash
# 1. Parse + rekonsiliasi (host; gagal = tidak menulis CSV)
python3 tools/parse_arkaaim_begbal_detail.py --write
python3 tools/parse_arkaaim_asset_sheet.py --write

# 2. Salin CSV ke /opt (dibaca container lewat /mnt/extra-addons)
cp addons/_tenants/custom_arka_aim_opening_balance/data/opening_detail_*.csv \
   /opt/odoo-platform/addons/_tenants/custom_arka_aim_opening_balance/data/
cp addons/_tenants/custom_arka_aim_asset_register/data/asset_register_*.csv \
   /opt/odoo-platform/addons/_tenants/custom_arka_aim_asset_register/data/

# 3. Dry run dulu (tanpa env var), lalu eksekusi
docker exec -i -e BEGBAL_REPLACE=1 odoo19-platform-odoo \
  sh -c 'odoo shell -d prd_arkaaim --no-http' < scripts/tenants/arkaaim/load_begbal_detail.py
docker exec -i -e ASSET_REBUILD=1 -e ASSET_POSTED_THROUGH=2026-06-30 odoo19-platform-odoo \
  sh -c 'odoo shell -d prd_arkaaim --no-http' < scripts/tenants/arkaaim/rebuild_asset_register.py
```

Keduanya idempoten: loader GL melewati company yang sudah punya ref detail;
rebuild register menghapus register lama lebih dulu (karena itu wajib backup).
Aturan pemuatan ada di `hooks.py` masing-masing modul, jadi install baru
(`-i custom_arka_aim_opening_balance` / `custom_arka_aim_asset_register`)
menghasilkan data yang sama.

## Verifikasi

```sql
-- TB per company harus 43.264.095.721,50 dan 5.054.276.231
with bal as (select l.company_id cid, l.account_id, round(sum(l.debit-l.credit),2) b
  from account_move_line l join account_move m on m.id=l.move_id
  where m.date<='2026-05-31' and m.state='posted' group by 1,2)
select cid, round(sum(case when b>0 then b else 0 end),2) tb_debit,
            round(sum(case when b<0 then -b else 0 end),2) tb_credit, count(*) akun
from bal group by cid order by cid;

-- Register: 3.180 unit disusutkan + 410 register-only
select a.company_id, g.code, a.depreciation_method, count(*), round(sum(a.acquisition_value),2)
from custom_fixed_asset a left join custom_fixed_asset_group g on g.id=a.group_id
group by 1,2,3 order by 1,2;

-- Bulan terbuka pertama harus Juli-2026
select date_trunc('month',date)::date, count(*), round(sum(amount),2)
from custom_fixed_asset_depreciation_line where not posted group by 1 order by 1 limit 1;
```
