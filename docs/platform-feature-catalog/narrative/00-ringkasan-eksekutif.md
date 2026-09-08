---
title: Ringkasan Eksekutif
---

# Ringkasan Eksekutif

Dokumen ini adalah katalog lengkap fitur yang sudah dibangun di atas platform Odoo
Erajaya Group: **{{n.modules_total}} modul custom**, dikelompokkan ke dalam
{{n.tenants}} brand dan tiga belas domain fungsional. Dokumen ini menjawab tiga
pertanyaan yang selama ini tersebar di banyak berkas dan tidak pernah dijawab di
satu tempat:

1. Apa saja yang sudah tersedia?
2. Mana yang berlaku umum untuk tenant mana pun, dan mana yang khusus satu brand?
3. Sejauh mana platform ini benar-benar berjalan sebagai layanan, dan apa yang
   belum ada?

## Angka yang perlu diketahui

| | |
|---|---|
| Modul custom | **{{n.modules_total}}** |
| Berlaku umum untuk semua tenant | {{n.scope.general}} |
| Khusus satu brand (`addons/_tenants/`) | {{n.scope.tenant}} |
| Lapisan kendali platform | {{n.scope.platform}} |
| Komponen pihak ketiga (OCA) | {{n.scope.vendor}} |
| Brand / tenant terdaftar | {{n.tenants}} |
| Kesenjangan tercatat (prioritas tinggi) | {{n.gaps}} ({{n.gaps.high}}) |

Sekitar **{{n.scope.general}} dari {{n.modules_total}} modul berlaku umum**. Hanya
{{n.scope.tenant}} modul yang benar-benar terikat pada satu brand. Itulah angka
yang menopang klaim reuse lintas vertikal: sebuah tenant baru mewarisi hampir
seluruh kapabilitas platform tanpa pengembangan ulang, dan yang tersisa adalah
konfigurasi serta data.

## Apa yang membedakan dokumen ini

Setiap angka di sini **dipindai langsung dari repositori**, bukan diketik. Sebuah
skrip membaca seluruh direktori `addons/`, mengurai setiap manifest dan kode
model, lalu menghasilkan berkas data yang menjadi sumber tunggal bagi versi
Markdown, PDF, dan Excel dokumen ini. Menambahkan modul baru membuat proses build
gagal sampai modul itu diklasifikasikan.

Alasannya sederhana: sebelum dokumen ini dibuat, tabel jumlah modul di dokumen
arsitektur internal salah pada lima dari delapan barisnya. Satu grup tertulis 78
modul padahal berisi 105. Angka yang dipelihara manual selalu tertinggal.

Dokumen ini juga **menandai tingkat keyakinannya sendiri**. Dari
{{n.modules_total}} modul, {{n.knowledge_draft}} memiliki dokumen pengetahuan
hasil generator yang belum diperiksa manusia, dan {{n.knowledge_missing}} belum
memiliki dokumen sama sekali. Isinya tetap dipakai — tetapi setiap baris membawa
kolom **Keyakinan Info**, dan sebuah gerbang otomatis membandingkan setiap klaim
dengan kode sebelum dokumen ini terbit. Klaim yang menyebut model yang tidak ada
di kode diturunkan keyakinannya dan daftar modelnya dibuang.

## Struktur dokumen

- **Bab 1–2** — arsitektur platform dan model layanan: bagaimana satu basis kode
  melayani banyak brand, dan apa arti "umum" versus "khusus brand".
- **Bab 3–15** — tiga belas domain fungsional. Setiap bab menutup dengan
  subbagian *Yang bersifat khusus per-brand*, sehingga pemisahan umum versus
  khusus terlihat di setiap domain, bukan hanya di ringkasan.
- **Bab 15** — administrasi platform dan Odoo sebagai layanan, termasuk analisis
  kesenjangan **Kondisi Saat Ini versus Sasaran** yang jujur.
- **Lampiran** — rincian teknis per modul dalam Bahasa Inggris, untuk tim
  pengembang dan arsitek. Istilah antarmuka Odoo sengaja dipertahankan dalam
  Bahasa Inggris di seluruh dokumen.

## Yang tidak dokumen ini janjikan

Katalog ini mencatat **apa yang ada di dalam basis kode**, bukan apa yang aktif di
setiap basis data. Sebuah modul yang tercatat di sini belum tentu terpasang pada
tenant tertentu; kolom **Brand Terkait** menunjukkan di mana sebuah modul sudah
membawa data atau konfigurasi, bukan daftar instalasi. Untuk pertanyaan
"apakah fitur X aktif di basis data Y", jawabannya ada di basis data itu sendiri,
bukan di dokumen ini.
