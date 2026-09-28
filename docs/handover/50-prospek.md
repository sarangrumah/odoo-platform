# Handover — Pipeline & prospek

## 1. Ringkasan

Empat jalur yang **belum berjalan** plus satu submission award. Setiap angka dan tanggal menyebut sumbernya dalam
tanda kurung: nama file memory, path repo, nomor PR, atau nama basis data. Status DB diverifikasi terhadap
`pg_database` pada `odoo19-platform-postgres`, **28-Sep-2026**.

> **Semua yang ada di halaman ini adalah pipeline, bukan produksi.** Tidak ada satu pun yang punya DB produksi,
> kontrak implementasi berjalan, atau pengguna akhir. Yang ada adalah dokumen, pilot, dan estimasi. Jangan
> menggambarkannya seolah berjalan.

| Proyek | Pelanggan | Tahap | DB | Dokumen yang sudah ada |
| --- | --- | --- | --- | --- |
| GentleWoman | GentleWoman (retail fashion) | Pilot storefront; **diblokir integrasi pembayaran Eraspace** | `gentlewoman` (110 MB, hanya `custom_storefront_api`) | 11 markdown + 4 PDF + 1 PPTX + SoC xlsx |
| Finance Portal | Erajaya (di depan SAP S/4HANA) | Charter **Draft for Approval** 23-Jun-2026; belum ada tenant | **tidak ada** (hanya terpasang di `rnd_ppob`) | Charter, Architecture v1/v2 docx, 3 dokumen estimasi + xlsx |
| Warehouse JDS | JDS — JD Sport Cikupa | **Pra-implementasi**; POC lulus, kontrak belum | **tidak ada** (POC di `demo_wms`/`rnd_wms`) | Paket `wms-implementation` 7 dokumen + materi klien JDS |
| PPS / Odoo-Hub | Erajaya VAS / Eraspace | Dokumen BRD/TSD/UAT siap; program Fase 1–3 belum dimulai | node `ppob` di 192.168.3.185 (kosong) | BRD + TSD docx, UAT xlsx, paket `ppob-implementation` 10 dokumen |
| EAA — EAL-Hub | Internal Erajaya (E-InnoHub) | Material siap, **belum disubmit** | — | `docs/awards/eaa-ealhub/` form + 3 PPTX (tanpa PDF) |

## 2. GentleWoman

- Paket dokumen di `docs/projects/gentlewoman/`: 00 Board Briefing, 01 PID, 02 BRD, 03 FSD, 04 TSD, 05 Executive
  One-Pager, 06 AI Personal Shopper MVP Plan, `spec-headless-fashion-commerce-ai.md`, plus Release 1.0 Business
  Package (11-TSD-v1.0, 12-Blueprint-v1.0, 13-FSD-v1.0) dengan artefak PDF/PPTX dan
  `Scope of Compliance (SoC) - ecommerce website for GentleWomanAP .xlsx`
  (`docs/projects/gentlewoman/README.md`).
- **Posisi yang tidak konsisten antar dokumen — perlu diputuskan satu versi.** One-pager menyebut
  "**Live pilot · tenant `gentlewoman`**" sementara indeks proyek platform menyebut GentleWoman
  "**pre-implementation**, owned modules: none yet" (`docs/projects/gentlewoman/05-one-pager.md` vs
  `docs/projects/README.md`). Yang bisa diverifikasi: DB `gentlewoman` **ada** (110 MB) dan hanya
  `custom_storefront_api` 19.0.0.1.0 yang `installed` (28-Sep-2026); container `odoo19-platform-storefront`
  **Up 6 weeks (healthy)**.
- **Satu blocker menurut dokumen:** Fase 1 "built, integrated and verified end-to-end", dan satu-satunya dependensi
  ke go-live penuh adalah **integrasi pembayaran Eraspace** — checkout selesai sampai pembuatan order dan aktif
  begitu spesifikasi API vendor tiba (`docs/projects/gentlewoman/05-one-pager.md`).
- Yang diklaim sudah jalan di pilot: browse/detail produk, ketersediaan ukuran, harga promo, "New" drops, pencarian
  & filter bilingual ID/EN; store locator + **stok toko real-time** + click-&-collect; akun + guest checkout,
  alamat tersimpan, riwayat order, wishlist; **program afiliasi** (link terlacak, komisi, payout, dashboard
  self-serve); promosi, newsletter, CMS editorial **di dalam Odoo**; konsen **UU PDP**.
- **AI personal shopper** adalah diferensiator Fase 3 yang **budget-gated**, sengaja di luar jalur kritis launch
  (`docs/projects/gentlewoman/05-one-pager.md`, `06-ai-personal-shopper-mvp-plan.md`).
- **Tiga permintaan ke board yang menggantung:** (1) endorse pilot naik ke rencana launch produksi; (2) unblock
  pembayaran dengan meneruskan dokumentasi API Eraspace ke tim delivery; (3) putuskan budget AI shopper —
  approve atau defer, independen dari launch.
- Rebuild artefak: `python tools/build_gentlewoman_deck.py` dan `python tools/build_gentlewoman_docs.py`; publikasi
  ke Odoo lewat `python tools/publish_gentlewoman_docs.py` (XML-RPC ke DB `gentlewoman`, atau `--print-shell`).
  PDF dipublikasikan sebagai `ir.attachment` **publik** dan dijangkau lewat proxy `/api/docs/<id>` yang **hanya**
  menyajikan PDF publik (id non-publik → 404). **Attachment id berubah setiap PDF di-regenerate** — tabel id di
  README harus diperbarui setelah publish (`docs/projects/gentlewoman/README.md`).

## 3. Finance Portal

- Posisi: **Odoo sebagai *system of engagement* di depan SAP S/4HANA yang tetap *system of record*** (posting GL,
  MIRO, pembayaran). Memenuhi requirement "Finance Portal - Integration.xlsx": Cash Advance, Reimbursement &
  Expenses, Vendor Invoice (PO / Non-PO Non-Trade), settlement Perjalanan Dinas — masing-masing dengan approval
  **Tax → Finance**, validasi budget/PR, push SAP + mirror status, sinkronisasi master data, dan SSO
  (`docs/projects/finance-portal/README.md`).
- Empat modul Odoo + satu sidecar non-Odoo: `custom_finance_portal` (domain engagement + `finance.document.mixin`,
  **tanpa posting GL**), `custom_finance_budget` (budget biaya per divisi/tahun + `_check_document_budget` soft
  enforce), `custom_finance_portal_sap` (adapter `finance_sap_bridge`/`finance_hris_bridge`, push async via
  `queue_job`, cron sinkron master harian, webhook masuk `secure_endpoint('finance_sap')`, `finance.sync.log`),
  `custom_finance_portal_sso` (Keycloak SSO via `auth_oauth` + mapping role→group employee vs vendor), dan
  `services/finance-sap-bridge` (jembatan Kafka ⇄ HMAC-REST, punya mode mock tanpa Kafka).
- Siklus hidup dokumen: `draft → submitted → (Tax review → Finance review) → approved → pushed → posted → paid`
  (+ `rejected`/`cancelled`). **Odoo tidak pernah memposting jurnal**; `_finance_push_to_sap` mengirim dokumen yang
  sudah disetujui ke bridge, dan bridge memirror tanggal payment-plan + status SAP balik lewat webhook
  (`_finance_apply_sap_status`).
- **Belum ada tenant Finance Portal.** Satu-satunya DB di host ini yang memasang `custom_finance_portal` adalah
  `rnd_ppob` — DB kerangka PPOB, bukan lingkungan Finance Portal (diverifikasi 28-Sep-2026; lihat juga
  `rnd-ppob-db-setup`).
- **Dependensi eksternal yang bertanda "Not Ready" di spreadsheet klien dan BUKAN build kita** — suite berjalan
  stub/mock sampai semuanya mendarat: SAP memaparkan **PR/PO/GR non-trade** dengan nilai + status (sekarang hanya
  trade); konektor Kafka/SAP untuk **posting GL, journal, MIRO, payment list, GL account/budget, master feed**
  (item category, COA, cost budget, approval matrix); **addon Attachment** ke SAP Basis; **status approval
  PO/invoice** dari SAP; kontrak API **HRIS** travel + employee-master. Bentuk JSON dan topic map yang disepakati
  ada di `services/finance-sap-bridge/app/contracts.md` (`docs/projects/finance-portal/README.md`).
- Estimasi **scope Odoo saja** (effort SAP dan HC/HRIS dikeluarkan): subtotal PMO 47 / BA 93 / Dev 177 / QA 84 =
  **401 mandays**, dengan kontingensi 15% menjadi PMO 54 / BA 107 / Dev 204 / QA 97 = **≈ 462 mandays**, durasi
  ±24 minggu. Satu manday = satu orang-hari; **mandays ≠ durasi kalender**
  (`docs/projects/finance-portal/Project-Estimation-Odoo-Finance-Portal.md`).
- Charter berstatus **Draft for Approval**, versi 1.0, 2026-06-23
  (`docs/projects/finance-portal/Project-Charter-Odoo-Finance-Portal.md`).
- Opsi packaging: tambahkan `custom.hub.industry.pack` "Finance Portal (SAP)" di `custom_hub_console`
  (`_SEED_PACK_MODULES` + `industry_pack_seed.xml`) yang memuat 4 modul portal + `custom_approval_engine`,
  `custom_adapter_framework`, `queue_job`, `hr`, `account`, `auth_oauth` — **belum dilakukan**.

## 4. Warehouse JDS

- **Status engagement: pra-implementasi. POC selesai dan lulus; kontrak implementasi belum**
  (`docs/projects/wms-implementation/06-Addendum-JDS.md` v1.1, 2026-08-11).
- **Tidak ada DB JDS.** POC dijalankan di `demo_wms` (380 MB, demo JD Sport Cikupa) dan `rnd_wms` (172 MB,
  implementasi referensi). Detail teknis tumpukan WMS ada di handover terpisah `30-wms.md` — termasuk fakta bahwa
  DB bernama `prd_wms` **kosong** dan bukan produksi.
- Bukti yang sudah ada: skenario POC 12 kategori transaksi (A–L) **14/14 PASS**
  (`docs/projects/warehouse-jds/WMS-POC-Scenario.md`); uji otomatis lembar 15 kebutuhan klien **15/15 PASS**
  (`scripts/tenants/wms_demo/70_scenario_test.py`); walkthrough `80_poc_scenario.py`; dataset demo
  `10..52_*.py`; materi klien (capability deck, configuration guide, `WMS-Test-Scenario-rnd_wms.xlsx`,
  18 screenshot) di `docs/projects/warehouse-jds/`.
- **JDS tidak punya modul sendiri** dan sebaiknya tetap begitu: ia berjalan di atas `ee_gap/custom_wms_*` +
  `core/custom_hht_bridge`; tidak ada alasan membuat modul `_tenants/` kecuali muncul kebutuhan yang tidak layak
  digeneralisasi (`docs/projects/wms-implementation/06-Addendum-JDS.md` §1).
- Estimasi JDS pasca-POC, **tanpa PM** (kolom PM sengaja dikosongkan): BA 30 / DEV 51 / QA 28 = 109, plus
  kontingensi 15% → **BA 34 / DEV 59 / QA 32 ≈ 125 mandays, ≈ 10 minggu**. Dibanding Greenfield 448 md itu hemat
  **72%**; dibanding Brownfield generik 179 md selisihnya 54 md karena Requirement lebih pendek, Design delta lebih
  kecil, dan pengujian bisa memakai `70_scenario_test.py` + `80_poc_scenario.py` sebagai basis regresi.
- Asumsi lingkup estimasi: **1 gudang (Cikupa), ≤3 zona, ≤200 bin, ≤5.000 SKU aktif, integrasi SAP di-scope.**
  Penyesuaian bila asumsi berubah: SAP **tidak** di-scope −10 md; skala >500 bin +8; >10.000 SKU +10; mode SAP
  slotting tidak dipakai −5; gudang kedua serupa +10; mode offline handheld terbukti wajib +12; pembersihan master
  data massal dinilai setelah audit (`docs/projects/wms-implementation/06-Addendum-JDS.md` §6).
- **Delapan hal yang harus ditutup di fase Requirement & fit-gap JDS** (O1–O8): volume riil gudang/zona/bin/SKU
  aktif di Cikupa; perangkat handheld riil dan simbologi yang aktif (unit Denso di lingkup proyek ini **hanya
  membaca EAN-13** — harus diuji, bukan diasumsikan); integrasi SAP di-scope atau tidak; kualitas master produk
  JDS (barcode unik, dimensi, berat); mode SAP slotting dipakai atau tidak; denah bin riil dan urutan jalan;
  ekspektasi ketersediaan & RPO (**RPO nyata platform saat ini 24 jam**); serta relevansi gap platform yang sudah
  diketahui (cron sesi hitung, berkas placeholder, mode offline handheld)
  (`docs/projects/wms-implementation/06-Addendum-JDS.md` §5).

## 5. PPS / Odoo-Hub

- Program **PPS** (Erajaya Value-Added Services / Eraspace, revamp EVShop) di atas **Odoo Hub**. Lingkup gabungan:
  control plane Odoo Hub **dan** fungsi PPOB/PPS, mencakup **Fase 1–3** (`docs/projects/pps-odoo-hub/README.md`).
- Paket dokumen klien sudah lengkap: **BRD** 15 bab / 26 tabel / **142 kebutuhan bernomor** (BR-HUB, BR-AU, BR-MD,
  BR-WL, BR-TU, BR-DP, BR-TX, BR-BL, BR-CH, BR-PR, BR-RS, BR-FI, BR-OP, BR-NF) dengan MoSCoW + status platform +
  fase, 14 aturan bisnis, **10 keputusan terbuka**, 12 risiko, gerbang antar fase; **TSD** 11 bab / 25 tabel
  termasuk 7 rute kanal + 2 rute VA + 2 feed + **5 operasi wallet yang perlu dibangun**, 10 utang teknis,
  14 kriteria penerimaan teknis; **UAT Script** 9 lembar / **184 kasus uji** (107 positif / 77 negatif) dengan
  Traceability seluruh 142 kebutuhan dan Defect Log.
- Isi dokumen **di-grounding ke kode nyata** — `addons/control_plane/custom_hub_console`, `tenant-orchestrator`,
  dan 12 modul `addons/verticals/custom_ppob_*` — dan tidak ada kapabilitas berstatus perlu dibangun yang ditulis
  seolah sudah tersedia (`docs/projects/pps-odoo-hub/README.md`).
- **`docs/projects/pps-odoo-hub/` TIDAK berhubungan dengan stack `odoohub` lama.** Yang ini generator dokumen BRD/
  TSD/UAT; `odoohub` adalah pendahulu `odoo-platform` yang sudah dimatikan (`odoohub-predecessor`).
- Substrat teknisnya sudah ada tetapi kosong: node `ppob` di VPS 192.168.3.185 terbangun dan terverifikasi
  8-Sep-2026 dengan 11 modul PPOB installed, IDR, `chart_template=id` — tetapi **nol data master dan nol
  transaksi**. Enam gap G1–G6 (termasuk **API wallet sinkron belum ada**) masih terbuka. Rincian ada di handover
  `40-integrasi.md` §2 (`ppob-node-vps-185-takeover`, `docs/projects/ppob-implementation/README.md`).
- Estimasi PPS tiga fase, tanpa PM: BA 32 / DEV 114 / QA 56 ≈ **233 mandays / ≈ 23 minggu** — lebih besar dari
  Brownfield generik (243 md/13 minggu justru lebih singkat durasinya) karena mencakup **tiga gelombang perpindahan
  otoritas** (saldo → dispatch → konsolidasi), masing-masing dengan gerbang paritasnya sendiri. Untuk gap *Revamp
  EVShop* khusus: ≈497 md penuh / ≈235 md prioritas, yang di-rebase menjadi **178 md / 14 minggu** untuk delivery
  AI-assisted (`docs/projects/ppob-implementation/README.md`, dokumen 07 dan 09).

## 6. Submission Erajaya Achievement Award (EAA) untuk EAL-Hub

- Disiapkan 17-Sep-2026: material submission **Erajaya Achievement Award** jalur **Project** lewat platform
  **E-InnoHub** di QLEAP, untuk project **EAL-Hub** (= brand produksi platform Odoo ini, `eal-hub.erajaya.com`;
  EAL = Erajaya Active Lifestyle). **Belum disubmit — login NIK milik user** (`eaa-ealhub-submission`).
- Deliverable di `docs/awards/eaa-ealhub/`: `00-form-innohub.md` (teks final tiap field form Basic Info → Business
  Issue → Idea → Project Implementation, plus tabel sumber tiap angka) dan deck yang dibuat
  `tools/build_eaa_ealhub_deck.py`, yang meng-import `build_pptx`/`build_pdf` dari
  `tools/build_presentation.py` sehingga keduanya bisa dipakai sebagai library. Isi direktori per 28-Sep-2026:
  `EAA-EAL-Hub.pptx`, `EAA-EAL-Hub-Business-Issue.pptx`, `EAA-EAL-Hub-Idea.pptx`, plus `brand/`, `screenshots/`,
  `template/` — **tidak ada berkas `.pdf`** di sana, walau memory menyebut `.pdf` pernah dibuat, jadi regenerate
  dulu kalau PDF dibutuhkan.
- Tim: user (owner) + Agus Suripto 202307510, Christopher Hansel 202401484, Arindini Nuri 202611005.
- Angka kunci: **124 user internal** (88 `prd_levis_begbal` + 36 `prd_arkaaim`) × **Rp 170.000** (odoo.com/pricing
  paket Custom) × 12 = **Rp 252.960.000/tahun lisensi EE dihindari**; **159 modul kustom** (108 `ee_gap`),
  646 model, **215.567 baris Python**, 645 commit.
- **Timeline nyata (BUKAN "4 bulan"):** commit pertama 16-Mei-2026 → kedua DB produksi berdiri 11-Jun (26 hari) →
  jurnal pertama 10-Jul (55 hari) → 12.422 jurnal sebelum 1-Agu. Headline: **8 minggu dari nol ke produksi**.
- Nilai jual dashboard Next.js 15: finance-cockpit (14 tie-check per page load, parity vs laporan Odoo, 70.735
  baris ~1 detik), sales-cockpit (Rp 27,92 M / 19.268 order / 23 toko / 72 SPG), login-gateway, vas-pmo — semua
  read-only di tingkat DB, dan **asisten finance sengaja TANPA LLM** (`eaa-ealhub-submission`,
  `finance-cockpit-dashboard`).
- Branding: logo Erajaya Active Lifestyle dari `login-gateway/public/brand/eal-logo.png`; logo InnoHub +
  E-University diekstrak dari PDF playbook klien ke `docs/awards/eaa-ealhub/brand/`. Palet: navy `#23308F` (warna
  bersama), merah `#E30613` (Erajaya), oranye `#F79009` (InnoHub).
- **Asumsi yang HARUS tetap tertulis:** rate Rp 3 juta/manday adalah **asumsi**; ±Rp 7,15 M adalah **nilai setara
  build, bukan penghematan**; dan **JANGAN mengklaim satu tanggal go-live bersih** — cutover Levi's sengaja
  bertahap (`eaa-ealhub-submission`, `levis-config-followups-status`).
- Yang belum ada: **rubrik penilaian EAA** (playbook InnoHub hanya cara memakai platform). Dependensi build deck
  (`python-pptx`, `reportlab`) **tidak terpasang** di python sistem — pakai venv.

## 7. Komitmen & dokumen yang menggantung

| # | Hal | Sumber |
| --- | --- | --- |
| P1 | GentleWoman: dokumentasi API pembayaran **Eraspace** harus diteruskan ke tim delivery — satu-satunya blocker go-live | `docs/projects/gentlewoman/05-one-pager.md` |
| P2 | GentleWoman: board harus memutuskan endorse launch dan approve/defer budget AI shopper | `docs/projects/gentlewoman/05-one-pager.md` |
| P3 | GentleWoman: status "Live pilot" vs "pre-implementation" bertentangan antar dokumen — satukan sebelum dipakai ke klien | `05-one-pager.md` vs `docs/projects/README.md` |
| P4 | GentleWoman: tabel attachment id di README harus diperbarui setiap PDF di-regenerate | `docs/projects/gentlewoman/README.md` |
| P5 | Finance Portal: Charter masih **Draft for Approval** (23-Jun-2026) — belum ada persetujuan | `Project-Charter-Odoo-Finance-Portal.md` |
| P6 | Finance Portal: 5 kelompok dependensi SAP/Kafka/HRIS bertanda "Not Ready" — suite jalan stub/mock sampai mendarat | `docs/projects/finance-portal/README.md` |
| P7 | Finance Portal: belum ada tenant; industry pack `custom_hub_console` belum dibuat | DB (28-Sep-2026), `docs/projects/finance-portal/README.md` |
| P8 | JDS: O1–O8 harus ditutup di fase Requirement; **simbologi handheld Denso wajib diuji, bukan diasumsikan** | `06-Addendum-JDS.md` §5, `denso-bht-code128-disabled` |
| P9 | JDS: estimasi 125 md bersifat **indikatif berbasis asumsi tertulis, bukan komitmen kontrak**, dan kolom PM masih kosong di seluruh paket | `docs/projects/wms-implementation/README.md` |
| P10 | PPS: 10 keputusan terbuka di BRD + 9 di `06-Addendum-PPS.md`; 5 operasi wallet masih perlu dibangun | `docs/projects/pps-odoo-hub/README.md`, `ppob-implementation/README.md` |
| P11 | PPS/PPOB: enam gap G1–G6 harus diakui apa adanya di setiap presentasi — sudah tertulis terbuka di paket dokumen | `docs/projects/ppob-implementation/README.md` |
| P12 | EAA: submission belum dikirim (login NIK milik user); rubrik penilaian belum ada | `eaa-ealhub-submission` |
| P13 | EAA: deck lama `docs/presentation-erajaya-vas.md` masih menyebut 82 modul — **basi**, jangan dipakai | `eaa-ealhub-submission` |
| P14 | Katalog fitur: memory menyebut direktorinya tak ter-track dan branch-nya belum di-push, tetapi per 28-Sep-2026 **8 berkas di `docs/platform-feature-catalog/src/` SUDAH tracked** dan **`origin/docs/feature-catalog-main` SUDAH ada** — verifikasi dulu sebelum mengutip klaim lama | `platform-feature-catalog` vs `git ls-files` / `git branch -a` |
| P15 | Katalog fitur: hitungan modul di `main` adalah **156**, bukan 158 — dua modul hanya ada di checkout `/home`; rebuild setelah setiap merge | `platform-feature-catalog` |

Catatan terakhir tentang katalog fitur, karena ia jadi lampiran presales untuk semua prospek di atas: pipeline-nya
`build_catalog_json.py` → `catalog.json` → `render_md.py`/`render_html.py`/`build_xlsx.py`, dijalankan lewat
`./build.sh` lalu `./publish.sh` ke `/srv/sftp-share/files/katalog-fitur-platform/`, dengan `verify.py` menjalankan
14 pemeriksaan. Dua invarian yang menjaganya jujur: `taxonomy.py::DOMAIN_BY_MODULE` wajib mencakup setiap modul di
disk dua arah tanpa bucket catch-all (addon baru **menggagalkan build** sampai diklasifikasi), dan `--audit`
mencocokkan setiap model/field yang diklaim knowledge file terhadap hasil AST scan — **hanya 4 dari 129 knowledge
doc berstatus `reviewed`, 111 masih draft generator** (`platform-feature-catalog`).
