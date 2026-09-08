# Levi's Odoo — Panduan Clearing GL Open Item

Menjawab sheet after-go-live **#22** ("belum ada fitur GL Open Item") dan **#23**
("guide cara clearing GL Open Item"). Fiturnya sudah ada sejak
`custom_accounting_reports` + `custom_account_reconcile` terpasang; dokumen ini
adalah rujukan internal, versi klien dibagikan terpisah sebagai Google Docs.

---

## 1. Apa itu GL Open Item

Setiap akun ber-`reconcile = True` (piutang, hutang, GR/IR, uang muka, kliring,
intercompany) menyimpan baris jurnal yang saling menunggu pasangan. Baris yang
belum ter-*match* adalah **open item**.

Saldo akun bisa nol sementara isinya penuh baris yang tak pernah dipasangkan —
aged report lalu menampilkan dokumen yang sebenarnya lunas, dan selisih kecil
(pembulatan, biaya bank) menumpuk tanpa ketahuan.

---

## 2. Melihat: report GL Open Items

**Invoicing → Reporting → Reports → GL Open Items / Outstanding**
(`custom.report.gl.open.items`, kode report `gl_open_items`)

Kolom: Akun, Tanggal, No. Dokumen, Referensi, Lawan Transaksi, Jatuh Tempo, Umur
(hari), Debit, Kredit, Outstanding. Tersedia ekspor XLSX.

**Beda dengan Aged Receivable/Payable — dan ini disengaja.** Aged membaca
`amount_residual` **saat ini**, sehingga baris yang dilunasi setelah cut-off
sudah tampak berkurang. Report ini membangun ulang sisa dari rekonsiliasi yang
benar-benar sudah terjadi per `date_to` (`account.partial.reconcile.max_date`),
sehingga angkanya tie dengan ledger per akhir periode.

**Pelunasan oleh jurnal draft tidak dihitung.** Bila kedua kaki penyelesaian
tidak berada dalam scope terlapor, baris tetap dianggap terbuka — di
`prd_levis_begbal` ada partial reconcile Rp 75.405.550 terhadap move yang masih
draft. Mengurangkannya akan membuat report berhenti tie dengan GL.

---

## 3. Melakukan clearing

### 3.1 Overview per akun

**Invoicing → Accounting → Reconciliation → Reconcile**
(`custom.reconcile.account`, SQL view read-only: satu baris per akun yang punya
posted + unreconciled line)

Kolom: jumlah baris, debit, kredit, residual, tanggal item tertua. Tombol pada
baris membuka seluruh journal item terbuka di akun tersebut.

### 3.2 Mempertemukan baris

1. Centang baris yang berpasangan.
2. Klik **Reconcile** (aksi kontekstual pada list `account.move.line`, membuka
   `custom.account.reconcile.wizard`).
3. Wizard menampilkan Debit, Credit, Residual, dan flag `is_balanced`.

| Kondisi | Tindakan |
|---|---|
| Residual = 0 | Mode **Partial**, klik Reconcile — semua baris tertutup penuh. |
| Sisa memang disengaja (cicilan) | Mode **Partial**. Baris besar tetap terbuka sebesar sisanya. |
| Selisih harus dihapusbukukan | Mode **Write-off**: isi `writeoff_account_id`, `writeoff_journal_id`, `writeoff_date`, dan `writeoff_label`. Sistem memposting jurnal penyeimbang lalu menutup seluruh baris. |

Isi **Label** dengan keterangan bermakna — default `"Write-Off"` tidak
menjelaskan apa pun di GL.

### 3.3 Rekening koran

**Invoicing → Accounting → Reconciliation → Bank Reconciliation** — buka baris,
centang kandidat (skoring berdasarkan jumlah/partner/referensi), Reconcile.
Tersedia **Auto-match** (`action_st_lines_auto_match`) untuk batch. Sisa bisa
di-write-off dari wizard yang sama.

Menutup periode **mensyaratkan** seluruh statement line periode itu sudah
direkonsiliasi — lihat `OPEN_CLOSE_PERIOD_GUIDE.md`.

### 3.4 Payment yang belum menempel

**Invoicing → Accounting → Reconciliation → Unapplied Payments** — payment
ter-posting (`in_process`/`paid`) yang tidak menutup dokumen apa pun
(`is_unapplied`). Ini sumber open item yang paling sering terlewat: uang sudah
keluar, bill masih tampak belum lunas.

---

## 4. Alur kerja bulanan

1. Jalankan **GL Open Items / Outstanding** dengan cut-off akhir bulan.
2. Urutkan per **Umur (hari)**, tinjau > 60 hari lebih dulu.
3. Bereskan **Unapplied Payments** — biasanya menghapus banyak baris sekaligus.
4. Rekonsiliasi rekening koran sampai bersih.
5. Bereskan akun kliring: GR/IR, uang muka, intercompany.
6. Sisa kecil di-write-off dengan label jelas.
7. Jalankan ulang report, cocokkan dengan Trial Balance, baru kunci periode.

---

## 5. Jebakan

- **Write-off tunduk pada lock date.** `writeoff_date` di periode terkunci akan
  ditolak. Pakai tanggal periode terbuka; jangan memaksa periode terlapor.
- **Reset to draft melepas rekonsiliasi.** `account.move.button_draft()`
  memanggil `remove_move_reconcile()` **sebelum** `super()`, jadi dokumen lawan
  kembali terbuka. Setelah di-posting ulang, rekonsiliasi **harus dipasang
  kembali manual** — tidak otomatis.
- **Baris ter-match tidak bisa diubah struktur.** `account.move.line.write()`
  menolak perubahan `account_id` / `partner_id` selama baris masih membawa
  partial, dalam state apa pun. Lepas rekonsiliasinya dulu bila memang perlu.
- **Jangan tutup selisih material dengan write-off.** Selisih besar berarti ada
  dokumen belum/salah dibukukan — telusuri dulu.
- **Satu payment untuk banyak bill:** pilih semua baris sekaligus dalam satu kali
  Reconcile, jangan satu per satu, agar tidak menyisakan pecahan partial.

---

## 6. Model & menu terkait (rujukan teknis)

| Fungsi | Model / action | Menu |
|---|---|---|
| Report open item as-of | `custom.report.gl.open.items` | Reporting → Reports → GL Open Items / Outstanding |
| Overview per akun | `custom.reconcile.account` (SQL view) | Accounting → Reconciliation → Reconcile |
| Reconcile manual | `custom.account.reconcile.wizard` | aksi kontekstual pada list Journal Items |
| Match rekening koran | `custom.bank.reconcile.wizard` | Accounting → Reconciliation → Bank Reconciliation |
| Payment menggantung | `account.payment.is_unapplied` | Accounting → Reconciliation → Unapplied Payments |

Rekonsiliasinya sendiri tetap memakai core CE (`account.move.line.reconcile()`,
`account.bank.statement.line._reconcile_with_amls()`); modul kita menyediakan UI
dan skoring kandidat, bukan engine baru.
