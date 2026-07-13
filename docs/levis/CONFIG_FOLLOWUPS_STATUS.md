# Levi's Odoo — Status Konfigurasi Tindak Lanjut

Diverifikasi ulang terhadap DB yang berjalan pada **13 Juli 2026**, bukan disalin
dari catatan lama. Beberapa item di `CONFIG_FOLLOWUPS.md` ternyata **sudah usang**.

DB yang diperiksa & diperbaiki: `rnd_levis`, `prd_levis`, `prd_detail_levis`,
`prd_levis_begbal`, `demo_updated_levis`.

Skrip: [`scripts/tenants/levis/72_fix_config_followups.py`](../../scripts/tenants/levis/72_fix_config_followups.py)
(DRY by default, idempoten) dan
[`73_load_mdr_bin.py`](../../scripts/tenants/levis/73_load_mdr_bin.py).

---

## Ringkasan

| # | Item | Status |
|---|------|--------|
| 1 | GR/IR clearing stream **Trade** | ✅ **Sudah benar — catatan lama keliru** |
| 2 | Akun *scrap loss* | ✅ **Selesai & terverifikasi** |
| 3 | Tabel Card BIN / MDR | ⏳ **Menunggu data Finance** |
| 4 | Akum. depresiasi **Vehicles** | ✅ **Selesai & terverifikasi** (sebabnya bukan yang dicatat) |
| 4b | **Jurnal depresiasi** semua grup aset | ✅ **Selesai** — *gap baru, tidak ada di daftar lama* |
| 5 | Pemetaan COA biaya audit | ❓ Perlu arahan Finance |
| 6 | Saklar go-live impor | ⛔ **Sengaja tidak disentuh** |

---

## 1. GR/IR Trade — catatan lama KELIRU

`CONFIG_FOLLOWUPS.md` menyatakan akun GR/IR trade "belum di-set". **Tidak benar.**
Semua kategori dagangan sudah teresolusi ke akun GR/IR yang tepat:

| Kategori | Akun valuasi | GR/IR clearing | Tipe |
|---|---|---|---|
| Textile | `1113100021` | `2103109121` | `liability_current` ✅ |
| Footwear | `1113100022` | `2103109122` | `liability_current` ✅ |
| Accessories | `1113100023` | `2103109123` | `liability_current` ✅ |
| Miscellaneous | `1113100024` | `2103109124` | `liability_current` ✅ |

Baris **Trade** pada `levis.purchase.account.map` memang `grir_account_id = NULL` —
dan itu **memang seharusnya begitu**. GR/IR trade diambil per-kategori; mengisi
baris map justru akan menimpa (override) pemetaan per-kategori tersebut.

> **Catatan Odoo 19:** `product.category.account_stock_variation_id` **bukan field
> tersimpan** — ia diturunkan dari `account.account.account_stock_variation_id` milik
> akun valuasi kategori. Jadi GR/IR trade dikonfigurasi di **akun valuasi**, bukan di
> kategori. Ini kenapa pemeriksaan lewat kategori tampak "kosong".

**Tidak ada tindakan.**

---

## 2. Akun scrap loss — SELESAI

Parameter `custom_levis_localization.scrap_loss_account_code` kosong, sehingga
validasi Scrap Batch gagal.

**Diisi:** `7218000001` — *Inventory write-off* (`expense`).

**Terverifikasi end-to-end** (Scrap Batch dibuat, divalidasi, lalu di-rollback):

```
SCRAP  state=done
       7218000001  Inventory write-off    Dr 584.807
       1113100021  Inventories-textile               Cr 584.807
```

---

## 3. Card BIN / MDR — MENUNGGU DATA

`levis.mdr.bin` masih 0 baris di semua DB. Tidak bisa diisi tanpa data asli.

**Yang dibutuhkan dari Finance**, per baris: skema kartu, rentang BIN, bank
acquirer (Kode BI), tarif MDR (% dan/atau nominal tetap), akun beban MDR, masa berlaku.

Loader sudah siap: isi [`scripts/tenants/levis/mdr_bin.csv`](../../scripts/tenants/levis/mdr_bin.csv)
lalu jalankan `73_load_mdr_bin.py`. Skrip memvalidasi dulu sebelum menulis —
termasuk **rentang BIN yang tumpang tindih**, yang tidak dijaga database
(`levis.mdr.bin` memakai `_sql_constraints` gaya lama yang **diabaikan diam-diam**
oleh Odoo 19, jadi constraint-nya tidak pernah terbentuk).

---

## 4. Vehicles — SELESAI, tapi sebabnya bukan yang dicatat

Catatan lama: *"kode `1205202000` tidak ada di Chart of Accounts"*. **Keliru** —
akun itu **ada** (`Fixed assets - Accumulated depreciation - Vehicles`, `asset_fixed`).
Yang kosong hanyalah **pemetaannya** pada grup aset.

**Diisi:** grup `Vehicles` → `default_depreciation_account_id` = `1205202000`.

## 4b. Jurnal depresiasi — GAP BARU

Ditemukan saat memverifikasi item 4. **Tidak satu pun dari 6 grup aset** memiliki
`default_journal_id` di keempat DB nyata. Akibatnya `action_confirm()` pada aset
**gagal untuk SEMUA kategori** — bukan hanya Vehicles — dengan pesan
*"depreciation journal must be set"*.

**Diisi:** semua grup ber-depresiasi → jurnal `DEPRE`. Jurnal `DEPRE` sendiri tidak
ada di `prd_levis` dan `prd_detail_levis`, jadi skrip membuatnya.
**Land dilewati** — tanah tidak disusutkan, jadi tidak butuh jurnal.

**Terverifikasi end-to-end** di 4 DB (aset Vehicles Rp 120jt / 96 bulan, lalu rollback):

```
ASSET  state=running  lines=96
       7204102000  Depreciation - Fixed Asset - Vehicles   Dr 1.250.000
       1205202000  Fixed assets - Accum. depreciation                  Cr 1.250.000
```

---

## 5. COA biaya audit — perlu arahan

Terlalu kabur untuk ditindak. Perlu Finance menyebutkan: biaya audit dibebankan ke
akun mana, dan lewat produk/kategori apa ia masuk ke Vendor Bill.

---

## 6. Saklar go-live — SENGAJA TIDAK DISENTUH

Diputuskan untuk **tidak** diaktifkan sekarang:

| Saklar | Status | Alasan |
|---|---|---|
| Cron *Retail Import: poll SFTP feeds* | nonaktif | Mengaktifkannya mulai memposting jurnal ke GL. Keputusan go-live. |
| `retail_import.x48_post_enabled` | `0` | **Ada bug yang belum diperbaiki:** refund X48 di-tender ke metode CASH toko dan nilainya mendarat di akun *Cash Difference*, bukan mengurangi kas. Harus dibereskan dulu. |
| `retail_import.x31_post_enabled` | `0` | Benar — saling eksklusif dengan `x24_discount_reclass=1` yang aktif. Mengaktifkan keduanya menggelembungkan Gross Sales dua kali. |
| Cron *Custom Asset: Post Monthly Depreciation* | nonaktif | Sekali diaktifkan, ia langsung memposting **seluruh** baris depresiasi yang sudah jatuh tempo. Sebaiknya Finance posting manual dulu lewat **Post Depreciation** untuk melihat dampaknya. |

> Dokumen FD/Manual versi awal menyebut cron depresiasi **aktif** — itu **salah**;
> sudah dikoreksi.
