---
project: vas-pmo
title: VAS PMO — Implementation status (Rilis 1, sebagian)
status: in-progress
date: 2026-07-30
---

# Status implementasi

Dikerjakan terhadap plan `00-development-plan.md` (baseline + Revisi 2). Diuji di
`rnd_vas_pmo` pada stack docker lokal, Odoo 19.0-20260528.

## Yang SELESAI dan TERUJI

| Komponen | Bukti |
|---|---|
| `ee_gap/custom_project_portfolio` | install bersih; 20 test lolos |
| `ee_gap/custom_project_cr` | install bersih; 14 test lolos |
| `ee_gap/custom_project_notify` | install bersih; 13 test lolos |
| `ee_gap/custom_project_api` | install bersih; diuji lewat HTTP nyata |
| **Total test** | **44/44 lolos** (`--test-tags vaspmo`, wajib `--db-filter=^<db>$` karena test HttpCase memanggil route `auth='public'`) |
| Frontend `vas-pmo/` (Next.js 15) | image ter-build, container jalan, health `{"status":"up","odoo":"up"}` |
| Loop notifikasi ujung-ke-ujung | stage change → outbox → HMAC → BFF → **email nyata masuk mailpit**; WA di-skip "no phone number on record" **tanpa menjatuhkan email** |
| REST API | login 200 (+401 utk password salah & tanpa token), `/auth/me`, `/dashboard/summary`, `/tasks`, `/meta/verticals`, transisi ke Hold → `sla_clock=paused`, transisi ilegal → 422 `RULE_REJECTED` |
| Retry outbox | terbukti: baris `on_hold` mencatat 3 attempt dengan backoff saat BFF belum hidup, lalu berhenti sendiri |
| Wiring | service `vas-pmo` di `docker-compose.yml` (port 18110), env di `.env.example`, industry pack `vas_pmo` di `custom_hub_console` |

### Pemetaan 8 poin Revisi 2

| Poin | Status |
|---|---|
| 2 · Hold + Waiting User Verification | **Selesai.** `sla_clock` per stage; hold dikurangkan dari cycle time, user-wait dibukukan ke user; auto-close 5 hari kerja; reminder H+2/H+5 |
| 3 · Vertical per brand | **Selesai.** 8 vertical ter-seed, badge di semua layar, ikut ke template WA/email, record rule brand-PIC |
| 4 · Weekly Progress + sprint mingguan | **Selesai.** sprint ISO mingguan, cron roll-over + carry-over, draft otomatis Jumat 15:00, reminder & digest |
| 5 · Pisah Project/CR/Task | **Selesai.** `custom.change.request` + approval berjenjang + impact analysis + SLA respons + intake |
| 7 · Summary per BA | **Selesai** sebagai agregat (`/dashboard/ba-summary`, tanpa tabel baru) |
| 8 · Log per transaksi | **Selesai** di atas `pdp.audited.mixin` / `pdp.audit.log` yang ber-hash-chain; ditampilkan di detail task & `/vaspmo/api/logs` |
| 1 · Pola UI modern | **Selesai untuk core.** Command palette Ctrl/Cmd+K (destinasi statis + pencarian task/CR/project via `/api/search`, debounce 180 ms, navigasi ↑↓/⏎/esc), view switcher List/Board/Timeline lewat query param, optimistic UI pada perpindahan stage. Belum: shortcut inline J/K, burn-down chart |
| 6 · CMS master data | **Selesai.** 4 layar di Next.js — Vertical/brand (edit badan hukum, urutan, aktif), Stage & jam SLA (edit `sla_clock`, auto-close, wajib alasan), Aturan notifikasi (toggle WA/Email/Odoo per aturan), Pengguna & peran (read-only, nomor ter-mask). Semua perubahan tercatat sebagai `master_data_change` |

### Layar yang sudah ada di Next.js

`/login` · `/portfolio` · `/board` (+`?view=list`) · `/tasks/[id]` · `/weekly` · `/cr` ·
`/timeline` · `/logs` · `/settings/{verticals,stages,rules,users}` — semuanya diverifikasi
render dengan data nyata (13 pemeriksaan konten lolos), dan anonim ditolak middleware (307).

## Bug yang ditemukan oleh test-nya sendiri (dan sudah diperbaiki)

`_guard` di kedua controller menangkap `ValidationError` lalu mengembalikan 422 yang rapi —
**tanpa `cr.rollback()`**. Constraint model menyala saat *flush*, yaitu setelah UPDATE sudah
dikirim ke Postgres; menangkap exception dan meneruskan request berarti UPDATE itu tetap
ter-commit. Gejalanya: PATCH stage Hold → `sla_clock=running` dijawab
`422 RULE_REJECTED`, tapi stage Hold benar-benar kehilangan jam `paused`-nya — dan begitu itu
terjadi, **semua angka cycle time jadi salah** karena waktu hold berhenti dikurangkan.

Ditemukan karena dua test yang tidak berhubungan (`test_hold_pauses_clock_and_resume_returns`
dan `test_sla_cron_only_fires_while_clock_runs`) mulai gagal setelah endpoint CMS dipakai
sekali. Perbaikannya satu baris di dua tempat, plus
`custom_project_api/tests/test_admin_api.py` yang menguji hal yang sebenarnya penting: bukan
status code-nya, tapi bahwa **database tidak berubah** — dan sebaliknya, perubahan yang legal
tetap tersimpan (supaya rollback-nya tidak berlebihan).

## Yang BELUM dikerjakan

| Item | Alasan |
|---|---|
| `custom_project_jira` (sync 2 arah) | **Ditunda atas permintaan** — dikerjakan setelah core. Butuh kredensial Jira Cloud + satu project uji untuk memvalidasi loop guard |
| `custom_project_ticket_bridge` | **Ditunda atas permintaan** + menunggu OD1 (ticketing mana) |
| Shortcut inline J/K, burn-down chart | Sisa kecil dari R1 |
| Deploy VPS | Skrip siap ([`scripts/deploy-vas-pmo.sh`](../../../scripts/deploy-vas-pmo.sh)), dieksekusi oleh tim |

## Deviasi dari plan (disengaja, dengan alasan)

1. **`custom.project.stage.config` → ekstensi `project.task.type`.** Odoo sudah punya
   stage engine + kanban. Model stage paralel berarti dua implementasi kanban dan dua
   sumber kebenaran. Yang dibutuhkan plan sebenarnya adalah *perilaku yang menempel pada
   stage*, dan itu yang dipasang sebagai field baru.
2. **Approval CR native, bukan `custom_approval_engine`.** Supaya modul CR tetap bisa
   di-install & diuji tanpa menarik seluruh stack approval ke tenant ini. Seam-nya ada:
   `_cr_external_approval_hook()`.
3. **Tidak ada model log baru.** Platform sudah punya audit append-only ber-hash-chain
   (`pdp.audit_log_v` + `pdp.audited.mixin`). Dipakai apa adanya — hemat effort dan
   log-nya jadi *tamper-evident*.
4. **`custom_blocked_by_ids` dibatalkan.** `project.task.depend_on_ids` sudah native sejak
   Odoo 17 dan labelnya sama ("Blocked By"); field kedua hanya jadi duplikasi.
5. **CSS biasa, bukan Tailwind.** UI-nya berasal dari mockup yang sudah didesain; menulis
   ulang jadi utility class kehilangan detail tanpa manfaat.
6. **View standalone, bukan inherit view core.** Satu xmlid core yang berubah adalah
   penyebab paling umum modul gagal install di rilis Odoo baru.

## Temuan Odoo 19 (baru, belum ada di catatan platform)

1. **`res.groups.category_id` dihapus** → pakai `privilege_id`
   (`custom_core.res_groups_privilege_custom_platform`). Ini yang membuat install pertama
   gagal. Catatan: `ee_gap/custom_retail_import/security/security.xml` masih memakai
   `category_id` — kemungkinan modul itu juga gagal install di Odoo 19, perlu dicek.
2. **`res.groups.user_ids` hanya anggota langsung.** Yang lewat `implied_ids` ada di
   **`all_user_ids`**. Agregat per-role wajib pakai yang kedua.
3. **`res.partner.mobile` dilebur ke `phone`.**
4. **`name_get()` sudah tidak dipakai** → `_compute_display_name`.
5. **Odoo mengisi `user_ids` task baru dengan pembuatnya**, jadi skenario "tanpa PIC" harus
   mengosongkan `user_ids` secara eksplisit.
6. **Next.js standalone bind ke `$HOSTNAME`** (= container id di docker), jadi
   `HOSTNAME=0.0.0.0` wajib atau healthcheck 127.0.0.1 ditolak.

## Catatan deployment yang penting

`DBFILTER=^.*$` di stack dev cocok ke banyak DB, sehingga Odoo tidak bisa memilih satu DB
untuk route `auth='public'` → semua endpoint `/vaspmo/api/*` menjawab 404. Ini **bukan bug
kode**: produksi harus memakai dbfilter per-host (pola `ODOO_TENANT_HOST` + `PROXY_MODE`
seperti storefront), atau satu proses Odoo dengan `--db-filter=^<db>$`.

Untuk verifikasi lokal dipakai cara kedua: listener single-DB di port 18169 dalam container
Odoo, dan `VAS_PMO_ODOO_BASE_URL=http://odoo:18169` di `.env`. **Sebelum deploy, kembalikan
ke `https://nginx` + set `VAS_PMO_TENANT_HOST`.**

## Langkah berikutnya

1. Putuskan target VPS + host/domain, lalu deploy (rebuild image, rotasi
   `VAS_PMO_HMAC_SECRET` & `VAS_PMO_JWT_SECRET`, dbfilter per-host).
2. Isi kredensial WaHub, lalu uji satu pesan WA nyata dengan
   `NOTIFICATION_TEST_MODE=true` ke satu nomor penguji.
3. Konfirmasi daftar badan hukum per brand → lengkapi `legal_entity`.
4. Putuskan OD1 (ticketing), lalu kerjakan bridge.
5. Kredensial Jira Cloud + satu project uji → kerjakan `custom_project_jira`.
