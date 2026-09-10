# Functional Specification Document (FSD)
## Implementasi PPOB / Bill-Payment Switching di atas Odoo 19

| | |
|---|---|
| **Dokumen** | 02 — Functional Specification Document |
| **Versi** | 1.0 |
| **Tanggal** | 2026-08-11 |
| **Pembaca** | Key user, BA, QA, Ops, Finance |
| **Prasyarat** | [`01-BRD.md`](01-BRD.md) |

---

## Contents

1. [Gambaran solusi](#1-gambaran-solusi)
2. [Peta modul & navigasi](#2-peta-modul--navigasi)
3. [Peran & hak akses](#3-peran--hak-akses)
4. [Spesifikasi fungsional per area](#4-spesifikasi-fungsional-per-area)
5. [Kanal & API masuk](#5-kanal--api-masuk)
6. [Keuangan, pajak & pelaporan](#6-keuangan-pajak--pelaporan)
7. [Operasional harian](#7-operasional-harian)
8. [User journey](#8-user-journey)
9. [Perilaku non-fungsional](#9-perilaku-non-fungsional)
10. [Acceptance test representatif](#10-acceptance-test-representatif)
11. [Matriks traceability BR → fungsi](#11-matriks-traceability-br--fungsi)

---

## 1. Gambaran solusi

Solusi terdiri dari **12 modul** `custom_ppob_*` yang bekerja dalam empat lapis:

```
  KANAL MASUK        pps_gateway (H2H drop-in)   va (VA bank)   eraspace_bridge (mirror)
        |                     |                       |                  |
        v                     v                       v                  v
  MESIN TRANSAKSI  ---------------- custom_ppob_sale ----------------------------
        |            state machine · idempotensi · routing · refund · reaper
        |
        +--> WALLET MITRA      custom_ppob_wallet    (saldo prepaid, atomik, GL)
        +--> DEPOSIT BILLER    custom_ppob_provider  (bucket atomik, adapter, DP-100%)
        +--> ADAPTER BILLER    biller_digiflazz · adapter mock · adapter HTTP generik
                                oracle_bridge (jalur legacy, opsional)
        |
  FONDASI & FINANCE  custom_ppob_core (master + mapping akun)
                     custom_ppob_rollup (faktur ringkas harian)
                     custom_ppob_commission (komisi + PPh 23)
                     custom_ppob_sla (target & sampling throughput)
```

Prinsip fungsional yang menentukan perilaku seluruh sistem:

1. **Uang bergerak lewat primitif atomik.** Debit/kredit wallet dan deposit selalu melalui
   fungsi yang mengunci baris dan menulis jurnal pada transaksi basis data yang sama.
2. **Idempotensi ditegakkan basis data.** Kombinasi mitra + kunci idempotensi unik; permintaan
   ulang mengembalikan hasil pertama.
3. **Status "pending" adalah status sah**, bukan kegagalan. Hanya kegagalan terkonfirmasi yang
   memicu refund.
4. **Semua data masuk yang tak dikenali disimpan**, tidak dibuang.

## 2. Peta modul & navigasi

| Modul | Fungsi bisnis | Menu utama |
|---|---|---|
| `custom_ppob_core` | Kelas produk, katalog, tier harga, mitra/provider, pemetaan akun | PPOB ▸ Master Data |
| `custom_ppob_wallet` | Saldo mitra + buku pembantu | PPOB ▸ Wallet |
| `custom_ppob_provider` | Provider, bucket deposit, SKU map, top-up deposit | PPOB ▸ Provider |
| `custom_ppob_sale` | Transaksi PPOB, mutasi wallet & bucket | PPOB ▸ Transaksi |
| `custom_ppob_va` | VA bank, top-up mitra, koneksi bank | PPOB ▸ Top-up |
| `custom_ppob_pps_gateway` | Kredensial kanal, log callback, field game | PPOB ▸ Gateway |
| `custom_ppob_eraspace_bridge` | Koneksi feed, join transaksi, settlement, antrean lewatan | PPOB ▸ Bridge |
| `custom_ppob_oracle_bridge` | Jalur legacy Oracle EVShop (opsional) | PPOB ▸ Oracle |
| `custom_ppob_biller_digiflazz` | Adapter biller Digiflazz | (di form Provider) |
| `custom_ppob_commission` | Aturan & akrual komisi, settlement | PPOB ▸ Komisi |
| `custom_ppob_rollup` | Faktur ringkas harian per mitra | PPOB ▸ Rollup |
| `custom_ppob_sla` | Target SLA + sampel throughput | PPOB ▸ SLA |

## 3. Peran & hak akses

Empat grup di bawah satu privilege "PPOB":

| Grup | Untuk siapa | Kemampuan |
|---|---|---|
| **PPOB User** | Staf operasional dasar | Melihat transaksi, wallet, dan mutasi; tidak mengubah saldo |
| **PPOB Ops** | Operator harian (mewarisi User) | Dispatch ulang, refund manual, top-up deposit, tinjau antrean lewatan, backfill |
| **PPOB Manager** | Supervisor & finance (mewarisi Ops) | Master data, tier harga, aturan komisi, target SLA, freeze wallet, pemetaan akun |
| **PPOB API** | Akun teknis integrasi (mewarisi Ops) | Dipakai jalur integrasi; tidak untuk login manusia |

Aturan pemisahan tugas yang disarankan: pihak yang **mengubah tier harga / aturan komisi**
bukan pihak yang **menjalankan refund manual**.

## 4. Spesifikasi fungsional per area

### 4.1 Master data — `BR-MD-01..07`

| # | Fungsi | Perilaku |
|---|---|---|
| F-MD-01 | Kelas produk | Kode, nama, akun default (wallet liability, revenue, COGS), dan **mode PPN**: marjin · nilai lain · bruto · bebas |
| F-MD-02 | Produk PPOB | Kode unik, kelas, denominasi, harga modal default, penanda "perlu inquiry" — dengan akun revenue/COGS opsional yang menimpa default kelas |
| F-MD-03 | Tier harga | Kumpulan baris produk → harga jual; harga jual wajib positif |
| F-MD-04 | Mitra | Partner ditandai mitra, kode mitra unik, tier melekat, penanda NPWP terhitung otomatis |
| F-MD-05 | Cap mitra | Cap nilai transaksi harian & bulanan; dievaluasi sebelum dispatch atas transaksi berstatus sukses + diproses |
| F-MD-06 | Pemetaan akun | Peran (mis. `ppn_keluaran`, `ppn_masukan`, `provider_deposit_default`) → akun, per perusahaan |
| F-MD-07 | Provider/biller | Kode, vendor, mode settlement (deposit prabayar / pascabayar), status (aktif · maintenance · nonaktif), prioritas failover, ambang stale, mode bucket, akun & jurnal |

### 4.2 Wallet mitra — `BR-WL-01..09`

| # | Fungsi | Perilaku |
|---|---|---|
| F-WL-01 | Struktur wallet | Satu wallet per mitra per kelas produk per perusahaan (dijaga unik) |
| F-WL-02 | Debit atomik | Mengunci baris wallet, membaca saldo terkini, menolak bila melebihi saldo + credit limit, menulis jurnal Dr *liability wallet* / Cr *counterpart*, mencatat mutasi + saldo akhir |
| F-WL-03 | Kredit atomik | Kebalikan dari debit: Dr *counterpart* / Cr *liability wallet* |
| F-WL-04 | Kredit inklusif pajak | Memecah nilai bruto menjadi DPP + PPN; wallet hanya bertambah sebesar DPP, PPN diarahkan ke akun PPN keluaran |
| F-WL-05 | Freeze | Wallet berstatus beku menolak debit maupun kredit dengan pesan jelas |
| F-WL-06 | Credit limit | Batas overdraw per mitra; nol berarti tidak boleh minus |
| F-WL-07 | Buku pembantu | Setiap mutasi menyimpan jenis, nilai bertanda, saldo setelah mutasi, referensi, dan tautan jurnal |
| F-WL-08 | **API wallet sinkron** | `hold` / `commit` / `release` / `credit` / `balance`, bertanda tangan HMAC, idempoten per referensi transaksi — **PERLU DIBANGUN** |
| F-WL-09 | Saldo pembuka | Pemuatan saldo awal dari sistem lama dengan jurnal migrasi tertelusur — **PERLU DIBANGUN** |

### 4.3 Deposit biller — `BR-DP-01..07`

| # | Fungsi | Perilaku |
|---|---|---|
| F-DP-01 | Mode bucket | *bulky* (satu bucket untuk semua produk provider) atau *fixed denom* (satu bucket per produk/denominasi) |
| F-DP-02 | Drawdown atomik | Kunci baris + tolak saldo kurang + jurnal Dr *COGS* / Cr *deposit* |
| F-DP-03 | Non-negatif | Dijaga constraint basis data, bukan hanya validasi aplikasi |
| F-DP-04 | Low-water-mark | Ambang per bucket sebagai dasar peringatan |
| F-DP-05 | Top-up DP-100% | Wizard: nilai bruto, diskon, nilai dibayar, split DPP/PPN sesuai metode Coretax provider; menghasilkan invoice DP dan (bila perlu) pelunasan |
| F-DP-06 | Perlakuan diskon | Diakui sesuai konfigurasi provider (pendapatan lain atau pengurang harga modal) |
| F-DP-07 | Integrasi stok opsional | Bucket dapat ditautkan produk inventaris sehingga pemakaian deposit menerbitkan pengeluaran barang |

### 4.4 Transaksi & routing — `BR-TX-01..12`

Alur `_dispatch`:

```
  cek status boleh dispatch
        |
  cek cap harian/bulanan mitra
        |
  resolusi provider  <-- SKU map: prioritas asc, provider aktif
        |             (harga modal diambil dari baris SKU yang menang)
  debit wallet mitra  --> jurnal
        |
  debit bucket deposit (bila provider prabayar) --> jurnal
        |
  status = diproses, catat waktu dispatch
        |
  panggil adapter (diukur latensinya)
        |
   +----+-----------------------------+
   |          |                       |
  sukses    gagal                  pending (ok = None)
   |          |                       |
  status    refund wallet+bucket    biarkan; reaper yang meresolusi
  sukses    status gagal
```

| # | Fungsi | Perilaku |
|---|---|---|
| F-TX-01 | Status transaksi | pending · inquiry OK · diproses · sukses · gagal · timeout · refund |
| F-TX-02 | Idempotensi | Unik per (mitra, kunci idempotensi); permintaan ulang mengembalikan transaksi asli |
| F-TX-03 | Resolusi provider | Bila provider ditentukan, wajib ada SKU map; bila tidak, pilih prioritas terkecil di antara provider aktif |
| F-TX-04 | Koreksi harga modal | Harga modal ditulis ulang dari baris SKU yang menang; bila nol dan tanpa default, transaksi ditolak dengan pesan tegas |
| F-TX-05 | Inquiry | Produk berpenanda "perlu inquiry" memanggil `inquiry()` lebih dulu; konfirmasi memindahkan status ke inquiry OK |
| F-TX-06 | Tiga kemungkinan jawaban adapter | sukses · gagal · **belum selesai**. Jawaban "belum selesai" tidak pernah diperlakukan sebagai kegagalan |
| F-TX-07 | Refund otomatis | Mengembalikan wallet dan bucket beserta jurnal balik; berhenti bila refund sudah pernah dilakukan |
| F-TX-08 | Reaper | Berkala memeriksa transaksi diproses yang melewati ambang provider, menanyakan `status()`, lalu menandai sukses atau timeout + refund; provider tanpa `status()` dibiarkan untuk ops manual |
| F-TX-09 | Retry | Menggandakan transaksi dengan nomor percobaan +1 dan kunci idempotensi turunan |
| F-TX-10 | Refund manual | Hanya untuk transaksi gagal/timeout, oleh peran Ops |
| F-TX-11 | Pengukuran latensi | Latensi adapter diukur khusus di sekitar panggilan biller, terpisah dari waktu posting GL |
| F-TX-12 | Penjualan manual | Wizard untuk ops membuat transaksi tanpa kanal (mis. penanganan eksepsi) |

### 4.5 Integrasi biller — `BR-BL-01..06`

| # | Fungsi | Perilaku |
|---|---|---|
| F-BL-01 | Registry adapter | Adapter didaftarkan dengan dekorator dan muncul sebagai pilihan pada provider |
| F-BL-02 | Kontrak adapter | `inquiry()`, `pay()`, `status()`, `topup()`, `check_balance()` — implementasi mengembalikan objek hasil berisi ok (tri-state), referensi provider, token/serial, kode & pesan galat, payload mentah |
| F-BL-03 | Adapter mock | Hasil dapat disetel sukses/gagal/timeout untuk QA dan demo |
| F-BL-04 | Adapter Digiflazz | Prepaid top-up + tagihan pascabayar (inquiry & bayar), penandatanganan MD5 sesuai spesifikasi vendor, `ref_id` sebagai kunci idempotensi |
| F-BL-05 | Kredensial | Diambil dari konfigurasi adapter per tenant, atau parameter sistem; tidak pernah disimpan di record provider |
| F-BL-06 | Log panggilan | Endpoint, payload, kode status, latensi, galat, dan hasil tercatat bila provider memakai konfigurasi adapter |

> **Batasan yang harus dinyatakan ke klien:** pada Digiflazz jalur **prepaid tidak memiliki
> `inquiry()` maupun `status()`** (keduanya menolak dengan galat "tidak tersedia"). Artinya
> reaper tidak dapat meresolusi otomatis transaksi prepaid yang menggantung pada jalur itu —
> resolusinya menunggu webhook vendor atau penanganan ops manual.

### 4.6 Kanal masuk — `BR-CH-01..07`

Gateway H2H meniru kontrak switcher lama sehingga aplikasi kanal cukup mengganti base URL.

| # | Endpoint | Fungsi |
|---|---|---|
| F-CH-01 | `POST /pps/sell` | Membuat + men-dispatch transaksi; permintaan ulang dengan nomor transaksi sama mengembalikan hasil asli |
| F-CH-02 | `POST /pps/statustrx` | Status terakhir transaksi |
| F-CH-03 | `POST /pps/statustrxwithdeposit` | Status + saldo wallet mitra |
| F-CH-04 | `POST /pps/checknocustomer` | Inquiry nama pemilik nomor e-wallet |
| F-CH-05 | `POST /pps/inquiry-pln` | Inquiry PLN (meter, nama, tarif) |
| F-CH-06 | `POST /pps/game-list` | Katalog produk game + field dinamis |
| F-CH-07 | `POST /pps/direct-topup` | Top-up game dengan payload field dinamis |
| F-CH-08 | Callback | Hasil transaksi asinkron dikirim ke URL callback mitra secara berkala; status polling tetap tersedia sebagai cadangan |

Keamanan kanal: kredensial per mitra (`pps_user` + rahasia), **daftar IP yang diizinkan**,
tanda tangan per endpoint sesuai spesifikasi vendor, dan idempotensi basis data.

> **Koreksi yang harus disampaikan:** dokumentasi modul menyebut adanya penjaga replay dan
> pemeriksaan kesegaran waktu. Pada kode saat ini yang benar-benar ditegakkan adalah **IP
> allowlist + tanda tangan + idempotensi basis data**; field toleransi selisih waktu ada
> tetapi tidak dibaca. Ini gap G5 dan masuk lingkup.

### 4.7 Top-up mitra — `BR-TU-01..07`

| # | Fungsi | Perilaku |
|---|---|---|
| F-TU-01 | VA mitra | Nomor VA per bank per mitra, tertaut wallet tujuan, dengan akun transit |
| F-TU-02 | `POST /api/ppob/va/<bank>/inquiry` | Bank memvalidasi VA; jawaban berisi identitas mitra dan kelas wallet |
| F-TU-03 | `POST /api/ppob/va/<bank>/payment` | Bank memberitahu pembayaran; top-up dibuat dan wallet dikredit |
| F-TU-04 | Idempotensi | Referensi bank unik; callback ganda mengembalikan acknowledgment asli tanpa kredit kedua |
| F-TU-05 | Keamanan | HMAC-SHA256 atas timestamp + body, rahasia per bank, toleransi selisih waktu, penjaga replay, allowlist IP |
| F-TU-06 | Jalur rekening koran | Aturan rekonsiliasi mencocokkan baris rekening koran ke VA dan membuat top-up bila bank tidak mengirim callback |
| F-TU-07 | Penolakan | Top-up dapat ditolak ops dengan alasan; tidak menyentuh wallet |

## 5. Kanal & API masuk

Ringkasan seluruh permukaan API yang menyentuh uang:

| Jalur | Arah | Autentikasi | Idempotensi |
|---|---|---|---|
| `/pps/*` (7 endpoint) | Kanal → Odoo | Tanda tangan per endpoint + IP allowlist | `unique(mitra, kunci)` |
| `/api/ppob/va/<bank>/inquiry` | Bank → Odoo | HMAC + IP + nonce | — (baca saja) |
| `/api/ppob/va/<bank>/payment` | Bank → Odoo | HMAC + IP + nonce | `unique(bank_ref)` |
| `/api/ppob/eraspace/pos` | Kanal/legacy → Odoo | HMAC + IP + nonce | `unique(pos_ref)` |
| `/api/ppob/eraspace/h2h` | Switcher → Odoo | HMAC + IP + nonce | `unique(h2h_ref)` |
| API wallet (`hold`/`commit`/`release`/`credit`/`balance`) | Switcher → Odoo | HMAC + IP + nonce | per referensi + langkah — **PERLU DIBANGUN** |

Mirror bridge menyatukan dua feed berdasarkan referensi transaksi kanal, menghitung marjin, dan
menandai transaksi yang tidak berpasangan sebagai temuan rekonsiliasi. Data yang tidak dapat
dipetakan (mitra/produk/biller tak dikenal, status belum final, galat posting) masuk **antrean
lewatan** lengkap dengan alasan dan payload asli, dan dapat dimasukkan ulang lewat backfill.

## 6. Keuangan, pajak & pelaporan

### 6.1 Pola jurnal

| Peristiwa | Jurnal |
|---|---|
| Top-up mitra via VA | Dr *Kas/Transit bank* — Cr *Utang saldo mitra* |
| Top-up mitra inklusif pajak | Dr *Kas/Transit* — Cr *Utang saldo mitra* (DPP) — Cr *PPN keluaran* |
| Penjualan (debit wallet) | Dr *Utang saldo mitra* — Cr *Pendapatan PPOB* |
| Penjualan (pemakaian deposit) | Dr *Harga pokok* — Cr *Deposit biller* |
| Transaksi gagal | Kebalikan dari kedua jurnal di atas |
| Top-up deposit biller (DP-100%) | Dr *Uang muka/Deposit* + Dr *PPN masukan* — Cr *Kas/Utang vendor* |
| Faktur ringkas harian | Faktur penjualan ringkas per mitra dengan PPN sesuai mode kelas |
| Komisi diterima | Dr *Piutang komisi* — Cr *Pendapatan komisi* |
| Komisi ke mitra | Dr *Beban komisi* — Cr *Utang komisi mitra* — Cr *Utang PPh 23* |

### 6.2 PPN

Mode PPN ditetapkan **per kelas produk**:

| Mode | Dasar pengenaan |
|---|---|
| `margin` | Harga jual − harga modal (PMK-63/2022) |
| `other_valuation` | 10/11 dari harga jual |
| `gross` | Harga jual penuh |
| `exempt` | Nol |

PPN **tidak** diakui per transaksi; pengakuan terjadi pada **faktur ringkas harian per mitra**
(rollup). Jurnal ringkasan non-GL dikecualikan dari laporan keuangan agar tidak terhitung ganda.

### 6.3 Komisi & PPh 23

Aturan komisi berskala kelas/produk/mitra dengan dua arah (**dari provider** dan **ke mitra**),
tipe perhitungan persentase atau nilai tetap, serta masa berlaku. Akrual dibuat per transaksi
sukses, dipotong PPh 23 sesuai status NPWP mitra, dan diselesaikan lewat wizard settlement yang
menghasilkan jurnal pelunasan dan bukti potong.

### 6.4 Pelaporan

| Laporan | Isi | Frekuensi |
|---|---|---|
| Marjin per produk / mitra / biller | Volume, bruto, harga modal, marjin | Harian |
| Rekonsiliasi wallet vs GL | Saldo wallet vs saldo akun liability | Harian |
| Rekonsiliasi deposit | Bucket vs saldo biller | Harian |
| Faktur ringkas per mitra | Dasar e-Faktur/Coretax | Harian |
| SLA & throughput | Volume, tingkat sukses, latensi p95, pelanggaran target | Per jam |
| Antrean lewatan | Data masuk yang perlu ditinjau | Harian |

## 7. Operasional harian

| Waktu | Aktivitas | Pelaku |
|---|---|---|
| Sepanjang hari | Pantau antrean lewatan dan transaksi timeout | Ops |
| Sepanjang hari | Pantau saldo deposit terhadap low-water-mark; ajukan top-up | Ops |
| Tiap jam | Tinjau sampel throughput & pelanggaran SLA | Ops |
| Pagi | Verifikasi faktur ringkas harian terbit | Finance |
| Pagi | Cocokkan saldo wallet total vs GL liability | Finance |
| Mingguan | Settlement komisi + bukti potong | Finance |
| Insidental | Refund manual setelah konfirmasi biller | Ops (dengan persetujuan) |

Pekerjaan terjadwal yang berjalan otomatis: reaper transaksi menggantung (tiap 5 menit),
pengiriman callback kanal (tiap menit), rekonsiliasi bridge (tiap 5 menit), sampling throughput
(tiap jam), rollup faktur (harian), serta sinkronisasi jalur legacy bila diaktifkan.

## 8. User journey

### J1 — Mitra top-up saldo (otomatis)
1. Mitra transfer ke nomor VA miliknya.
2. Bank memanggil endpoint inquiry lalu payment.
3. Odoo memverifikasi tanda tangan, membuat record top-up, mengkredit wallet, memposting jurnal.
4. Saldo mitra bertambah seketika; callback ganda tidak menambah lagi.

### J2 — Mitra menjual pulsa (jalur sukses)
1. Kanal mengirim permintaan jual bertanda tangan.
2. Odoo memverifikasi kredensial + IP, memeriksa duplikasi nomor transaksi.
3. Cap mitra diperiksa; provider dipilih dari SKU map.
4. Wallet dan deposit didebit beserta jurnal; status menjadi diproses.
5. Adapter memanggil biller; jawaban sukses menutup transaksi dan token dikirim balik.

### J3 — Biller menolak (jalur gagal)
1. Sama sampai langkah 4 di atas.
2. Adapter menjawab gagal.
3. Odoo mengembalikan saldo wallet dan deposit beserta jurnal balik, status menjadi gagal.
4. Kanal menerima pesan galat; saldo mitra utuh.

### J4 — Transaksi menggantung
1. Adapter menjawab "belum selesai"; transaksi tetap berstatus diproses.
2. Melewati ambang provider, reaper menanyakan status.
3. Jawaban sukses → transaksi ditutup sukses. Jawaban gagal → refund + status timeout. Jawaban
   masih diproses → dibiarkan sampai siklus berikutnya.

### J5 — Deposit biller menipis
1. Saldo bucket menembus low-water-mark; ops menerima peringatan.
2. Ops menjalankan wizard top-up deposit (bruto, diskon, split DPP/PPN).
3. Invoice DP terbit; setelah pembayaran, saldo bucket bertambah beserta jurnal.

### J6 — Tutup hari finance
1. Rollup harian membentuk faktur ringkas per mitra dari transaksi sukses.
2. Finance memverifikasi total dan mengekspor untuk e-Faktur/Coretax.
3. Rekonsiliasi wallet vs GL dan deposit vs biller diperiksa; selisih ditindaklanjuti.

### J7 — Menyalakan biller baru
1. Manager membuat provider, memilih kelas adapter, dan menautkan konfigurasi adapter berisi kredensial.
2. Manager mengisi SKU map (produk → SKU biller, harga modal, prioritas).
3. Uji koneksi dijalankan; transaksi uji memakai adapter mock lalu adapter riil di sandbox.
4. Target SLA diisi; provider diaktifkan untuk irisan kecil lebih dulu.

### J8 — Onboarding mitra baru
1. Manager membuat partner mitra (kode unik, tier harga, cap harian/bulanan).
2. Wallet per kelas dibuat, akun & jurnal terisi dari default kelas.
3. Nomor VA diterbitkan dan ditautkan.
4. Kredensial kanal dibuat beserta allowlist IP dan URL callback.

## 9. Perilaku non-fungsional

| Aspek | Perilaku |
|---|---|
| Konkurensi | Debit paralel pada wallet/bucket yang sama diserialisasi lewat kunci baris; saldo tidak pernah negatif |
| Idempotensi | Ditegakkan constraint unik pada basis data untuk transaksi, top-up VA, dan feed masuk |
| Ketahanan | Kegagalan adapter tidak pernah membiarkan saldo terdebit tanpa transaksi; kegagalan posting mengarahkan data ke antrean tinjauan |
| Keamanan | Seluruh endpoint uang bertanda tangan + IP allowlist; rahasia di luar record bisnis |
| Auditabilitas | Perubahan status, nilai, dan referensi provider terekam pada jejak audit transaksi |
| Kinerja | Latensi adapter terukur per transaksi; throughput & p95 tersampel per jam |

## 10. Acceptance test representatif

| # | Uji | Kriteria lulus | BR |
|---|---|---|---|
| AT-01 | Debit wallet melampaui saldo + limit | Ditolak dengan pesan jelas; saldo tidak berubah | BR-WL-03 |
| AT-02 | Dua debit paralel pada wallet sama | Keduanya diserialisasi; saldo akhir benar; tidak negatif | BR-NF-01 |
| AT-03 | Debit wallet berhasil | Saldo turun; jurnal Dr liability / Cr revenue terbit; mutasi mencatat saldo akhir | BR-WL-05 |
| AT-04 | Wallet beku didebit | Ditolak | BR-WL-04 |
| AT-05 | Jual dengan nomor transaksi yang sama dua kali | Transaksi kedua mengembalikan hasil pertama; tidak ada transaksi baru | BR-TX-02, BR-TX-03 |
| AT-06 | Jual saat cap harian terlampaui | Ditolak sebelum saldo tersentuh | BR-MD-05 |
| AT-07 | Provider utama nonaktif | Rute jatuh ke provider prioritas berikutnya; harga modal mengikuti provider itu | BR-TX-04, BR-TX-05 |
| AT-08 | Adapter menjawab gagal | Wallet & deposit kembali; jurnal balik terbit; status gagal | BR-TX-07 |
| AT-09 | Refund dipanggil dua kali | Hanya satu pengembalian | BR-TX-08 |
| AT-10 | Adapter menjawab "belum selesai" | Transaksi tetap diproses; tidak ada refund | BR-TX-09 |
| AT-11 | Reaper atas transaksi stale, biller menjawab sukses | Status menjadi sukses; tidak ada refund | BR-TX-09 |
| AT-12 | Reaper atas transaksi stale, biller menjawab gagal | Refund + status timeout | BR-TX-09 |
| AT-13 | Reaper atas provider tanpa endpoint status | Tidak ada refund otomatis; transaksi tercatat untuk ops | BR-TX-09 |
| AT-14 | Deposit kurang saat dispatch | Transaksi ditolak; saldo wallet tidak ikut terdebit | BR-DP-02 |
| AT-15 | Callback pembayaran VA | Wallet terkredit; jurnal terbit; top-up tercatat | BR-TU-03 |
| AT-16 | Callback VA ganda | Kredit hanya sekali; jawaban menandai duplikat | BR-TU-04 |
| AT-17 | Callback VA tanda tangan salah | Ditolak 401; tidak ada perubahan data | BR-NF-02 |
| AT-18 | Panggilan kanal dari IP di luar allowlist | Ditolak | BR-CH-06 |
| AT-19 | Rollup harian dijalankan dua kali | Faktur tidak berganda | BR-FI-05 |
| AT-20 | Mode PPN marjin | Dasar pengenaan = harga jual − harga modal pada faktur ringkas | BR-FI-03 |
| AT-21 | Komisi mitra tanpa NPWP | PPh 23 dipotong dengan tarif yang lebih tinggi; bukti potong terbit | BR-FI-08 |
| AT-22 | Sampling throughput per jam | Sampel berisi volume, tingkat sukses, p95; pelanggaran target tertandai | BR-OP-02, BR-OP-03 |
| AT-23 | Feed masuk dengan mitra tak dikenal | Masuk antrean lewatan dengan alasan + payload asli; tidak ada posting | BR-OP-05 |
| AT-24 | Backfill periode tertentu | Data masuk ulang tanpa menggandakan posting | BR-OP-06 |
| AT-25 | Dual-run paritas satu hari penuh | Marjin, status akhir, deposit, dan faktur ringkas cocok; selisih 0 | BR-NF-08 |

## 11. Matriks traceability BR → fungsi

| Kelompok BR | Fungsi FSD | Acceptance test |
|---|---|---|
| BR-MD-01..07 | F-MD-01..07 | AT-06 |
| BR-WL-01..09 | F-WL-01..09 | AT-01..AT-04 |
| BR-TU-01..07 | F-TU-01..07 | AT-15..AT-17 |
| BR-DP-01..07 | F-DP-01..07 | AT-14 |
| BR-TX-01..12 | F-TX-01..12 | AT-05, AT-07..AT-13 |
| BR-BL-01..06 | F-BL-01..06 | AT-08, AT-10, AT-13 |
| BR-CH-01..07 | F-CH-01..08 | AT-05, AT-18 |
| BR-FI-01..10 | §6.1–6.4 | AT-19..AT-21 |
| BR-OP-01..07 | §5, §7 | AT-22..AT-24 |
| BR-NF-01..08 | §9 | AT-02, AT-17, AT-25 |

---

*Dokumen berikutnya: [`03-TSD.md`](03-TSD.md) — spesifikasi teknis.*
