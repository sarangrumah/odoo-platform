# Matriks Role Standar — Head Office & Retail

Daftar jabatan standar yang dikirim bersama modul `custom_role_manager`. Sumber
kebenarannya adalah `addons/core/custom_role_manager/data/seed_roles.py`; dokumen
ini adalah bacaan manusianya. Kalau keduanya berbeda, file Python yang benar.

Cara pakai: buka **Settings → Users → Security Roles**, atau langsung tab
**Roles** di form user. Pilih role, simpan — group akses tersusun sendiri.

## Cara membaca

- **Level** menentukan kedalaman wewenang, bukan modulnya: `manager` boleh
  mengubah konfigurasi dan menyetujui, `supervisor` memeriksa dan memposting,
  `staff` menyiapkan dokumen, `operator` menjalankan satu proses harian,
  `readonly` hanya membaca.
- **Mewarisi** berarti role itu otomatis membawa seluruh hak role di bawahnya.
  Jangan menyalin group; tambahkan pewarisan. Store Manager, misalnya, tidak
  punya group sendiri untuk stok — ia mewarisi Store Supervisor.
- Role menjawab **"boleh apa"**. Batas **"boleh atas data siapa"** diatur
  terpisah lewat Operating Unit (tab **Operating Units** di form user). Dua sumbu
  ini sengaja dipisah: seorang Accounting Supervisor di Head Office dan di satu
  toko memegang role yang sama, yang berbeda hanya OU-nya.

## Head Office

| Role | Level | Ringkas | Mewarisi |
|---|---|---|---|
| **Finance & Accounting Manager** | manager | Hak akuntansi penuh: CoA, lock date, persetujuan dokumen keuangan, laporan custom tingkat admin | Accounting Supervisor, Treasury, Tax Officer |
| **Accounting Supervisor** | supervisor | Memeriksa dan memposting apa yang disiapkan staff; menjalankan laporan standar | Accounting Staff AP + AR |
| **Accounting Staff — AP** | staff | Input tagihan vendor dan permintaan pembayaran. Tidak bisa memposting ke periode terkunci maupun mengubah CoA | — |
| **Accounting Staff — AR** | staff | Invoice pelanggan, penerimaan, tindak lanjut piutang | — |
| **Tax Officer** | staff | e-Faktur, Coretax, PPh/bupot | — |
| **Treasury / Cashier** | staff | Jurnal bank & kas, eksekusi pembayaran, petty cash | — |
| **Purchasing Manager** | manager | Menyetujui PO, mengelola harga vendor | Purchasing Staff |
| **Purchasing Staff** | staff | Membuat PO, menindaklanjuti vendor | — |
| **Sales Manager** | manager | Hak penjualan penuh termasuk harga dan diskon | Sales Admin |
| **Sales Admin / Merchandising** | staff | Sales order dan pemeliharaan master produk | — |
| **Inventory Manager** | manager | Konfigurasi gudang, valuasi, penyesuaian stok | Stock Keeper |
| **IT / System Administrator** | manager | Administrasi teknis (`base.group_system`) | — |
| **Internal Auditor** | readonly | Membaca buku besar dan laporan; tidak membuat/mengubah apa pun | — |

## Retail / Toko

| Role | Level | Ringkas | Mewarisi |
|---|---|---|---|
| **Store Manager** | manager | Menjalankan satu toko: konfigurasi POS, stok, laporan toko, persetujuan lapis pertama | Store Supervisor |
| **Store Supervisor** | supervisor | Buka/tutup sesi POS, mengawasi stock count | Kasir POS, Stock Keeper |
| **Store Staff / Kasir POS** | operator | Mengoperasikan POS. Tanpa akuntansi, tanpa konfigurasi stok | — |
| **Stock Keeper** | operator | Terima dan kirim barang, hitung stok. Tanpa akuntansi | — |
| **Area Manager** | supervisor | Mengawasi beberapa toko | Store Manager |

## Dua hal yang sengaja dibuat begini

**IT / System Administrator dipisah dari role bisnis.** Tidak ada satu pun role
di atas yang membawa `base.group_system`. Hak Settings tidak boleh didapat
sebagai efek samping dari jabatan — di `prd_levis_begbal` pernah tercatat 73 user
memegang `group_system` sekaligus.

**Area Manager = satu penugasan, bukan dua belas.** Beri role Area Manager, lalu
di tab Operating Units cukup pilih OU bertipe *Area*. Semua toko di bawahnya ikut
otomatis, dan menambah toko baru ke area itu tidak perlu menyentuh usernya lagi.

## Menyesuaikan untuk satu tenant

Role bawaan ditandai **Shipped by Platform** dan di-refresh setiap modul
di-upgrade. Kalau komposisinya perlu berbeda di satu tenant:

- **Duplikat** role-nya, lalu ubah duplikatnya — cara yang dianjurkan, karena
  role bawaan tetap menerima perbaikan dari platform; atau
- edit langsung role bawaannya. Begitu diedit, role itu ditandai **Customized**
  dan tidak akan pernah di-refresh lagi (form-nya memberi tahu). Perubahan lokal
  aman, tetapi perbaikan berikutnya dari platform tidak akan sampai.

Group yang modulnya belum terpasang di sebuah database dilewati diam-diam. Jadi
tenant tanpa POS tetap punya role Kasir POS — kosong, dan otomatis terisi saat
POS dipasang lalu modul di-upgrade.

## Yang tidak diubah oleh mesin role

Group yang diberikan manual, atau oleh modul lain (peta role Keycloak di
`custom_finance_portal_sso` menulis secara aditif), **tidak pernah dicabut** saat
role user berubah. Mesin hanya mencabut apa yang ia berikan sendiri. Yang
tercatat bisa dilihat di form user: *Granted by roles* dan *Held before roles
were applied*.
