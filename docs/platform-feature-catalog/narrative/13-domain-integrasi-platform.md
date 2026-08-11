---
title: Integrasi & Fondasi Platform
domain: integrasi-platform
---

# 13. Integrasi & Fondasi Platform

{{n.domain.integrasi-platform}} modul. Domain ini jarang terlihat pengguna
akhir, tetapi hampir setiap fitur di bab-bab sebelumnya berdiri di atasnya.

## 13.1 Fondasi

`custom_core` adalah akar dependensi hampir seluruh platform: utilitas bersama,
mixin, helper kebijakan, penyimpanan konfigurasi terenkripsi, dan **dekorator
`secure_endpoint`** yang menjaga setiap endpoint masuk.

Satu kontrak HMAC dipakai untuk kedua arah, dengan bentuk kanonik yang sama:
stempel waktu digabung dengan badan permintaan mentah, batas selisih waktu 300
detik, penjagaan pengulangan lewat Redis, dan daftar izin CIDR. Endpoint masuk
memakai `@secure_endpoint('<scope>')`; scope yang dipakai saat ini adalah `hht`,
`finance_sap`, `storefront`, `mdm`, dan `ops_alertmanager`.

`custom_adapter_framework` menangani arah keluar: registri adapter, klien HTTP
dengan **retry berjenjang dan circuit breaker**, kredensial lewat rujukan ke
parameter konfigurasi alih-alih disimpan pada record, dan log panggilan
append-only yang menyimpan **hash** badan permintaan, bukan isinya. Kesalahan
4xx diperlakukan permanen dan tidak diulang — perilaku yang membedakan adapter
yang matang dari yang membanjiri mitra dengan permintaan gagal.

> Utang teknis yang layak dicatat: empat modul (`custom_ai_bridge`,
> `custom_payment_id`, `custom_sms_id`, `custom_voip`) menulis adapternya sendiri
> alih-alih memakai kerangka ini. Itu adalah warisan, bukan preseden — integrasi
> keluar yang baru harus memakai kerangka bersama.

## 13.2 Mesin persetujuan

`custom_approval_engine` menyediakan persetujuan berjenjang generik dengan
delegasi, mode di luar kantor, dan eskalasi SLA. Ia dipakai oleh klaim biaya,
cuti, purchase order, sales order, Finance Portal, uang muka, dan perubahan
kategori produk. Membangun tujuh alur persetujuan terpisah adalah kesalahan yang
dihindari platform ini sejak awal.

## 13.3 Identitas

`authenticate_keycloak` menambahkan alur OAuth2 authorization code dengan
confidential client di atas `auth_oauth` bawaan Odoo. Ia menjadi fondasi bagi SSO
karyawan (`custom_hr_sso_keycloak`) dan SSO Finance Portal
(`custom_finance_portal_sso`).

## 13.4 Konektor ESB

`custom_esb_connector` adalah mesin integrasi ke **ESB Core dan ESB OMS**, sistem
ERP food & beverage yang dipakai EFN. Ia menyediakan adapter REST bersesi, mirror
master data, snapshot stok, dan outbox dokumen yang idempoten. Mesinnya generik;
yang khusus EFN adalah vertikal `custom_fnb_stock_ops` di Bab 14.

## 13.5 Presentasi dan kenyamanan

`custom_report_templates` menyediakan tata letak PDF faktur, penawaran, dan
purchase order dengan branding per tenant. `custom_home_console` menggantikan
halaman depan Odoo dengan kartu aplikasi terkelompok dan pencarian.

`custom_currency_nbsp` menyelesaikan masalah kecil yang berbiaya besar: Odoo
menyisipkan **non-breaking space** pada nominal mata uang, yang membuat ekspor
CSV terbaca sebagai teks rusak di Excel. Modul ini menghapusnya dan menambahkan
BOM UTF-8 pada ekspor. Setiap tim keuangan yang pernah melihat karakter "Â" di
lembar kerjanya tahu mengapa ini ada.

## 13.6 Komponen pihak ketiga

Empat modul OCA di-vendor apa adanya dan tidak diubah: **queue_job** (eksekusi
pekerjaan latar belakang berbasis basis data, dipakai enam modul dan dimuat
sebagai server-wide module), **auth_jwt**, **partner_firstname**, dan
**base_rest** — yang terakhir masih pada seri 18.0 dan ditandai tidak dapat
dipasang.

> Perlu ditegaskan: Redis di platform ini **bukan** broker pekerjaan. Ia dipakai
> untuk penjagaan replay dan cache. Antrean pekerjaan berjalan di PostgreSQL
> lewat `queue_job`. Tidak ada RabbitMQ maupun Celery, dan Kafka hanya muncul
> sebagai mock di jembatan SAP — tidak ada broker Kafka di berkas Compose mana
> pun.

## 13.7 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
