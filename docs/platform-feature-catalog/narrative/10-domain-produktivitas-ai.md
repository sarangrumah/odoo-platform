---
title: Produktivitas & AI
domain: produktivitas-ai
---

# 10. Produktivitas & AI

{{n.domain.produktivitas-ai}} modul, seluruhnya berlaku umum. Domain ini
menggantikan sekelompok aplikasi Odoo Enterprise yang biasanya dibeli terpisah —
Documents, Knowledge, Spreadsheet, Sign, Studio — dan menambahkan lapisan AI di
atasnya.

## 10.1 Lapisan AI

`custom_ai_bridge` adalah satu-satunya jalan keluar menuju model bahasa. Ia
menandatangani permintaan dengan HMAC dan mengirimkannya ke sebuah gateway
terpisah, yang kemudian memilih penyedia: **Claude (Anthropic), OpenAI, atau
Ollama lokal**. Abstraksi ini penting secara komersial dan kepatuhan sekaligus:
mengganti penyedia adalah perubahan konfigurasi, dan sebuah tenant dengan
kebutuhan kedaulatan data dapat diarahkan ke model lokal tanpa mengubah satu pun
modul di atasnya.

`custom_ai_features` memakai jembatan itu untuk fitur yang terlihat pengguna:
**Ask AI** di mana saja, **inbox anomali** yang menyoroti transaksi menyimpang,
**chat bahasa alami ke data**, dan klasifikasi dokumen otomatis.

## 10.2 Dokumen dan pengetahuan

**Manajemen dokumen** (`custom_documents`) menyediakan workspace, penandaan,
versi, dan akses yang menghormati klasifikasi data pribadi dari domain
kepatuhan. **Basis pengetahuan** (`custom_knowledge`) adalah wiki internal ringan
dengan template dan versi artikel. **Tanda tangan elektronik**
(`custom_sign`) menangani alur multi-penandatangan lewat portal bertoken.

**Spreadsheet** (`custom_spreadsheet`) menambahkan lapisan workbook dengan impor
dan ekspor CSV, bantuan AI, versi, dan berbagi.

## 10.3 Kustomisasi tanpa kode

`custom_studio_lite` adalah pengganti ringan Odoo Studio: pengelola field kustom
dan ekstensi tampilan secara **deklaratif**. Perbedaannya dengan Studio asli
penting bagi tim yang memelihara platform ini — perubahan disimpan sebagai
record yang dapat ditinjau dan dipindahkan antar basis data, bukan sebagai
modifikasi tampilan yang menyebar dan sulit dilacak.

## 10.4 Dashboard dan kerapian data

**Dashboard KPI** (`custom_dashboards`) menyusun ubin metrik dengan kueri bahasa
alami. **Pembersihan data** (`custom_data_cleaning`) menjalankan aturan
deduplikasi dan normalisasi format Indonesia — nomor telepon dan NIK — yang
merupakan sumber duplikasi partner paling umum di basis data lokal.
**Daftar tugas pribadi** (`custom_todo`) melengkapi dengan timer pomodoro,
pemecahan tugas berbantuan AI, dan template berulang.

## 10.5 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
