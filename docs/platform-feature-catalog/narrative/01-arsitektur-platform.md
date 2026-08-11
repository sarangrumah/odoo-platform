---
title: Arsitektur Platform
---

# 1. Arsitektur Platform

## 1.1 Satu basis kode, banyak brand

Platform ini adalah **satu repositori Odoo 19 yang melayani seluruh brand
Erajaya Group sekaligus beberapa tenant di luar grup**. Setiap tenant mendapat
basis datanya sendiri di dalam satu klaster PostgreSQL; kode, modul, dan
pembaruan dibagi bersama.

Konsekuensinya berlaku dua arah, dan keduanya perlu dipahami sebelum membaca bab
mana pun setelah ini:

- Sebuah perbaikan yang dikerjakan untuk satu brand langsung tersedia untuk semua
  brand lain. Ini sumber penghematan terbesar platform.
- Sebuah perubahan pada modul bersama **menyentuh semua tenant**, termasuk yang
  tidak meminta perubahan itu. Karena itu ada aturan tegas tentang di mana sebuah
  modul boleh diletakkan.

{{TABEL_TENANT}}

## 1.2 Tingkatan modul

Tingkat sebuah modul ditentukan **semata-mata oleh direktori tempat ia berada** di
bawah `addons/`. Kategori di dalam manifest bukan penentu tingkat: modul `ee_gap`
sengaja memakai kategori bawaan Odoo agar muncul berdampingan dengan aplikasi
Enterprise yang digantikannya.

{{TABEL_GRUP}}

Tiga aturan mengatur penempatan:

- **Mesin integrasi bersama selalu masuk `ee_gap/` atau `core/`, tidak pernah
  `_tenants/`.** Data awalnya boleh milik satu pelanggan; mesinnya tidak. Contoh
  kanoniknya adalah `custom_retail_import`, yang generik, sementara profil
  `levis_*` di dalam datanya milik satu tenant.
- **Promosi.** Sebuah pola yang muncul untuk pelanggan kedua naik dari
  `_tenants/` ke `ee_gap/`.
- **Kedalaman direktori tetap** `addons/<grup>/<modul>/`. Satu pengecualian yang
  sudah ada — modul template di `verticals/_template/` — berada satu tingkat lebih
  dalam, dan itulah sebabnya perhitungan modul yang berbatas kedalaman
  menghasilkan satu modul lebih sedikit dari {{n.modules_total}}.

Grup `ee_gap` adalah yang terbesar dengan {{n.group.ee_gap}} modul. Isinya adalah
**selisih antara Odoo Community dan Odoo Enterprise**, ditambah lokalisasi
Indonesia: akuntansi, payroll, gudang, portal keuangan, retail, dan e-commerce.
Ini bagian dari platform yang paling bernilai secara komersial, karena
menghilangkan ketergantungan lisensi Enterprise per pengguna untuk kapabilitas
yang dibutuhkan Erajaya.

![Tingkatan modul: semakin ke atas, semakin sedikit tenant yang tersentuh](svg/D02-tingkatan-modul.svg)

## 1.3 Lapisan teknis

Seluruh tumpukan berjalan sebagai kontainer Docker di satu host, di belakang satu
reverse proxy:

- **Pintu depan** — Caddy dengan Web Application Firewall (OWASP CRS), TLS, dan
  pembatasan laju per alamat IP. Nama sub-domain tenant diterjemahkan menjadi
  nama basis data lewat header, sehingga satu instans Odoo melayani banyak tenant
  tanpa saling melihat.
- **Gerbang login** — halaman `/signin` tersendiri menggantikan pemilih basis data
  bawaan Odoo, yang secara bawaan membocorkan daftar seluruh tenant.
- **Aplikasi** — Odoo 19 Community dengan {{n.modules_total}} modul custom di
  atasnya, ditambah beberapa aplikasi pendamping (konsol admin, storefront,
  aplikasi PMO) yang berbicara ke Odoo lewat API bertanda tangan.
- **Data** — satu klaster PostgreSQL dengan satu basis data per tenant, Redis
  untuk pencegahan replay dan cache, MinIO untuk objek dan salinan cadangan.
- **Integrasi** — satu kontrak HMAC dipakai untuk kedua arah: setiap panggilan
  masuk dan keluar ditandatangani dengan stempel waktu, dibatasi selisih waktu
  300 detik, dan dijaga terhadap pengulangan lewat Redis.

![Arsitektur platform: dari pengguna sampai basis data](svg/D01-arsitektur.svg)

Rincian operasional lapisan ini — siklus hidup tenant, hak akses, cadangan, dan
apa yang **belum** dibangun — ada di Bab 15.

## 1.4 Domain fungsional dalam dokumen ini

Tiga belas domain di bawah ini adalah cara dokumen ini membaca
{{n.modules_total}} modul tersebut. Pengelompokan ini dibuat untuk pembaca bisnis
dan tidak selalu sama dengan struktur direktori: sebuah modul akuntansi tetap
masuk domain Keuangan meskipun ia berada di `addons/_tenants/`.

{{TABEL_DOMAIN}}

![Modul per domain fungsional](svg/D04-peta-domain.svg)
