---
title: Vertikal Industri
domain: vertikal-industri
---

# 14. Vertikal Industri

{{n.domain.vertikal-industri}} modul membentuk dua paket khusus industri: **PPOB
/ Value-Added Services** untuk Eraspace, dan **operasi stok F&B** untuk EFN.
Berbeda dengan domain lain, modul di sini dirancang sebagai satu suite yang
dipasang bersama, bukan sebagai fitur yang dipilih satu per satu.

## 14.1 PPOB — Payment Point Online Bank

Dua belas modul menopang bisnis value-added services Erajaya: pulsa, paket data,
token listrik, dan pembayaran tagihan yang dijual lewat jaringan **mitra**
(reseller B2B) dengan model prabayar.

**Fondasi** (`custom_ppob_core`) menyediakan partner mitra dan provider, katalog
produk dengan denominasi, tingkatan harga per mitra, dan kerangka pemetaan bagan
akun. Satu field di sini menentukan perlakuan pajak seluruh kelas produk: mode
PPN — margin, DPP nilai lain, gross, atau bebas — sesuai PMK-63/2022 untuk
distributor pulsa dan voucher.

**Dompet** (`custom_ppob_wallet`) adalah fondasi kebenarannya. Satu dompet per
pasangan (mitra, kelas produk), dengan operasi debit dan kredit yang **atomik**:
kunci baris `SELECT ... FOR UPDATE`, jurnal berpasangan, baris sub-ledger, dan
pembaruan saldo — semuanya dalam satu transaksi PostgreSQL. Tidak ada celah di
mana saldo dan buku besar berbeda. Dalam bisnis prabayar, dua penjualan simultan
yang keduanya berhasil terhadap saldo terakhir yang sama adalah kerugian
langsung.

**Transaksi** (`custom_ppob_sale`) menjalankan state machine
`pending → inquiry_ok → in_progress → success / failed / timeout / refunded`,
menarik dompet mitra dan deposit provider secara atomik, lalu memanggil adapter
provider. Sebuah cron reaper menyelesaikan transaksi yang tergantung dengan
**menanyakan status ke provider terlebih dahulu, tidak pernah langsung
mengembalikan dana** — penjagaan agar pelanggan tidak dibayar dua kali ketika
provider hanya lambat.

**Virtual Account** (`custom_ppob_va`) menangani top-up dompet lewat VA bank
(BCA, BNI, BRI, Mandiri, Permata). Jaminan idempotensinya bukan penjagaan replay
berbasis waktu, melainkan **indeks unik pada referensi bank**: callback ganda
mengkredit dompet tepat satu kali dan mengembalikan tanda terima yang sama.

Sisanya melengkapi rantai: **provider** dengan inventori bucket atomik dan topup
deposit, **komisi** dua arah dengan pemotongan PPh 23, **rollup harian** yang
mengagregasi transaksi menjadi satu faktur ringkas per mitra untuk e-Faktur,
**target SLA** per provider dengan pengambilan sampel per jam, dan tiga jembatan:
Digiflazz sebagai biller H2H, **ERASPACE** untuk mencerminkan feed POS, serta
**Oracle EVShop** untuk pipeline lama.

`custom_ppob_pps_gateway` membalik arahnya: ia mengekspos API H2H sehingga POS
ERASPACE dapat bertransaksi ke Odoo, menjadikan Odoo sebagai switcher — tahap
kedua dari rencana menggantikan sistem lama sebagai sumber kebenaran dompet.

Seluruh suite PPOB saat ini berjalan di basis data pengembangan `rnd_ppob`.

## 14.2 F&B di atas ESB Core

`custom_fnb_stock_ops` menyediakan tiga kapabilitas yang dibutuhkan vertikal EFN
di atas ESB Core: **stock opname**, **prakiraan permintaan**, dan
**replenishment otomatis** untuk outlet. Mesin integrasinya sendiri
(`custom_esb_connector`) tinggal di domain Integrasi, sesuai aturan bahwa mesin
bersama tidak boleh masuk vertikal.

Status: pembangunan selesai dan teruji, menunggu kredensial staging ESB.

## 14.3 Template vertikal

`custom_vertical_example` adalah modul rujukan — titik awal untuk membangun
vertikal baru. Ia tidak pernah dipasang di mana pun dan dihitung hanya agar
totalnya dapat direkonsiliasi. Ia juga satu-satunya modul yang berada satu
tingkat lebih dalam dari standar direktori, di `verticals/_template/`.

## 14.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
