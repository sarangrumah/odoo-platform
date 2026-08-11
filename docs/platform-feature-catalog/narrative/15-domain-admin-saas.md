---
title: Administrasi Platform & Odoo-as-a-Service
domain: admin-saas
---

# 15. Administrasi Platform & Odoo-as-a-Service

Bab ini menjawab kebutuhan kedua dari dokumen ini: bagaimana platform ini
dikelola sebagai layanan, siapa yang bisa melakukan apa, dan — bagian yang paling
perlu dibaca — **apa yang belum dibangun**.

Bab ini memakai konvensi yang sama dengan dokumen arsitektur internal:
setiap pernyataan ditandai sebagai **KONDISI SAAT INI (NOW)** atau **SASARAN
(TARGET)**. Tidak ada yang dideskripsikan sebagai ada sampai ia benar-benar ada.
Versi sebelumnya dari dokumen arsitektur itu pernah menggambarkan Kafka, Postgres
warm-standby, dan struktur direktori infra yang tidak pernah dibangun, dan
perencanaan sempat berangkat dari asumsi tersebut. Bab ini tidak mengulanginya.

## 15.1 Mengapa multi-tenant

Satu basis kode Odoo 19 melayani {{n.tenants}} brand terdaftar. Setiap tenant
memiliki **basis datanya sendiri** di dalam satu klaster PostgreSQL — bukan satu
basis data bersama dengan kolom perusahaan. Pilihan ini menentukan hampir semua
hal lain di bab ini:

- Data satu brand tidak dapat bocor ke brand lain lewat kesalahan kueri, karena
  tidak berada dalam basis data yang sama.
- Sebuah tenant dapat dicadangkan, dipulihkan, atau dihentikan sendiri tanpa
  menyentuh yang lain.
- Sebaliknya, **pemutakhiran modul bersama menyentuh semua basis data** dan harus
  dijalankan pada semuanya. Ini sumber insiden operasional yang nyata dan
  ditangani sebagai prosedur, bukan sebagai hal yang diingat.

## 15.2 Peta lapisan kendali

**NOW.** Enam lapisan, dari luar ke dalam:

**Pintu depan** — Caddy dengan Web Application Firewall berbasis Coraza dan OWASP
Core Rule Set, TLS, penekanan header build, dan pembatasan laju per IP. Nama
sub-domain tenant diekstrak lewat ekspresi reguler pada header dan diteruskan
sebagai `X-Tenant-Slug`, yang dipakai Odoo sebagai `dbfilter`. Satu instans
melayani banyak tenant tanpa satu pun melihat yang lain.

**Gerbang login** — aplikasi `/signin` tersendiri menggantikan pemilih basis data
bawaan Odoo, yang secara bawaan menampilkan daftar seluruh basis data kepada
siapa pun yang membuka halamannya. Daftar tenant yang boleh muncul dikurasi
tangan dalam sebuah berkas konfigurasi dengan penanda publik atau internal.

**Konsol admin** — sebuah aplikasi satu halaman (React) dengan lapisan
backend-for-frontend yang menandatangani permintaan ber-HMAC ke orkestrator.
Dua belas halaman: Dashboard, Onboarding Pipeline, Tenants & Verticals, VPS
Console, Module Deployments, Dev Cycles, Services Monitoring, Audit Trail,
Documents, **Users & RBAC**, dan Cost & Licenses.

**Orkestrator** — layanan FastAPI yang menjadi mesin siklus hidup tenant. Setiap
endpoint `/v1/*` menuntut tanda tangan HMAC-SHA256 dengan jendela replay lima
menit. Ia menjalankan penjadwal cadangan, enkripsi kunci data dengan skema
envelope, dan bootstrap VPS jarak jauh lewat SSH.

**Registry** — sebuah skema PostgreSQL tersendiri, `tenant_registry`, berisi empat
tabel: `tenants`, `action_log`, `backups`, dan `coretax_usage`. `action_log`
adalah **log append-only berantai-hash** — setiap baris menyimpan hash baris
sebelumnya, dan sebuah trigger menghitungnya saat penyisipan. Hak akses dipisah:
orkestrator boleh menulis, peran pembaca hanya boleh membaca.

**Di dalam Odoo** — empat modul lapisan kendali, yang juga merupakan isi domain
ini: konsol hub terpadu, super admin, infrastruktur tenant, dan perjalanan
onboarding. Ditambah tiga modul operasi internal: analisis kesenjangan BRD,
pelacakan siklus pengembangan, dan monitor kapasitas.

![Lapisan kendali: siapa memanggil siapa](svg/D03-control-plane.svg)

## 15.3 Siklus hidup tenant

**NOW.** Enam fase, masing-masing dengan prosedur tertulis dan perintah yang
dapat dijalankan:

**Onboarding** — `custom_onboarding_journey` menjalankan state machine intake →
BRD → Go/No-Go → provisioning → handover, dengan transisi tahap yang **tidak
dapat diubah setelah tercatat** dan sinkronisasi dua arah ke modul Project.
Formulir intake publik tersedia lewat controller tersendiri. Prosedur manualnya
ada di `docs/sops/tenant-onboarding.md`.

**Provisioning** — orkestrator membuat basis data lewat CLI Odoo di dalam
kontainer manajemen, bukan lewat endpoint pembuatan basis data bawaan. Alasannya
tercatat sebagai komentar di berkas Compose: endpoint bawaan mengembalikan HTTP
200 meskipun pembuatan gagal. Perintah operator: `make tenant-provision`.

**Operasi** — deploy modul per tenant lewat halaman Module Deployments, dengan
peta vertikal → modul yang didefinisikan di dalam kode konsol hub, bukan di
manifest.

**Cadangan dan pemulihan** — `make tenant-backup`, `tenant-list-backups`,
`tenant-restore`. Penjadwal per tenant berjalan di orkestrator; sebuah cron host
terpisah menjalankan dump seluruh basis data pukul 02.30 dengan rotasi harian,
mingguan, dan bulanan, ditambah pekerjaan verifikasi pukul 07.05 yang sengaja
dipisah agar kegagalan verifikasi tidak tertutupi oleh keberhasilan dump.

**Suspend dan resume** — `make tenant-suspend` dan `tenant-resume` menghentikan
akses tanpa menghapus data.

**Offboarding** — `make tenant-archive`, dengan prosedur di
`docs/sops/tenant-offboarding.md`.

Integritas seluruh jejak tindakan dapat diperiksa kapan saja dengan
`make tenant-verify-chain`, yang menelusuri rantai hash `action_log` dan gagal
bila ada mata rantai yang putus.

## 15.4 Pengelolaan pengguna dan hak akses

**NOW.** Tiga lapisan identitas berjalan bersamaan:

**Di dalam Odoo**, hak akses memakai model *privilege* Odoo 19. Platform
mendefinisikan kategori dan privilege `custom_platform` sendiri, dan setiap modul
vertikal maupun kepatuhan menggantungkan grup keamanannya pada kategori itu.

> Jebakan yang penting diketahui saat memberi hak: pada Odoo 19, satu dropdown
> privilege memetakan ke **satu grup**. Memberi seseorang akses lewat dropdown
> tidak menambahkan grup — ia menggantikan. Pencabutan hak administrator harus
> mencabut pasangan grup yang benar lewat ORM, bukan lewat layar pengguna.

**Lewat SSO**, tiga modul menghubungkan Odoo ke Keycloak:
`authenticate_keycloak` menyediakan alur OAuth2, `custom_hr_sso_keycloak`
menyinkronkan data karyawan dari klaim token, dan `custom_finance_portal_sso`
memetakan peran ke grup serta memisahkan karyawan dari vendor.

**Di konsol admin**, halaman Users & RBAC menampilkan pengguna lintas tenant
lewat JSON-RPC ke Odoo.

## 15.5 Isolasi dan keamanan

**NOW.**

- **Isolasi data**: satu basis data per tenant dalam satu klaster.
- **Antar layanan**: satu kontrak HMAC untuk semua arah, dengan penjagaan
  pengulangan berbasis Redis dan daftar izin CIDR.
- **Pintu masuk**: WAF Coraza dengan OWASP CRS di Caddy, pembatasan laju per IP,
  dan penguncian origin agar hanya lewat CDN.
- **Jejak audit**: `action_log` berantai-hash di sisi platform, dan
  `pdp.audit_log` berantai-hash di dalam setiap basis data tenant — yang terakhir
  dilindungi trigger PostgreSQL yang menolak UPDATE dan DELETE.
- **Kredensial**: kunci data dienkripsi dengan skema envelope di orkestrator;
  kredensial VPS disimpan sebagai rujukan vault, tidak pernah sebagai nilai di
  dalam Odoo; kredensial adapter disimpan sebagai rujukan ke parameter
  konfigurasi terenkripsi.

Prosedur pemulihan tersedia sebagai 13 runbook, termasuk pemulihan bencana,
pemulihan data tenant, Postgres mati, Odoo kehabisan memori, dan pengerasan pintu
depan.

## 15.6 Observability

**NOW.** Overlay observability menyediakan Prometheus, Alertmanager, Loki,
Promtail, Grafana, exporter untuk node/Postgres/Redis/Odoo, dan sebuah layanan
prakiraan kapasitas. Di dalam Odoo, `custom_ops_monitor` menampilkan kesehatan
server dan prakiraan kapasitas, serta menerima alert lewat endpoint ber-HMAC.

Perlu ditegaskan: ini **metrik operasional, bukan business intelligence**.
Pelaporan bisnis berjalan di dalam Odoo lewat mesin laporan akuntansi.

## 15.7 Analisis kesenjangan — Kondisi Saat Ini vs Sasaran

Daftar lengkap kesenjangan yang tercatat: {{n.gaps}} butir, {{n.gaps.high}} di
antaranya berprioritas tinggi. Ringkasannya lebih dulu, lalu satu blok rincian
per butir. Setiap butir menyertakan **rujukan berkas** yang dapat dibuka sendiri
untuk memeriksa klaimnya — seluruhnya sudah diverifikasi ulang terhadap
repositori saat dokumen ini dihasilkan.

{{TABEL_KESENJANGAN}}

## 15.8 Peta jalan yang diusulkan

Pengelompokan di bawah ini mengikuti kolom Horizon pada tabel di atas, dan
diurutkan berdasarkan risiko, bukan kemudahan.

**0–3 bulan — tutup risiko kehilangan data lebih dulu.** WAL archiving dan
backup off-site yang benar-benar terpisah (GAP-BACKUP-01, GAP-BACKUP-02) adalah
dua butir prioritas tinggi yang dapat diselesaikan tanpa perubahan arsitektur.
Bersamaan dengan itu, sambungkan dua endpoint konsol yang masih mengembalikan
data contoh, pastikan mode demo mati di lingkungan produksi, dan lengkapi
referensi endpoint konsol admin.

**3–6 bulan — kurangi luas serangan dan tutup utang pengetahuan.** Ganti akses
soket Docker penuh pada orkestrator dengan perantara berhak terbatas
(GAP-SEC-01), dan naikkan status dokumen pengetahuan modul yang menghadap klien
dari draft ke reviewed (GAP-KNOW-01).

**6–12 bulan — pisahkan lapisan.** Pemisahan host basis data, replika baca untuk
pelaporan, dan host redundan (GAP-HA-01) adalah pekerjaan arsitektur, dan
membuka jalan bagi permukaan business intelligence (GAP-BI-01) yang saat ini
tidak ada sama sekali.

Empat kendala teknis yang harus dihormati saat pemisahan itu dikerjakan, dan
sebaiknya diperiksa ulang sebelum perencanaan dimulai:

1. Instans Odoo utama dan instans manajemen **harus berbagi satu klaster
   PostgreSQL dan satu mount filestore yang sama**. Memisahkannya membuat aset
   gagal dimuat.
2. Nama host basis data masih ditulis langsung di berkas Compose untuk layanan
   Odoo; tidak ada variabel environment untuk menggantinya.
3. Jalur bootstrap VPS jarak jauh mengkloning tumpukan monolit per tenant — ia
   tidak memisahkan lapisan.
4. Model kapasitas mengasumsikan satu mesin: variabel CPU, RAM, dan disk di
   berkas environment bersifat tunggal.

## 15.9 Daftar modul

{{TABEL_MODUL}}

{{KHUSUS_BRAND}}
