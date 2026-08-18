# Status "[ARKA AIM] List Issue After Go Live" — review 2026-08-18

Sumber: sheet klien `[ARKA AIM] List Issue After Go Live`
(`docs.google.com/spreadsheets/d/1jxzoD2muFUaxaWx0fJJqyx5TLvtwkzAYy1xLlHPOXjs`).
Dua worksheet: **List Issue** (25 item) dan **List Feedback User Odoo (EO)** (15 item).

Semua temuan di bawah diverifikasi langsung ke DB live **`prd_arkaaim`** pada
2026-08-18, dan terhadap kode yang benar-benar berjalan di `/opt` (bukan `/home`).
Company: `1` = PT Aero Inovasi Media (AIM), `2` = PT Aero Reksa Kreasi Angkasa (ARKA).

Review sebelumnya atas sheet ini: [`arkaaim-golive-issue-sheet`](#) (memori, 2026-07-24).
Worksheet EO juga dibahas lebih dalam di
[`kendala-sheet-jul2026-status.md`](../../kendala-sheet-jul2026-status.md) — dokumen itu
tetap jadi acuan untuk backlog depresiasi Juni 2026 yang **sengaja ditahan**.

Isi update siap-tempel ada di [`issue-sheet-aug2026/`](issue-sheet-aug2026/):

| File | Tujuan |
| --- | --- |
| `list_issue_I3_J27.tsv` | tab **List Issue**, kolom I (Status) + J (Remarks), paste di sel **I3** |
| `eo_feedback_C3_C17.tsv` | tab **List Feedback User Odoo (EO)**, kolom C (Solution), paste di sel **C3** |

Baris yang sudah `Closed`/`Cancelled` dipertahankan apa adanya. Satu pengecualian:
remark item 1 aslinya 3 baris, dirapatkan jadi 1 baris supaya paste TSV tidak
merusak struktur — lewati sel `J3` kalau format aslinya mau dipertahankan.

---

## 1. GAP yang terkonfirmasi dengan bukti

### 1.1 Item 25 / EO #4 — payment ARKA masih lewat COA perantara

Pembayaran di company 2 masih membentur akun perantara, bukan langsung ke bank:

```
PBNK2/2026/00004 | 1103000004 Outstanding Payments   | cr 39.338.686
                 | 2103300001 Non trade payable      | dr 39.338.686
```

Di AIM sudah benar — `account_payment_method_line.payment_account_id` untuk journal
`BCA1`/`BCA2` sudah diarahkan ke akun bank itu sendiri (`1103019270`/`1103019280`),
sehingga jurnalnya langsung Dr/Cr bank:

```
PBCA2/2026/00001 | 1103019280 BCA - IDR-268.150.7878 | cr 11.875
```

Perbaikan: isi `payment_account_id` pada seluruh method line journal `BNK1`/`BNK2`
company 2 dengan akun bank masing-masing. `payment_account_id` yang NULL jatuh ke
default outstanding company — itulah sumber COA perantara.

### 1.2 Item 8 / EO #9 — depresiasi Jul-2026 dst belum menghasilkan jurnal

`custom_fixed_asset_depreciation_line` untuk 2026:

| Bulan | Baris | Punya `move_id` | Ditandai posted |
| --- | --- | --- | --- |
| Jan–Jun 2026 | 3.180/bln | 0 | 3.180 |
| Jul–Des 2026 | 3.180/bln | 0 | 0 |

Jan–Jun ditandai posted tanpa GL — itu **memang desain opening balance**. Yang jadi
gap: Juli 2026 dan seterusnya (periode setelah go-live) belum diposting sama sekali,
`account_move` untuk depresiasi berjumlah **nol**. Selaras dengan status "cron
depresiasi masih non-aktif" di `kendala-sheet-jul2026-status.md`.

Jumlah asetnya sendiri sudah cocok dengan report accounting per 31 Mei 2026:

| Company | State | Qty | Nilai perolehan |
| --- | --- | --- | --- |
| 1 (AIM) | running | **3.180** | 27.110.131.389 |
| 1 (AIM) | draft | 144 | 42.101.540 |
| 2 (ARKA) | draft | 266 | 98.637.293 |

410 aset draft itulah kandidat "cancel yang bukan asset" / register-only.

### 1.3 Item 20 / EO #1 — begbal AR/AP tanpa detail partner

Baris opening s/d 30-Jun-2026:

| Tipe akun | Baris | Ber-partner |
| --- | --- | --- |
| `asset_receivable` | 8 | 3 |
| `liability_payable` | 18 | 6 |

Saldo naik agregat, jadi Kartu Piutang/Utang dan aging tidak bisa dipecah per
pelanggan/vendor. Butuh detail begbal per partner dari Accounting.

### 1.4 Item 23 — user Fiqo belum ada

`syafiqo.zhafran@erajaya.com` tidak ada di `res_users`. Sebagai pembanding,
`feri.01@`, `mei.mey@`, `sumida.01@`, `nuri.pancawati@`, `kurnia.adhi@` semuanya ada
dan aktif — jadi item 7 sudah bisa ditutup. Ingat login Odoo 19 **case-sensitive**.

### 1.5 Item 4 & 21 — nomor rekening di invoice

`res_partner_bank` masih **0 record** untuk kedua company. ARKA tetap tercetak karena
memakai free-text `res_company.report_bank_details`:

```
Pembayaran dilakukan dengan cara transfer ke rekening sebagai berikut :
Nama Rekening Bank : PT AERO REKSA KREASI ANGKASA
Bank : PT. BANK CENTRAL ASIA Tbk.
Nomor Rekening : 2682626268
```

AIM masih kosong. Klausul tambahan item 21 ("Pembayaran yang sah…", "FULL AMOUNT…")
belum ada — cukup ditambahkan di field yang sama, tapi untuk AIM belum bisa karena
noreknya belum diberikan.

### 1.6 Item 22 — blok di bawah Balance Due

Yang tercetak setelah `BALANCE DUE` adalah `signature_block` di
`custom_report_templates/reports/report_common_templates.xml`: tanda tangan +
"If you have any questions about this invoice, please contact …". Perlu konfirmasi
klien bagian mana yang dihapus. `custom_report_templates` adalah **shared addon** —
perubahan harus di-flag per company, jangan hardcode.

### 1.7 EO #10 — Sales Report kosong di AIM

Bukan bug report. `custom.report.sales` memfilter
`move_id.move_type in ('out_invoice','out_refund')`
(`custom_accounting_reports/models/custom_report_sales.py:166`), sementara AIM
**tidak punya satu pun customer invoice**:

| Company | out_invoice | in_invoice | entry (posted) |
| --- | --- | --- | --- |
| 1 (AIM) | **0** | 5 | 37 |
| 2 (ARKA) | 4 | 9 | 20 |

Seluruh pendapatan AIM lewat jurnal `MISC` — dan bukan cuma begbal: Juni (14.356.875)
dan Juli 2026 (17.359.849) pun masih jurnal manual. Konsekuensinya lebih luas dari
Sales Report: AR aging, kartu piutang, dan e-Faktur AIM juga akan tetap kosong.
Butuh keputusan Accounting: apakah AIM akan menerbitkan invoice di Odoo, atau
posisinya hanya company pembukuan.

### 1.8 EO #12 — due date tidak mengikuti ketentuan Erajaya

- **0 dari 11 customer** dan **0 dari 11 vendor** punya default payment term.
- **16 dari 18 invoice** tercatat tanpa payment term — due date diketik manual.
- Akibatnya: bill 7-Apr-2026 → due 20-Agu-2026, dan 4-Mei-2026 → due 23-Agu-2026.
  Ini merusak AR/AP aging.

Master term ada 12, isinya set bawaan Odoo plus satu buatan lokal
`DP 30% / Pelunasan 70% (Net 14)`. Tidak ada yang dinamai sebagai standar Erajaya.
Term `10 Days after End of Next Month` sudah tersedia kalau ketentuannya memang itu.

Blocker: **ketentuan due date Erajaya Group belum diketahui isinya**. Begitu
dikonfirmasi, eksekusinya kecil — rapikan master term, set default per partner.
Invoice yang sudah salah due date-nya tidak ikut terkoreksi dan harus diperbaiki
lewat jalur yang benar (sudah posted).

### 1.9 Item 2 — template Excel "Invoice PPN"

`custom_coretax_export` 19.0.1.3.0 terpasang dan report Faktur Pajak sudah ada,
tapi template tarikan Excel ala Otomotif belum dibuat.

---

## 2. Sudah live — tinggal dikonfirmasi user

| Item | Bukti |
| --- | --- |
| 5 & 6 | `custom_arka_show_date` 19.0.1.5.0 aktif; `report_show_product_name = TRUE` di **kedua** company |
| 7 | 3 user aktif, sudah lowercase |
| 12 | Wizard Lock Date terpasang (`custom_accounting_full` 19.0.0.6.0); Kurnia = Administrator + Show Full Accounting Features. Semua lock date masih NULL — **sengaja**, menunggu keputusan periode |
| 16 | Menu **AR Aging Export** ada (15 bucket overdue) |
| 17 | `custom_accounting_reports.drilldown_enabled = 1` |
| 18 | `custom_payment_voucher` 19.0.1.0.0 terpasang |
| 19 | `custom_petty_cash` 19.0.0.5.0 terpasang **dan** terkonfigurasi: CA `1109000002`, PC `1115200001`, journal `PCPAY` + `CSH` kedua company |
| 24 (sebagian) | Payment method **Giro** ada (inbound + outbound); vendor **KAS NEGARA** ada (`supplier_rank` 11) |
| EO #5 | `"purchase": "custom.report.purchase"` sudah terdaftar di `REPORT_MODEL_MAP` pada `/opt` — purchase report tidak lagi jatuh ke Trial Balance |
| EO #11 | 107 kategori PPh + 214 rule ter-seed. `account_move_withholding_line` masih **0** — fiturnya ada, belum pernah dipakai |

Sisa item 19 murni keputusan klien: plafon masih `warn` (belum `block`), akun kas
`1102000003` belum dikonfirmasi Accounting, dan belum ada user ber-grup
*Petty Cash / Finance* selain admin.

Sisa item 24 yang belum ada buktinya: trade/non-trade, kode billing di receipt bank
untuk Giro, dan penamaan journal.

---

## 3. Catatan operasional

**Drift `/home` vs `/opt`.** `custom_accounting_reports` di `/opt` (yang benar-benar
jalan) ada di **19.0.0.19.0**, di `/home` masih **19.0.0.18.0**. Jangan deploy dari
`/home` sebelum di-rebase — perbaikan purchase report (EO #5) akan ikut mundur.

**Item 1 (begbal master product)** bukan blocker IT; menunggu konfirmasi nominal dari
pak Brando & pak Darwin.
