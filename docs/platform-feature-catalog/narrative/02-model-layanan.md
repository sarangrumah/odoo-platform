---
title: Model Layanan — Umum vs Khusus Brand
---

# 2. Model Layanan — Umum versus Khusus Brand

Pertanyaan "fitur ini bisa dipakai brand lain atau tidak" tidak punya jawaban
biner. Katalog ini membedakan **tiga tingkat**, dan perbedaannya menentukan
berapa biaya membawa sebuah kapabilitas ke tenant berikutnya.

## 2.1 Tiga tingkat cakupan

**Umum** — {{n.scope.general}} modul. Tersedia untuk tenant mana pun tanpa utang
konfigurasi berarti. Pasang, aktifkan, pakai. Mayoritas kapabilitas akuntansi,
SDM, gudang, dan produktivitas berada di tingkat ini.

**Umum, dikonfigurasi untuk brand tertentu** — mesin generik yang **sudah membawa
profil, data, atau pemetaan satu brand**. Tenant kedua bisa memakainya, tetapi
harus menyediakan profilnya sendiri. Dua contoh yang paling menjelaskan:

- `custom_retail_import` adalah mesin ingest Excel/CSV/SFTP yang sepenuhnya
  generik. Yang khusus Levi's adalah profil format berkas XStore di dalam
  datanya. Retailer lain memerlukan profilnya sendiri, bukan modul baru.
- `l10n_erajaya` menyediakan bagan akun 10 digit standar grup. Ia dipakai bersama
  oleh dua tenant live — ARKA-AIM dan Levi's — dan siap dipakai tenant Erajaya
  berikutnya tanpa perubahan kode.

**Khusus brand** — {{n.scope.tenant}} modul di `addons/_tenants/`. Terikat pada
satu entitas dan **tidak dapat dipakai ulang apa adanya**. Isinya adalah aturan
yang benar-benar hanya berlaku di sana: saldo awal per tanggal tertentu, format
penomoran dokumen satu perusahaan, akun revaluasi aset satu entitas.

Dua tingkat sisanya melengkapi gambaran: **Platform** ({{n.scope.platform}} modul)
adalah lapisan kendali yang melayani operator, bukan tenant; **Pihak ketiga**
({{n.scope.vendor}} modul) adalah komponen OCA yang di-vendor dan tidak diubah.

## 2.2 Mengapa modul khusus brand sedikit

Angka {{n.scope.tenant}} dari {{n.modules_total}} bukan kebetulan. Ada aturan
tertulis yang mencegahnya membesar: **mesin bersama tidak boleh masuk
`_tenants/`**, seberapa pun jelas ia diminta oleh satu pelanggan. Yang boleh masuk
ke sana hanyalah data dan aturan yang secara definisi tidak berlaku di tempat
lain.

Ketika sebuah pola muncul untuk pelanggan kedua, ia dipromosikan naik ke
`ee_gap/`. Jadi tekanan sistemnya mengarah ke pengurangan modul khusus brand
seiring waktu, bukan penambahan.

Konsekuensi praktisnya untuk perencanaan: **biaya menambah brand baru terutama
adalah konfigurasi dan migrasi data, bukan pengembangan.** Yang perlu dibangun
biasanya hanya bagan akun, penomoran dokumen, saldo awal, dan aturan lokal yang
tidak dimiliki entitas lain.

## 2.3 Cara membaca kolom Brand Terkait

Di setiap tabel domain, kolom **Brand** menunjukkan brand yang modul tersebut
**sudah membawa data atau konfigurasinya**. Kolom ini bukan daftar instalasi:

- Untuk modul **khusus brand**, kolom ini adalah pemiliknya.
- Untuk modul **umum**, kolom ini adalah brand yang profilnya sudah dikirim —
  petunjuk bahwa jalur itu sudah terbukti jalan, dan bahwa tenant lain akan
  memerlukan profilnya sendiri.
- Kolom kosong berarti modul berlaku umum tanpa data brand apa pun.

Pemetaan lengkap modul terhadap brand tersedia sebagai matriks di lembar **Peta
Brand** pada berkas Excel pendamping dokumen ini. Ringkasannya per domain:

![Domain terhadap brand](svg/D05-peta-brand.svg)

## 2.4 Kematangan dan keyakinan informasi

Dua kolom lain muncul di setiap tabel, dan keduanya adalah penilaian, bukan fakta
mentah:

**Kematangan** diturunkan dari kode. Modul dengan suite pengujian dinilai
*Produksi*; modul dengan model, endpoint, atau data tetapi tanpa pengujian dinilai
*Beta*; modul kosong dinilai *Kerangka*. Sebelas modul dikoreksi manual karena
mereka berjalan di produksi tanpa membawa pengujian — penilaian otomatis akan
salah menurunkannya.

**Keyakinan Info** menyatakan seberapa dipercaya deskripsi di dokumen ini,
bukan seberapa baik modulnya. *Tinggi* berarti deskripsi ditulis atau diperiksa
manusia. *Sedang* berarti berasal dari dokumen pengetahuan hasil generator yang
belum diperiksa. *Rendah* berarti tidak ada dokumen pengetahuan, atau gerbang
audit menemukan klaim yang tidak didukung kode.

Membedakan keduanya penting. Sebuah modul bisa berstatus Produksi dengan
Keyakinan Rendah — artinya ia berjalan baik, tetapi katalog ini belum bisa
menjamin deskripsinya lengkap.
