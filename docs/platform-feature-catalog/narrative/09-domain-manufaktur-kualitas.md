---
title: Manufaktur, Kualitas & Pemeliharaan
domain: manufaktur-kualitas
---

# 9. Manufaktur, Kualitas & Pemeliharaan

{{n.domain.manufaktur-kualitas}} modul — domain terkecil di platform, dan itu
mencerminkan bauran bisnis Erajaya: distribusi dan retail, bukan manufaktur.
Kapabilitasnya tetap dibangun karena tiga alasan nyata: pemeliharaan armada
drone, kontrol kualitas penerimaan gudang, dan perbaikan aset internal.

## 9.1 Kualitas

`custom_quality_full` menyediakan quality point dan pemeriksaan, alert
Non-Conformance Report, baris inspeksi, tanda tangan, **CAPA** (Corrective and
Preventive Action), serta template uji yang dapat dipakai ulang. Ia menjadi
titik sambung bagi dua modul lain: pemeriksaan kualitas otomatis saat aset sewa
dikembalikan, dan gerbang QC pada penerimaan gudang.

## 9.2 Pemeliharaan

`custom_maintenance` melampaui modul maintenance bawaan Odoo dengan alert dari
sensor IoT, metrik **MTBF/MTTR**, penjadwalan prediktif, SLA per tim, pelacakan
suku cadang, dan biaya pemeliharaan. Untuk armada drone ARKA-AIM, ini yang
menghubungkan jam terbang dengan jadwal servis.

`custom_repairs` menangani perbaikan aset internal dan menjembatani ke equipment
serta permintaan pemeliharaan, sehingga satu unit memiliki satu riwayat, bukan
dua catatan terpisah.

## 9.3 PLM dan IoT

`custom_mrp_plm` membawa Product Lifecycle Management: alur **ECO** (Engineering
Change Order), versi Bill of Materials, dan perubahan yang dikunci persetujuan.

`custom_iot_bridge` menerima pembacaan sensor lewat webhook, menampilkannya di
dashboard, dan memicu alert saat melewati ambang batas. Ia adalah sumber data
bagi pemeliharaan prediktif di atas.

## 9.4 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
