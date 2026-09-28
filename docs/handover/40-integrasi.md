# Handover — Integrasi: PPOB, VAS PMO, ESB/EFN, Denso

## 1. Ringkasan

Empat jalur integrasi non-retail. Setiap angka dan tanggal menyebut sumbernya dalam tanda kurung: nama file memory, path
repo, nomor PR, atau nama basis data. Status diverifikasi terhadap runtime **28-Sep-2026** (`pg_database` +
`ir_module_module` pada `odoo19-platform-postgres`, plus probe TCP ke node PPOB).

| Jalur | Modul | DB | Status jujur |
| --- | --- | --- | --- |
| PPOB / PPS | 12 × `verticals/custom_ppob_*` | `ppob` di VPS 192.168.3.185, `rnd_ppob` di host ini | Node terbangun & terverifikasi 8-Sep-2026; **nol data master**, belum ada transaksi |
| VAS PMO | 4 × `ee_gap/custom_project_*` + app Next.js | `rnd_vas_pmo` | Rilis 1 sebagian; **hanya `admin`** punya role, password DB masih default |
| ESB Core / EFN | `ee_gap/custom_esb_connector` + `verticals/custom_fnb_stock_ops` | `rnd_esb` (disposable) | Build selesai, 158 test hijau atas fixture; **diblokir kredensial ESB** |
| MDM product-master | `ee_gap/custom_retail_import_api` | `tst_mdm_levis` (UAT) | UAT hidup; **produksi `/api/mdm` masih `404 NOT_DEPLOYED`** |
| Denso BHT / barcode | `custom_wms_docs`, `custom_barcode` | `demo_wms`, `rnd_wms` | Perangkat perlu konfigurasi simbologi — bukan bug software |

> Tidak satu pun dari jalur ini berada di jalur kritis produksi Levi's atau ARKA-AIM hari ini.
> Jangan menjualnya sebagai kapabilitas yang sudah berjalan tanpa menyebut statusnya.

## 2. PPOB / PPS

### 2.1 Dua belas modul

Semua di tier `verticals/`, versi `19.0.1.x.0` (`addons/verticals/custom_ppob_*/__manifest__.py`).

| Modul | Fungsi |
| --- | --- |
| `custom_ppob_core` | Fondasi: partner mitra/provider, 19 akun PPOB via `hooks.py`, jurnal PSAL/PWAL/PPRV/PSUM, tarif PPN |
| `custom_ppob_wallet` | Wallet prepaid mitra, primitif debit/kredit atomik row-locked + ledger GL berpasangan |
| `custom_ppob_provider` | Master provider, inventori bucket atomik, mapping SKU |
| `custom_ppob_sale` | State machine transaksi PPOB + wallet & bucket atomik |
| `custom_ppob_va` | Virtual account mitra + top-up wallet (callback H2H bank) |
| `custom_ppob_commission` | Komisi dua arah: provider→kita dan kita→mitra |
| `custom_ppob_rollup` | Agregasi transaksi sukses menjadi `sale.order` harian |
| `custom_ppob_sla` | Target throughput + latensi deklaratif per provider/kelas |
| `custom_ppob_pps_gateway` | Memaparkan API H2H PPS/EVShop dari Odoo untuk ERASPACE POS |
| `custom_ppob_eraspace_bridge` | Mirror feed POS + H2H ERASPACE ke Finance/Accounting |
| `custom_ppob_biller_digiflazz` | Adapter H2H Digiflazz (topup prepaid, inquiry postpaid) |
| `custom_ppob_oracle_bridge` | Jembatan ke pipeline Oracle EVShop lama — **opt-in** |

### 2.2 Node VPS terpisah

Diputuskan 8-Sep-2026: PPOB/PPS pindah ke VPS sendiri di **192.168.3.185**, membawa clone repo `odoo-platform` utuh. **VPS
itu bukan mesin kosong** — di sana sudah jalan nginx :80 → Next.js :3000, **Odoo 18 CE** :8069/8071/8072, FastAPI "OdooHub
API" :8080, Postgres :5433, FTP :21; keputusan user **ambil alih**, bukan koeksistensi. **SSH di port 2221, bukan 22.** Host
remote `odoo-fico.local`, Ubuntu 24.04, 4 vCPU / 15 GiB / 96 GB; repo dikirim lewat `git bundle` (origin/main `74dc1ab`)
karena remote tak punya deploy key GitHub. Stack lama `odoohub` (7 container, ada env **prod**) diarsipkan ke
`/var/backups/pre-ppob-takeover/20260908_060416` (dump 47 M + bind-mount, total 102 M) lalu di-stop + `restart=no`;
**container & volume UTUH — rollback = `docker start`**. `odoohub` adalah **pendahulu** `odoo-platform`, bukan produk lain;
`/opt/odoohub` di host ini sudah dihapus sengaja dan dua systemd unit-nya di-disable 17-Sep-2026 setelah restart-looping
2.099.895 kali (`ppob-node-vps-185-takeover`, `odoohub-predecessor`).

Hasil DB `ppob` per 8-Sep: 11 modul `custom_ppob_*` **installed** (`oracle_bridge` sengaja uninstalled),
`chart_template=id`, currency **IDR**, 137 akun, 19 baris `custom_ppob_account_mapping`, 12 jurnal, 29 cron aktif; URL
`http://192.168.3.185:8069/`, admin awal bawaan installer yang **HARUS diganti**. Probe 28-Sep-2026: port 8069 dan 2221 masih
OPEN. Kit provisioning **sudah tracked di git** — `deploy/ppob-node/` = `takeover.sh` (dry-run default, butuh
`CONFIRM=yes-take-over`, **tidak pernah rm/dropdb**), `bootstrap.sh`, `docker-compose.ppob.yml`, `install-ppob.sh`,
`.env.ppob.example`, `README.md`. **Node ini TIDAK masuk cron backup 02:30 host .140** — perlu backup sendiri
(`ppob-node-vps-185-takeover`, `no-automated-tenant-db-backups`).

### 2.3 Jebakan yang sudah dibayar

- **PPOB tidak bisa dipilah dari monorepo.** Closure dependensi = **23 modul custom** di 4 keluarga:
  `verticals/custom_ppob_*` (12), `core/` (custom_core, custom_adapter_framework), `ee_gap/` (custom_accounting_full,
  custom_accounting_reports, custom_hr_payroll_id, l10n_id_psak_custom), `compliance/` (custom_coretax,
  custom_coretax_bupot, custom_pph_witholding, custom_pdp_core, custom_pdp_audit). Clone repo penuh, pasang modul PPOB saja
  — konsekuensinya node ikut siklus rilis addon bersama (`ppob-node-vps-185-takeover`, `shared-addon-version-bump-drift`).
- **URUTAN INSTALL WAJIB: `-i base` → set IDR → `-i l10n_id` → modul PPOB.** Di DB kosong tanpa CoA,
  `custom_ppob_core/hooks.py` membuat 19 akun sendiri (id 1–19), lalu `account` menjalankan `_auto_install_template` yang
  meng-`unlink()` semua akun placeholder → `ForeignKeyViolation` pada `custom_ppob_account_mapping_account_id_fkey`
  (`rnd-ppob-db-setup`).
- Dua jebakan compose: `ports:` **HARUS** pakai tag `!override` (tanpa itu compose menggabung daftar port, `127.0.0.1:8069`
  dari base ikut terbawa → "address already in use"), dan `DBFILTER: ${DBFILTER:-^ppob$$}` memang sampai ke container
  sebagai `^ppob$` walau `docker compose config` menampilkan `^ppob$$`. Dua bug kit yang diperbaiki: `chown` filestore ke
  **100:101** (image `odoo:19.0` jalan sebagai uid 100), dan guard chart_template harus menolak `generic_coa`/kosong karena
  Odoo 19 memakai kode negara **`id`** (`ppob-node-vps-185-takeover`).

### 2.4 `rnd_ppob` — jangan dipakai untuk demo

Per 13-Aug-2026 `rnd_ppob` (94 MB) adalah **kerangka kosong, BUKAN lingkungan demo**: skema lengkap (70 akun, 19 mapping,
jurnal PSAL/PWAL/PPRV/PSUM, 5 tarif PPN, 2 kelas produk, 4 grup, 7 cron) tetapi **0 provider / produk / tier / mitra /
wallet / VA / transaksi**, 1 user. **Dua cacat PERMANEN:** currency company **USD** dan chart template **`generic_coa`** —
per 8-Sep sudah ada 3 `account.move` (2 posted), jadi `try_loading('id', ...)` tidak lagi aman dan currency tidak bisa
diubah. Untuk demo/UAT dengan pajak Indonesia yang benar: **bikin DB baru** lewat `deploy/ppob-node/install-ppob.sh`. Per
8-Sep stack accounting penuh dipasang di `rnd_ppob` (134 modul installed), termasuk `custom_finance_portal` — satu-satunya
DB di host ini yang memasangnya (28-Sep-2026). Tiga cron Oracle bridge menyala tiap menit tanpa koneksi Oracle, jadi
**jangan pasang modul itu kecuali dipakai**; `oracle_bridge` butuh python `oracledb` (3.4.0 sudah di
`/opt/odoo-platform/odoo/requirements.txt`) (`rnd-ppob-db-setup`, `ppob-node-vps-185-takeover`).

### 2.5 Enam gap yang tercatat jujur di dokumen klien

`docs/projects/ppob-implementation/README.md` mencantumkannya terbuka — jangan disembunyikan:

| Gap | Isi |
| --- | --- |
| G1 | API wallet sinkron (`hold`/`commit`/`release`/`credit`/`balance`) belum ada; wallet hanya punya primitif internal tanpa controller |
| G2 | `custom_ppob_eraspace_bridge` masih berpola 2-feed (POS + H2H) dari konsep lama |
| G3 | Nol test otomatis pada `custom_ppob_core`, `_wallet`, `_commission`, `_rollup` |
| G4 | Jalur prepaid Digiflazz tak punya `inquiry()` maupun `status()` — reaper tak bisa auto-resolusi |
| G5 | Gateway PPS mendokumentasikan anti-replay + kesegaran waktu, tetapi controller hanya menegakkan IP allowlist + tanda tangan + idempotensi DB; `max_clock_skew_s` tidak pernah dibaca |
| G6 | Tidak ada skrip konfigurasi tenant PPOB di `scripts/tenants/` — go-live belum reproducible |

Dua batasan yang **diwarisi, bukan cacat implementasi**: **MD5** pada kontrak gateway PPS (terisolasi di satu berkas,
dikompensasi IP allowlist + rahasia per mitra + idempotensi DB) dan **PPN diakui pada faktur ringkas harian**, bukan per
transaksi.

### 2.6 Arah program dan paket dokumen

**Existing (terkoreksi 23-Jul-2026):** mitra prepaid bertransaksi **langsung ke H2H switcher**; **ERASPACE POS di luar jalur
transaksi PPOB**; saldo mitra dikelola aplikasi **Azecs**. **Fase 1** Odoo menggantikan Azecs sebagai pemegang saldo (wallet
authoritative, atomic) sekaligus mirror ledger → **sejak Fase 1 Odoo sudah di jalur kritis penjualan**. **Fase 2** Odoo
menggantikan H2H sebagai transaction engine. **Fase 3** konsolidasi penuh (VA top-up, katalog master, komisi/PPh)
(`docs/projects/ppob/ppob-eraspace-h2h-architecture.md`, `docs/projects/ppob/ppob-eraspace-odoo-target-architecture.md`).

`docs/projects/ppob-implementation/` — 10 dokumen (00 PID … 09 Rebasing), 80 kebutuhan BR-xx, 25 acceptance test, 12
keputusan arsitektur. Estimasi tanpa PM: Greenfield ≈ **538 md** / 26 minggu, Brownfield ≈ **243 md** / 13 minggu, PPS tiga
fase ≈ **233 md** / 23 minggu. Dokumen 07 memetakan **107 kebutuhan** klien *Revamp Evshop* (≈497 md penuh / ≈235 md
prioritas); dokumen 09 me-rebase itu menjadi **178 md / 14 minggu** untuk delivery AI-assisted; terakhir diverifikasi
terhadap repo **2026-08-11**. `docs/projects/pps-odoo-hub/` — BRD (15 bab, 26 tabel, **142 kebutuhan** bernomor), TSD (11
bab, 25 tabel), UAT Script (9 lembar, **184 kasus uji**: 107 positif / 77 negatif), dibangun ulang dengan `build_brd.py`,
`build_tsd.py`, `build_uat.py`.

## 3. VAS PMO

Monitoring pekerjaan tim **Product Owner Value-Added Services**: Odoo 19 CE sebagai engine project & task, UI Next.js 15
headless (`docs/projects/vas-pmo/00-development-plan.md`). Empat modul `ee_gap/custom_project_{portfolio,cr,notify,api}` —
pasang `custom_project_api`, ia menarik sisanya; semua `installed` di `rnd_vas_pmo` (portfolio 19.0.1.1.0, tiga lainnya
19.0.1.0.0, 28-Sep-2026).

**Topologi.** `vas-pmo/` Next.js BFF → container `odoo19-platform-vas-pmo`, host port **18110** (LAN only), **Up 8 weeks
(healthy)** per 28-Sep-2026; URL publik **https://103.130.240.24/vaspmo** lewat Caddy karena box ini ber-IP privat di
belakang NAT dan hanya 80/443 di-forward. Route adalah `handle /vaspmo*` (**BUKAN** `handle_path`) + `basePath: "/vaspmo"`;
tiga hal mengikuti prefix itu: healthcheck compose (hati-hati — service storefront punya baris healthcheck byte-identik),
`custom_project_notify.bff_url`, dan `NextResponse.redirect` di `src/middleware.ts` yang **tidak** menambah basePath
sendiri. **`odoo-vaspmo`** adalah klon service `odoo` dengan `DBFILTER=^rnd_vas_pmo$` tanpa port publik — dibutuhkan karena
`odoo` bersama jalan `DBFILTER=^.*$` sehingga Odoo tidak bisa memilih DB untuk rute `auth='public'` `/vaspmo/api/*` dan
menjawab **404**; me-restart odoo tidak memperbaikinya, itu hanya mendaftarkan controller (`vas-pmo-deploy-rnd`).

**Status.** **44/44 test lolos** (`--test-tags vaspmo`): portfolio 20, cr 14, notify 13, api lewat HTTP nyata. Loop
notifikasi ujung-ke-ujung terbukti (stage change → outbox → HMAC → BFF → **email nyata masuk mailpit**; WA di-skip "no phone
number on record" **tanpa menjatuhkan email**), retry outbox terbukti. Delapan poin Revisi 2 **Selesai** kecuali poin 1 yang
selesai "untuk core" — belum ada shortcut inline J/K dan burn-down chart
(`docs/projects/vas-pmo/10-implementation-status.md`).

**Tiga jebakan yang mahal.** (1) `_guard` di kedua controller menangkap `ValidationError` lalu mengembalikan 422 rapi
**tanpa `cr.rollback()`**; constraint menyala saat *flush*, setelah UPDATE sudah dikirim ke Postgres, jadi UPDATE itu tetap
ter-commit — stage Hold kehilangan jam `paused`-nya dan **semua angka cycle time jadi salah**. Testnya kini menguji
**database tidak berubah**, bukan status code. (2) **Stage ter-seed menjadi personal stage**: `project.task.type.user_id`
default ke `self.env.uid` dan `project.task_type_visibility_rule` adalah rule **global** (`user_id in (False, user.id)`) —
global berarti AND, jadi tidak ada grup yang bisa meng-override; ketujuh stage berakhir dimiliki user yang memasang dan
board hilang dari seluruh tim. Diperbaiki di `custom_project_portfolio` 19.0.1.0.1: `user_id=False` eksplisit +
`_vaspmo_make_stages_shared()` dari data file **non-noupdate** (record stage ber-`noupdate="1"`, jadi upgrade saja tidak
memperbaiki apa pun). (3) **Test butuh `--workers 0`** karena `/opt` jalan prefork dan `HttpCase.setUpClass` membaca
`server.httpd` yang tidak dimiliki `PreforkServer`; dan `scripts/deploy-vas-pmo.sh --with-tests` mem-pipe ke `tail -5` yang
**menyembunyikan baris verdict** (`vas-pmo-deploy-rnd`).

**Belum selesai.** Akun pengguna nyata (hanya `admin` yang memegang `VAS PMO / Administrator`, password DB masih default),
reverse proxy di 443, kredensial WaHub, `legal_entity` per brand, modul Jira dan ticket-bridge. Perbaikan stage + blok
`odoo-vaspmo` **uncommitted** di `/home` branch `feat/vas-pmo`; keputusan **OD1** (ticketing mana yang jadi sumber tiket)
belum dijawab dan tidak memblokir Fase 1–4 (`vas-pmo-deploy-rnd`).

## 4. ESB Core API & EFN

### 4.1 Cara membaca spesifikasinya, dan tiga keluarga base URL

Dokumentasi di `https://developers.esb.co.id/esb-core/` adalah **shell apiDoc kosong**. Spesifikasi nyata ada di
`https://developers.esb.co.id/esb-core/api_data.js` (~4 MB JSON, **363 endpoint / 41 grup**) + `api_project.js`. **Fetch dan
parse itu, jangan WebFetch halamannya.** Trik sama berlaku untuk portal saudaranya (`esb-oms`, `eso-fs`, `eso-qs`, `loop`) —
tetapi hanya `esb-oms` merespons. Salinan distilasi di `docs/integrations/esb-core-api.md`, spesifikasi verbatim di
`docs/integrations/esb/{esb-core,esb-oms}.apidoc.json`. Satu "base_url" tunggal **salah** — butuh 3 konfigurasi adapter
(`esb-core-api`):

| Keluarga | Prod | Staging |
| --- | --- | --- |
| Core `/auth`, `/inventory/*`, `/purchase/*`, `/product`, `/report/*` | `services.esb.co.id/core` | `stg7.esb.co.id/core-stg` (INT: `core-int`) |
| `corev1/*` (Get Product, GR inquiry, sales-information, daily material usage) | `core-api.esb.co.id` | `stg7.esb.co.id/api-fnb-backend/web` |
| `external/general/*` (OMS sales-head, sales-menu) | `esbcore.co.id` | `int-erp.esb.co.id` |

### 4.2 `status:"fail"` pada HTTP 200

**Envelope respons di SETIAP endpoint:** `{path, timestamp, status:"ok"|"fail", code, message, result, errors[]}`.
`EC03100000` OK · `EC03100001` Unauthorized/Invalid Token · `EC03100032` bad credentials. **HTTP 200 dengan `status:"fail"`
itu NORMAL — jangan pernah percaya kode HTTP saja.** Pagination: query `page`/`limit` (default 20, max **100** pada
stock-movement) dengan `result.count/next/prev`; OMS `external/general/*` justru memakai header `X-Pagination-*`.

Auth: `POST /auth/login` → `result.accessToken` (kadaluarsa **1 jam**) + `result.refreshToken` (**24 jam**); `GET
/auth/refresh` dengan `Authorization: Bearer {refreshToken}`. **Static API key bisa diterbitkan PIC ESB — lebih disukai**,
menghapus manajemen sesi sepenuhnya. **Gotcha terdokumentasi:** *"A successful API login will log you out of any existing
ESB Core session using the same credentials, vice versa."* Worker paralel yang masing-masing login akan saling menendang —
pakai satu user API khusus, satu baris sesi ter-cache, dan lock baris `FOR UPDATE` di sekitar login/refresh.

**Dua gap struktural yang harus didesain di sekelilingnya:** (1) tidak ada endpoint bulk "stock on hand" — snapshot harus
diturunkan dari `qtyBalance` terakhir per (branch, location, productDetailID) di jendela `/report/stock-movement`; (2)
**tidak ada header idempotency-key pada POST mana pun** — mitigasinya menstempel kunci hasil generate ke free-text
`additionalInfo` lalu memeriksa endpoint Index untuk kunci itu sebelum membuat. Pada `POST /inventory/item-journal`, **`qty`
adalah delta bertanda, bukan kuantitas hasil hitung**; `locationID` wajib bertipe warehouse atau kitchen; status 1 New / 2
Rejected / 3 Authorized / 38 Waiting for Approval; lalu `PATCH /inventory/item-journal/{num}/authorize`. Sebagian endpoint
bertanda **"(Piloting)"** — akses per company, bentuknya bisa berubah tanpa pemberitahuan (`esb-core-api`).

### 4.3 Proyek EFN (Erajaya F&B)

Greenfield: per 21-Jul-2026 **tidak ada satu pun kode ESB/EFN di odoo-platform**. **Keputusan user:** ESB Core adalah
**sumber kebenaran untuk stok**; Odoo memirror master + stok ESB, menjalankan intelijensinya, dan mendorong hasilnya balik
sebagai dokumen ESB native — Odoo **tidak pernah** memegang `qty_available` otoritatif untuk outlet EFN. Opname dihitung di
Odoo lalu di-push sebagai Item Journal (+ authorize); output replenishment **keempatnya** (Purchase Request, Goods Transfer
Request, Purchase Order) dengan gerbang **draft-di-Odoo → user Approve → push** (`esb-odoo-efn-integration`).

**`ee_gap/custom_esb_connector` 19.0.0.1.0** — `EsbCoreAdapter(BaseAdapter)` di atas `custom_adapter_framework`,
`custom.esb.session` (rotasi token di bawah lock `FOR UPDATE`), mirror master
(`custom.esb.branch/.location/.purpose/.document.template/.product.detail`) + `x_esb_*` di `product.product`,
`custom.esb.stock.snapshot`, `custom.esb.outbox` (queue_job + idempotensi via `additionalInfo`); **70 test hijau** terhadap
fixture, tanpa kredensial ESB. **`verticals/custom_fnb_stock_ops` 19.0.0.1.0** — opname di atas `custom_wms_cycle_count`
(sesi ber-scope branch+location ESB, expected dari snapshot, close → **SATU** item journal, **tanpa `stock.move` Odoo**),
histori demand dari material-usage OMS, forecast (`seasonal_dow` default + `weighted_ma` + `moving_average`, walk-forward
MAPE, **tanpa ML**), rule replenishment → proposal draft → **Approve manusia adalah push** → PR/GTR/PO; **86 test hijau**,
**158 test** di ketiga modul pada `rnd_esb` (48 MB, keduanya `installed` per 28-Sep-2026, DB **disposable**). Efek samping
yang diperbaiki: `custom_wms_cycle_count` memposting `stock.move` dengan field `name` yang tidak ada lagi di Odoo 19 —
**setiap** penyesuaian cycle count rusak, ESB atau bukan; dan `ir_sequence_data.xml`-nya placeholder sehingga semua sesi
bernama `CC/NEW`. Ketiga modul masuk pack `fnb` di `custom_hub_console` (`esb-odoo-efn-integration`).

**Blocker:** Q1 (akun integrasi khusus, idealnya static API key) dan Q2 (environment + kredensial staging) di
`docs/projects/efn-esb/02-BRD-technical.md` §7 — keduanya bertanda **Blocking: Yes**, Q1 "highest priority". Q3–Q7 tidak
memblokir tetapi Q4 (`additionalInfo` tersimpan verbatim dan bisa difilter) harus dikonfirmasi sebelum go-live; "Everything
else is ready" (`docs/projects/efn-esb/README.md`). Kriteria penerimaan AC-1 … AC-6 sudah tertulis, termasuk **AC-1:
autentikasi bertahan dari eviction sesi eksternal yang disengaja tanpa intervensi manual**
(`docs/projects/efn-esb/02-BRD-technical.md` §8).

## 5. MDM product-master API

Dibangun 27-Jul-2026 untuk feed Levi's Principal: `MDM HUB → SAP PO → IBM MQ → Mulesoft → POST <base>/products → Odoo`,
menggantikan laporan SSRS **X101**.

**Kunci SKU adalah `udf2`, BUKAN `skuCode`.** Aturannya berlaku pada seluruh **214.305 baris**
`docs/projects/levis/X101_Material_Master.xlsx`: `PROD SKU == PRODUCT_CODE.replace("-","") + "0" + ITEM_SIZE + (INSEAM if !=
"-")` — contoh `002IJ0027` + `0` + `32` + `28` = `002IJ002703228`. `skuCode` (`002IJ-00273228`, pakai tanda hubung) **tidak
muncul sama sekali** di X101 → disimpan di `product.product.mdm_sku_code`, **jangan** di `default_code`.
`category1`/`category2` adalah **taksonomi yang berbeda** dari 7 CATEGORY ber-prefix gender / 118 triple CLASS-SUBCLASS
milik X101, dan **tidak ada sumber SUBCLASS sama sekali** — karena itu ada crosswalk `retail.mdm.category.map` + flag
`mdm_category_unmapped`. **Jebakan Odoo yang memakan dua putaran debug:** pada template single-variant Odoo memirror
`default_code` varian ke `product.template.default_code`, jadi item satu ukuran menampilkan PROD SKU di template bukan kode
mainline — pakai `product.template.mdm_template_code`. Auth = mode `api_key` di `secure_endpoint` `custom_core` (default
tetap `hmac` agar 5 scope live tak tersentuh; **CIDR allow-list wajib** di mode api_key) (`levis-mdm-product-api`).

Endpoint memberi tahu dirinya sendiri: `GET /ping` dan `POST /products` mengembalikan `environment` + `database`. **Assert
`environment` sebelum run**, jangan percaya URL yang dikonfigurasi di klien — UAT dan produksi berbagi host, port, dan
sertifikat yang sama, dan **prefix path adalah satu-satunya pembeda**. Base URL produksi masih menjawab **`404
NOT_DEPLOYED`**; `enabled: false` → 503; `dryRun: true` → pesan divalidasi dan dipetakan tetapi **tidak ada produk yang
ditulis** (fase shadow, diharapkan di awal rollout). Spesifikasi mesin `docs/integrations/mdm-product-api.openapi.yaml`,
OpenAPI 3.1 (`docs/integrations/mdm-product-api.md`).

## 6. Denso BHT / barcode

**Denso BHT-1700QWB-1 di jaringan ini membaca EAN-13 dengan baik tetapi gagal pada SETIAP Code128.** Terverifikasi bahwa itu
perangkatnya, bukan hasil cetaknya: `zbarimg` berhasil mendekode **31/31** barcode (termasuk semua Code128) pada 300 dpi
dari PDF yang sama. Sebabnya: Denso merek Jepang dan banyak unit BHT dikirim dengan hanya simbologi JAN/EAN/UPC aktif;
Code128 mati secara default, dan perbaikannya **di perangkat**. Barcode bin/lokasi dan dokumen (`JDC-GR-IN-01`,
`JDC/IN/00012`) alfanumerik dan **hanya bisa** Code128 — tidak ada fallback EAN-13, jadi mengaktifkan Code128 itu **wajib**,
bukan opsional. Karena itu laporan WMS merender barcode item dengan mode `auto` supaya payload 13 digit keluar sebagai
EAN-13, sementara barcode dokumen tetap Code128. Generator sheet barcode: `scripts/tenants/wms_demo/gen_pdf.py`; output
dipublikasikan ke `/srv/sftp-share/files/hht_barcode_test_receiving.pdf` (`denso-bht-code128-disabled`,
`wms-report-barcodes`).

## 7. Yang MASIH TERBUKA

| # | Jalur | Yang terbuka |
| --- | --- | --- |
| T1 | PPOB | Enam gap G1–G6; DB `ppob` masih nol data master; node tidak masuk backup otomatis; ganti password admin awal bawaan installer |
| T2 | PPOB | Sembilan keputusan terbuka di `06-Addendum-PPS.md`; 10 keputusan terbuka di BRD PPS |
| T3 | VAS PMO | Akun pengguna nyata, reverse proxy 443, kredensial WaHub, `legal_entity` per brand, modul Jira + ticket-bridge |
| T4 | VAS PMO | Perbaikan stage + blok `odoo-vaspmo` **uncommitted** di `/home` branch `feat/vas-pmo`; keputusan OD1 belum dijawab |
| T5 | EFN/ESB | Q1 kredensial/static API key + Q2 environment staging — **keduanya blocking**; Q4 wajib dikonfirmasi sebelum go-live |
| T6 | MDM | Base URL produksi `/api/mdm` masih `404 NOT_DEPLOYED`; masih di fase UAT/shadow |
| T7 | Denso | Simbologi Code128 belum diaktifkan di unit BHT — perangkat, bukan software |

## 8. JANGAN

- **JANGAN WebFetch `developers.esb.co.id`** (shell kosong; parse `api_data.js`), **jangan percaya kode HTTP dari ESB** (200
  + `status:"fail"` normal), **jangan menjalankan beberapa worker yang masing-masing login** (saling mengevict), **jangan
  mengirim `qty` sebagai kuantitas hasil hitung** ke `/inventory/item-journal` (delta bertanda), dan **jangan mengandalkan
  idempotency ESB** (`esb-core-api`).
- **JANGAN memakai `skuCode` sebagai kunci SKU** (kuncinya `udf2`) dan **jangan memakai `default_code` sebagai identitas
  `product.template`** pada feed MDM (`levis-mdm-product-api`). Dan **jangan menyalahkan generator barcode sebelum `zbarimg
  -q --raw`** memastikan PDF-nya terdekode (`denso-bht-code128-disabled`).
- **JANGAN memakai `rnd_ppob` untuk demo atau UAT** (USD + `generic_coa`, permanen), dan **jangan me-restore `rnd_ppob` ke
  node baru** — bangun DB baru dengan `install-ppob.sh` (`rnd-ppob-db-setup`, `ppob-node-vps-185-takeover`).
- **JANGAN memasang modul PPOB sebelum CoA `l10n_id` ter-load** (FK `custom_ppob_account_mapping_account_id_fkey` pecah) dan
  **jangan memasang `custom_ppob_oracle_bridge` kecuali benar-benar dipakai** (`rnd-ppob-db-setup`).
- **JANGAN menghapus container/volume `odoohub` di 192.168.3.185** (jalur rollback), **jangan memulihkan `/opt/odoohub`** di
  host ini, dan **jangan mengandalkan `docker compose config`** untuk membaca `DBFILTER` (`ppob-node-vps-185-takeover`,
  `odoohub-predecessor`).
- **JANGAN mengubah `handle /vaspmo*` menjadi `handle_path`**, jangan mengasumsikan `NextResponse.redirect` menambah
  basePath, **jangan menjalankan test VAS PMO tanpa `--workers 0`**, dan jangan percaya keluaran `deploy-vas-pmo.sh
  --with-tests` yang di-pipe ke `tail -5` (`vas-pmo-deploy-rnd`).
