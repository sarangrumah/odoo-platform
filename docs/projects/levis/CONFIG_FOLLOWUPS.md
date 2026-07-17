# Levi's Odoo — Konfigurasi Tindak Lanjut (Config Follow-ups)

Dokumen ini mendaftar konfigurasi **non-kode** yang perlu diisi tim setelah
remediasi user-testing (cluster A–E) ter-deploy. Semua fitur sudah aktif di
`rnd_levis`, `prd_levis`, `prd_detail_levis` (`custom_levis_localization` 1.12.0);
yang tersisa hanya **pengisian data master**, bukan pengembangan.

Kerjakan di **`rnd_levis`** dulu untuk uji, lalu ulangi di `prd_levis` dan
`prd_detail_levis`. Prioritas menyusul.

> Konvensi: "menu" = jalur UI Odoo. Sebagian item butuh mode Developer aktif
> (Settings → Activate the developer mode). Kode akun bersifat *company-dependent*
> di Odoo 19 — pastikan company aktif = company Levi's saat mencari akun.

---

## 1. GR/IR clearing untuk stream **Trade**  — PRIORITAS TINGGI

**Kenapa:** Perbaikan GR/IR (Cluster A) me-route product line vendor bill ke akun
GR/IR clearing supaya net ke nol (Dr GR/IR / Cr AP). Untuk **non-trade** akun GR/IR
sudah ter-set (`1103300008` via mapping). Untuk **trade**, akun GR/IR diambil dari
**product category** (`account_stock_variation_id`) — dan saat ini **belum di-set**,
sehingga clearing trade belum aktif (bill trade masih ke COGS/expense).

**Yang harus dilakukan** (pilih salah satu):

- **Opsi A (disarankan) — per kategori produk:** set *Stock Variation / GR-IR account*
  pada tiap product category real-time yang dipakai barang dagangan.
  Menu: **Inventory → Configuration → Product Categories** → buka kategori →
  field akun variation/GR-IR.
- **Opsi B — global trade:** isi `grir_account_id` pada baris **Trade** di
  **Accounting → Configuration → Trade/Non-Trade Accounts** (model
  `levis.purchase.account.map`). Jika diisi, ini menang atas kategori.

**Verifikasi:** buat PO trade → validasi GR → posting bill; saldo akun GR/IR net ke 0.

---

## 2. Journal Scrap — akun *scrap loss*  — PRIORITAS TINGGI

**Kenapa:** Fitur Journal Scrap (`custom.scrap.batch`) aktif, tapi parameter akun
kerugian scrap masih kosong → posting scrap gagal.

**Yang harus dilakukan:** set parameter `custom_levis_localization.scrap_loss_account_code`
ke **kode akun** expense kerugian scrap.
Menu: **Settings → Technical → System Parameters** → cari
`custom_levis_localization.scrap_loss_account_code` → isi kode akun (mis. akun
"Inventory write-off / Scrap loss").

Alternatif via shell:
```python
env['ir.config_parameter'].sudo().set_param(
    'custom_levis_localization.scrap_loss_account_code', '<KODE_AKUN>')
```

---

## 3. Konfigurasi MDR & BIN kartu  — PRIORITAS SEDANG

**Kenapa:** Model `levis.mdr.bin` aktif (netting MDR saat settlement kartu), tapi
**0 baris** di semua DB.

**Yang harus dilakukan:** isi tabel BIN → acquirer + MDR% + biaya tetap + akun expense.
Menu: **Accounting → Configuration → Card BIN / MDR**. Satu baris per rentang BIN.

---

## 4. Fixed Asset — akun akumulasi penyusutan **Vehicles**  — PRIORITAS SEDANG

**Kenapa:** Seed 6 kategori FA (EBR) sudah jalan, tapi group **Vehicles** tidak
punya akun *accumulated depreciation* karena chart belum punya kode `1205202000`.
Tanpa ini, posting penyusutan aset Vehicles gagal.

**Yang harus dilakukan:** buat/pilih akun akumulasi penyusutan Vehicles lalu isi
`default_depreciation_account_id` pada group Vehicles.
Menu: **Accounting → Fixed Assets → Configuration → Asset Groups** → "Vehicles" →
*Accumulated Depreciation Account*.

---

## 5. Mapping COA *audit fee* pada Bills  — PRIORITAS RENDAH

**Kenapa:** Nominal untaxed di Bills sudah benar, tapi line **audit fee** belum
ter-map ke COA (feedback Sheet1 #8b).

**Yang harus dilakukan:** map produk/line "audit fee" ke akun yang sesuai
(mis. "Accrued Expenses 3P-Audit fee" atau akun professional fee terkait), lewat
akun expense pada produk atau kategorinya.

---

## 6. Aktifkan cron polling Retail Import  — SAAT GO-LIVE

**Kenapa:** Ingestion file SFTP (`X20/X24/X70D` dst.) dijalankan oleh
`ir.cron` **`cron_poll_retail_feeds`** yang **default nonaktif** supaya tidak
menarik file sebelum siap.

**Yang harus dilakukan (saat go-live retail import):** aktifkan cron.
Menu: **Settings → Technical → Scheduled Actions** → cari "retail" /
`cron_poll_retail_feeds` → set **Active = ON**.
Pastikan flag posting Finance dinyalakan sesuai kebutuhan:
`retail_import.x24_post_enabled`, `retail_import.x31_post_enabled`,
`retail_import.x48_post_enabled` (default `0`/off).

---

## Ringkasan checklist

| # | Item | Prioritas | Lokasi |
|---|------|-----------|--------|
| 1 | GR/IR trade account | Tinggi | Product Categories / Trade-NonTrade Accounts |
| 2 | Scrap-loss account | Tinggi | System Parameter `…scrap_loss_account_code` |
| 3 | MDR & BIN | Sedang | Accounting → Config → Card BIN / MDR |
| 4 | Vehicles accum. depreciation | Sedang | Fixed Assets → Asset Groups → Vehicles |
| 5 | Audit-fee COA | Rendah | Product/kategori audit-fee |
| 6 | Aktifkan retail poll-cron | Saat go-live | Scheduled Actions `cron_poll_retail_feeds` |

> Item feedback lain yang **belum dikembangkan** (backdate permission, block
> duplikat reference, template TB EBR, multi-CoA per-partner + aging, DP journal,
> end-to-end report, HS-code import) berada di luar cluster A–E dan menunggu
> keputusan scope terpisah.
