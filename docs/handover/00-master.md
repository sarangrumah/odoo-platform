# Handover EAL-Hub — Dokumen Master

**Berlaku per:** 28 September 2026
**Platform:** EAL-Hub (`eal-hub.erajaya.com`) — EAL = *Erajaya Active Lifestyle*
**Repo:** `github.com/sarangrumah/odoo-platform` · Odoo 19 CE multi-tenant

Dokumen ini adalah bagian lintas-vertikal. Rincian per pelanggan ada di dokumen pendamping:

| Dokumen | Cakupan |
| --- | --- |
| `Handover-Levis.docx` | PT ERA Busana Retailindo (Levi's) — retail, **live** |
| `Handover-ARKA-AIM.docx` | ARKA-AIM — drone rental & drone show, **live** |
| `Handover-WMS.docx` | WMS — rnd/demo saja, belum produksi |
| `Handover-Integrasi-PPOB-VAS-ESB.docx` | PPOB/PPS, VAS PMO, ESB/EFN, Denso |
| `Handover-Pipeline-Prospek.docx` | GentleWoman, Finance Portal, JDS, PPS/Odoo-Hub, submission EAA |

> Sumber pengetahuan dokumen ini adalah 274 catatan operasional yang **tidak ada di repo**
> dan dihapus setelah handover. Setiap angka dan tanggal di sini menyebut sumbernya dalam
> tanda kurung — nama catatan, path repo, nomor PR, atau nama DB — supaya tetap bisa
> diaudit setelah catatan aslinya tidak ada. Arsipnya: `handover-eal-knowledge-20260928.zip`.

---

## 1. Ringkasan eksekutif

EAL-Hub adalah platform Odoo 19 Community multi-tenant yang dibangun untuk menggantikan
fungsi Odoo Enterprise dengan modul kustom. Per 28-Sep-2026 ia melayani **dua pelanggan
produksi** (Levi's dan ARKA-AIM) di atas satu VPS, dengan ~24 database dan 21 container.

Angka platform yang sudah diaudit untuk submission Erajaya Achievement Award
(`docs/awards/eaa-ealhub/00-form-innohub.md`, `eaa-ealhub-submission`):

- **124 user internal** — 88 di `prd_levis_begbal`, 36 di `prd_arkaaim`
- **159 modul kustom** (108 di tier `ee_gap`), **646 model**, **215.567 baris Python**
- **Rp 252.960.000/tahun** lisensi Enterprise yang dihindari — asumsi Rp 170.000/user/bulan
  paket Custom dari odoo.com/pricing × 124 user × 12
- **Timeline nyata: 8 minggu dari nol ke produksi** — commit pertama 16-Mei-2026, dua DB
  produksi berdiri 11-Jun (26 hari), jurnal pertama 10-Jul (55 hari), 12.422 jurnal sebelum
  1-Agu

> **Yang HARUS tetap tertulis saat mengutip angka itu:** rate Rp 3 juta/manday adalah
> asumsi; ±Rp 7,15 M adalah *nilai setara build*, bukan penghematan kas; dan **jangan pernah
> mengklaim satu tanggal go-live yang bersih** — cutover Levi's sengaja bertahap
> (`eaa-ealhub-submission`, `levis-config-followups-status`).

Empat aplikasi dasbor Next.js 15 berdiri di luar Odoo dan **semuanya read-only di tingkat
database**: `finance-cockpit` (14 tie-check tiap page load), `sales-cockpit` (Rp 27,92 M /
19.268 order / 23 toko / 72 SPG), `login-gateway`, `vas-pmo`. Asisten di finance-cockpit
**sengaja tanpa LLM**.

## 2. Executive summary (English)

EAL-Hub is a multi-tenant Odoo 19 Community platform that rebuilds Enterprise-only features
as custom modules. As of 28 Sep 2026 it serves **two production customers** — Levi's (PT ERA
Busana Retailindo) and ARKA-AIM — from a single VPS, across ~24 databases and 21 containers.

Audited platform figures: **124 internal users** (88 `prd_levis_begbal` + 36 `prd_arkaaim`),
**159 custom modules** (108 in the `ee_gap` tier), **646 models**, **215,567 lines of
Python**, and **IDR 252,960,000/year of avoided Enterprise licensing** (an assumption of IDR
170,000/user/month on the Custom plan). Real timeline: **eight weeks from nothing to
production** — first commit 16 May 2026, two production databases live 11 Jun, first journal
entry 10 Jul, 12,422 journal entries before 1 Aug.

Four read-only Next.js 15 dashboards sit outside Odoo: `finance-cockpit`, `sales-cockpit`,
`login-gateway`, `vas-pmo`. The finance assistant deliberately has **no LLM**.

Three things a newcomer must internalise before touching anything:

1. **There are two checkouts of this repo on the host and they diverge on purpose.**
   `/home/odoo-erp/odoo-platform` is where you commit; `/opt/odoo-platform` is what actually
   runs. Never run `docker compose up/down` from `/home`.
2. **Take a fresh `pg_dump` before touching any `prd_*` database** — including a plain
   `-u <module>` upgrade. The nightly dump can be 24 hours old.
3. **Other sessions and other people share both checkouts.** Re-read `git status -sb`
   immediately before any reset, copy, or branch move — an approval given one turn ago can be
   aimed at a branch that no longer exists.

---

## 3. Peta environment

### 3.1 Dua checkout — ini akar dari sebagian besar insiden

| | `/home/odoo-erp/odoo-platform` | `/opt/odoo-platform` |
| --- | --- | --- |
| Peran | checkout dev, tempat commit | checkout runtime |
| `addons/` di-mount ke | tidak ada | 4 container: `odoo`, `odoo-mgmt`, `odoo-front`, `odoo-vaspmo` sebagai `/mnt/extra-addons` |
| Branch | berpindah sendiri (sesi lain) | pernah `main`, pernah branch deploy |
| Artinya | menyunting di sini **tidak** mengubah aplikasi yang jalan | berkas di disk **adalah** kode produksi untuk semua tenant |

Keduanya memakai `COMPOSE_PROJECT_NAME=odoo19-platform` yang sama, dan Postgres memakai
bind-mount **relatif** `./data/postgres` (`odoo-platform-checkouts`).

> **BAHAYA — jangan pernah `docker compose up/down` dari `/home`.** Compose akan me-recreate
> container `odoo19-platform-postgres` yang bernama sama, menunjuk ke `/home/.../data/postgres`
> (cluster dev, 2–3 DB) alih-alih `/opt/.../data/postgres` (produksi). Data produksi tidak
> hilang, cuma ter-unmount.

Ini sudah kambuh dua kali dengan mode kegagalan makin buruk:

- **14-Agu-2026:** `docker compose up -d sales-cockpit` dari `/home` cukup untuk memicunya,
  karena service baru itu punya `depends_on: postgres`. Produksi jalan di data dir salah
  ~74 detik (`odoo-platform-checkouts`).
- **Kambuh lagi:** compose berhenti di tengah karena container `sales-cockpit` lama tidak
  punya label compose → Postgres baru tertinggal status `Created`, **tidak pernah `Started`**.
  Database benar-benar **mati beberapa menit** (`compose-home-postgres-incident`).

Pengaman yang tidak disengaja: password role `odoo` berbeda antar cluster, jadi Odoo tidak
bisa autentikasi ke cluster salah dan karena itu tidak bisa menulis ke sana. Radius
kerusakannya downtime, bukan korupsi data.

**Pemulihan (±1 menit, tidak menyentuh service lain):**

```bash
docker stop odoo19-platform-postgres
cd /opt/odoo-platform && docker compose \
  -f docker-compose.yml -f docker-compose.multitenant.yml up -d --no-deps postgres
```

Verifikasi sesudahnya: ketiga mount menunjuk `/opt`, `select count(*) from pg_database`
sesuai jumlah yang diharapkan, dan log odoo berakhir `database connections ready` — bukan
`OperationalError`.

`sales-cockpit` dan `finance-cockpit` adalah **satu-satunya** service yang sumbernya hanya
ada di `/home` (`/opt/odoo-platform/sales-cockpit` tidak ada), jadi ia perlu perlakuan khusus:
`docker compose build` dari `/home`, `docker rm -f` container lamanya (karena tanpa label
compose), lalu `docker compose up -d --no-deps <service>` — `--no-deps` **wajib**. Langsung
sesudahnya cek mount Postgres masih `/opt`.

### 3.2 Overlay compose wajib disebut eksplisit

`/opt/odoo-platform/.env` **tidak punya `COMPOSE_FILE`** (hanya `COMPOSE_PROJECT_NAME`),
sehingga `docker compose up -d <svc>` polos memakai `docker-compose.yml` saja dan **diam-diam
membuang seluruh override** di `docker-compose.multitenant.yml`. Container kembali dengan
status *healthy* padahal konfigurasinya hilang — tidak ada yang memberi peringatan
(`opt-compose-multitenant-overlay`).

Kejadian 4-Agu-2026 pada `tenant-orchestrator`: container yang di-recreate kehilangan
`read_only: false`, mount `/var/run/docker.sock`, dan env `ODOO_HOST`/`ODOO_MGMT_CONTAINER` —
jadi seluruh jalur tenant-bootstrap mati dengan healthcheck hijau.

```bash
docker compose -f docker-compose.yml -f docker-compose.multitenant.yml \
  up -d --no-deps <service>
```

Cara menemukan invokasi aslinya tanpa menduga: baca label dari container yang **tidak**
di-recreate — `docker inspect <c> --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'`.

### 3.3 Container yang berjalan (21, per 28-Sep-2026)

| Kelompok | Container |
| --- | --- |
| Odoo | `odoo`, `odoo-front`, `odoo-mgmt`, `odoo-vaspmo` |
| Data | `postgres` (16-alpine), `redis` (7-alpine), `minio` |
| Ingress | `caddy` (`caddy-waf:2.11.4`), `nginx`, `storefront-tls` |
| Dasbor | `finance-cockpit`, `sales-cockpit`, `login-gateway`, `hub-portal`, `vas-pmo` |
| Layanan | `tenant-orchestrator`, `ai-gateway`, `ollama`, `baileys`, `filebrowser`, `storefront` |

### 3.4 Isolasi tenant — sering salah dipahami

Ada **tiga** instance Odoo dengan peran berbeda (`docker-compose.multitenant.yml`,
`odoo-dbmanager-listdb-vs-dbfilter`):

| Container | `list_db` | `dbfilter` | Peran |
| --- | --- | --- | --- |
| `odoo` (publik via Caddy) | default False | `^%d$` | satu hostname → satu DB, tanpa DB manager |
| `odoo-mgmt` (127.0.0.1:18079) | True | `^.*$` | **dengan** DB manager |
| `odoo-front` | — | `^.*$` | **tanpa** DB manager, melayani login-gateway & cockpit |
| `odoo-vaspmo` | true | `^rnd_vas_pmo$` | khusus VAS PMO |

`list_db` dan `dbfilter` adalah dua setting berbeda yang sering tertukar. Membuka `list_db`
di instance publik **tidak** memunculkan daftar DB, karena `dbfilter = ^%d$` mensyaratkan
nama DB sama persis dengan hostname. Terukur 4-Agu-2026: publik `/web/database/list` = 0 DB,
`odoo-mgmt` = 17 DB.

> `odoo-mgmt` **bukan lagi admin-only** sejak PR #101 menggabungkan routing bare-IP — ia
> melayani seluruh host `103.130.240.24`, artinya sesi user nyata. Perlakukan sebagai
> container web produksi, bukan sidecar provisioning (`restart-both-odoo-containers`).

Ketiga container Odoo wajib satu cluster Postgres dan mount `./data/odoo-filestore` yang
sama — kalau tidak, aset 404.

### 3.5 Registry database

Sumber kebenaran: **`login-gateway/config/tenants.json`**. Prefiks: `prd_` produksi ·
`trn_` training · `rnd_` R&D · `demo_` demo · `tst_` uji sekali pakai · `erp_dev_` dev.

| Vertikal | Pelanggan | Database |
| --- | --- | --- |
| `levis` | PT ERA Busana Retailindo | `prd_levis_begbal` (produksi), `prd_levis_AP`, `prd_detail_levis`, `prd_levis`, `demo_updated_levis`, `rnd_levis` |
| `arkaaim` | ARKA-AIM | `prd_arkaaim`, `trn_arkaaim`, `trn_arkaaim_begbal`, dev `erp_dev_aimarka` |
| `wms` | Warehouse Management | `prd_wms` (internal), `demo_wms`, `rnd_wms` |
| `gw` | GentleWoman | `gentlewoman` (internal) |
| `ppob` / `esb` / `vaspmo` / `sandbox` | — | `rnd_ppob`, `rnd_esb`, `rnd_vas_pmo`, `demo` |

> **Jangan tertipu prefiks `prd_`.** Hanya `prd_levis_begbal` dan `prd_arkaaim` yang benar-benar
> produksi pelanggan. `prd_levis_AP` (uji AP), `prd_detail_levis` (detail GL) dan `prd_levis`
> (pra-begbal) adalah DB internal.

Jangan pernah mengenumerasi populasi DB dari dugaan penamaan: `datname LIKE '%levis%'`
melewatkan `tst_agedpay` yang memasang modul Levi's. Enumerasi lewat `ir_module_module` di
setiap DB, dan container lewat `docker inspect ... .Mounts`
(`opt-runtime-checkout-third-actor`).

---

## 4. Cara kerja wajib

### 4.1 Sebelum menyentuh DB produksi

**Selalu `pg_dump` segar lebih dulu** — bukan hanya untuk posting jurnal, tapi juga untuk
`-u <modul>`, migrasi, dan skrip data-fix, sekalipun perubahannya kelihatan aditif dan sudah
lolos canary. Ini permintaan eksplisit user 11-Agu-2026 setelah sebuah deploy aditif ke 10 DB
(5 produksi) dijalankan tanpa dump baru (`always-dump-before-touching-prod`).

Alasannya: dump malam (cron 02:30) bisa berumur sampai 24 jam. Memulihkannya berarti membuang
transaksi sehari penuh — jadi itu bukan opsi rollback yang nyata untuk DB yang dipakai orang.
Penilaian "risikonya rendah" tidak boleh menggantikan jaring pengaman.

### 4.2 `-u` (upgrade modul)

> **`Some modules are not loaded` bukan catatan kaki — itu artinya BERHENTI.**

Pelajaran mahal (`blanket-upgrade-loop-wrecked-tst-db`): sebuah loop `-u` ke *semua* DB yang
memasang satu modul menghancurkan `tst_levis_wms` — dari 1.067 tabel berisi data (dump 120 MB)
jadi **135 tabel / 22 MB**, `ir_module_module` jadi 14 installed / 831 uninstalled, dan
`account_move` **hilang**. Tidak ada `CRITICAL` maupun `Traceback` di output, sehingga loop-nya
melaporkan "errors=0".

Rambu yang terlewat: sehari sebelumnya `-u` ke DB yang sama sudah mencetak `Some modules are
not loaded ... ['custom_wms_base']`. Pesan itu berarti **graf modul DB itu rusak** — ada modul
tercatat installed tapi kodenya tak ada di disk. Menjalankan `-u` di atas graf seperti itu
membuat Odoo menyelaraskan state terhadap filesystem, dan dependant-nya ikut ter-uninstall
beserta tabelnya.

Aturan turunannya:

- Jangan `-u` massal ke DB `tst_*`/eksperimen yang isinya tidak Anda kenal.
- Menghitung `CRITICAL|Traceback` **bukan** gerbang sukses.
- Untuk `-u` multi-modul, "gagal = tidak ada yang berubah" **salah**: modul lain dalam
  perintah yang sama bisa sudah commit (`odoo19-server-action-group-ids`).

### 4.3 Setelah mengubah kode addon di `/opt`

Restart **semua** container Odoo yang melayani DB terdampak — `odoo`, `odoo-mgmt`, dan
`odoo-vaspmo` bila relevan. Merestart hanya `odoo` meninggalkan yang lain menjalankan Python
lama (`restart-both-odoo-containers`).

Gejalanya menipu: `-u` mendaftarkan menu/view/action baru sebagai **data**, jadi tombolnya
muncul di mana-mana seketika — tapi method Python-nya hidup di proses yang berjalan dan hanya
di-import ulang saat proses start. Hasilnya `AttributeError: The method '<model>.<method>'
does not exist` saat diklik, yang terbaca seperti bug kode padahal bukan.

Verifikasi dengan `odoo shell` **di dalam container spesifik** dan cek
`hasattr(model, "method")` — memeriksanya dari container lain tidak membuktikan apa pun.

### 4.4 Commit & pre-commit

`.pre-commit-config.yaml` ada dan CI menjalankannya sebagai job `lint`, tapi **tidak ada
`.git/hooks/pre-commit` yang terpasang** — jadi `git commit` tidak menjalankan apa pun secara
lokal (`pre-commit-not-installed-as-hook`).

```bash
pre-commit run --from-ref origin/main --to-ref HEAD
git add -A
```

Dua hook butuh `python` di PATH yang host ini tidak punya (hanya `python3`):
`module-knowledge-drift` dan apa pun dengan `language: system` + `entry: python ...`. Shim-nya:
`ln -sf "$(type -P python3)" <dir>/python` lalu prefiks PATH. Kegagalan "Executable `python`
not found" adalah masalah environment, bukan temuan nyata.

### 4.5 Bekerja di checkout yang dipakai bersama

Ada beberapa sesi Claude dan beberapa orang yang memakai `/home` **dan** `/opt` bersamaan.
Ini bukan teori — sudah terbukti berulang:

- 6-Agu-2026: sesi lain meng-commit pekerjaannya saat branch milik sesi ini ter-checkout,
  sehingga commit-nya mendarat di branch yang salah dan ikut tertelan squash-merge
  (`shared-checkout-concurrent-sessions`).
- 8-Sep-2026: branch `/home` berubah dari `feat/finance-cockpit` ke `feat/asset-lifecycle`
  dalam beberapa menit, dengan 8 commit belum di-push dan 158 file modified + 92 untracked.
  Memindahkan branch akan menghapus satu-satunya salinan.
- 11-Agu-2026: `/opt` ditemukan dengan 36 berkas ter-stage tanpa jejak reflog, karena
  `git checkout <sha> -- <path>` **menulis ke index tanpa memindahkan HEAD**
  (`opt-runtime-checkout-third-actor`).

Kebiasaan yang wajib:

1. Jalankan `git status --short | wc -l` **persis sebelum** bertindak, bukan di awal sesi.
2. Commit berumur menit = sesi hidup. Cek `git log -1 --date=iso` sebelum memindahkan branch.
3. Untuk commit saat `/home` melayang: `git worktree add --detach <path> origin/<branch>`,
   kerjakan di sana, push, `git worktree remove --force`. Jangan menarik checkout bersama
   kembali ke branch Anda.
4. Pakai `git -C <path>` untuk **setiap** perintah git saat menangani dua pohon — `cd $WT`
   bertahan sepanjang satu invokasi Bash, sehingga `git checkout -- <file>` yang dimaksudkan
   untuk `/home` bisa diam-diam mengembalikan isi worktree.
5. Satu-satunya jejak operasi index adalah `stat -c '%y' .git/index`.
6. Kalau melihat berkas ter-stage di path addon di `/opt`: verifikasi isinya vs `origin/main`,
   lalu **tanya sesi lain sebelum mengubah HEAD**. Menimpanya pernah menghapus keadaan yang
   sengaja disusun orang lain.

### 4.6 Versi manifest modul shared

Naikkan `version` di `__manifest__.py` setiap kali skema modul shared berubah — setiap tenant
memuat modul itu.

Dua arah jebakannya:

- **Jangan mengambil versi `main` untuk modul yang versi `/opt`-nya lebih tinggi.** Itu
  menurunkan versi di bawah yang sudah ada di DB, sehingga `-u` berikutnya **buta** dan tidak
  melihat upgrade (`opt-home-divergence-aug04`, `shared-addon-version-bump-drift`).
- **Modul bisa ter-merge ke `main` tapi tidak pernah disalin ke `/opt`.** `custom_pos_tax_id`
  (PR #191) begitu — ada di repo, foldernya tidak ada di runtime, jadi Odoo tak melihatnya dan
  tak bisa dipasang di DB mana pun. Setelah merge, **cek `/opt` punya foldernya**.

Kalau diff CSV/teks melaporkan 100% baris berubah sementara jumlah barisnya sama, **cek CR
dulu** sebelum menyimpulkan data divergen — `/opt` menyimpan ekspor klien apa adanya (CRLF),
`main` LF (`opt-home-divergence-aug04`).

### 4.7 Menavigasi repo ini dengan murah

Repo ini besar (~4.700 berkas ter-track, 158 addon, 2.000+ `.py`). Urutan pencarian yang
dianjurkan ada di `CLAUDE.md` dan tetap berlaku:

1. Knowledge graph `graphify-out/` — 20.738 node, 34.175 edge, 1.574 komunitas atas 2.805
   berkas, kode **dan** prosa (278 `.md`). **Celah: tidak ada ekstraktor `.xml`**, jadi ~1.006
   berkas view/data/security hanya bisa ditemukan lewat `git ls-files | grep`.
2. `addons/**/MODULE_KNOWLEDGE.md` — 123 dari 158 modul punya satu.
3. `git ls-files | grep <nama>` lalu `sed -n 'A,Bp'` pada bagian yang dicari.
4. Baca berkas penuh hanya saat akan menyunting.

`graphify-out/` **gitignored** (62 MB) — ia tidak datang lewat `git clone`. Membangun ulang
memerlukan `graphify extract . --backend claude-cli` dan memakan ~4 jam. Cara memasang ulang
CLI-nya ada di `README-ARSIP.md` dalam arsip pengetahuan.

---

## 5. Arsitektur repo

### 5.1 Tier modul

| Tier | Jumlah | Isi |
| --- | --- | --- |
| `addons/core` | 11 | primitif bersama; semuanya bergantung ke sini |
| `addons/ee_gap` | 108 | rebuild fitur Enterprise — bagian terbesar |
| `addons/operations` | 3 | monitor server, dev lifecycle, BRD analyzer |
| `addons/verticals` | 13 | 12 × `custom_ppob_*` + `custom_fnb_stock_ops` |
| `addons/compliance` | 9 | PDP UU 27/2022, Coretax, PPh witholding |
| `addons/control_plane` | 4 | super admin, tenant infra, hub console, onboarding |
| `addons/_tenants` | 11 | kode per pelanggan: `custom_arka_*` (7), `custom_levis_*` (4) |
| `addons/_vendor` | 4 | OCA — **jangan diedit**, tidak masuk graf |

**Jumlah yang terukur 28-Sep-2026** (diverifikasi, bukan dikutip): delapan tier di atas
berisi **163** modul, ditambah satu scaffold `verticals/_template/custom_vertical_example`
yang duduk di depth 4 — total **164 `__manifest__.py` di disk**. Ia satu-satunya manifest di
luar delapan tier itu, jadi `ls -d addons/<tier>/*/__manifest__.py` melewatkannya.

> **Angka modul di dokumen lain lebih kecil dan itu bukan salah ketik — repo bertambah.**
> Submission EAA 17-Sep menyebut **159 modul** dan catatan katalog fitur menyebut **158**
> dengan sebaran per tier yang berbeda (core 9, ee_gap 105, `_tenants` 10). Pakai angka
> hasil pengukuran hari itu, jangan mengutip angka lama sebagai keadaan sekarang. Di `main`
> jumlahnya lebih kecil lagi karena `custom_accounting_recurring_tax_id` dan
> `custom_approval_engine_budget` hanya ada di `/home` (`platform-feature-catalog`).

God node yang wajib dikenal sebelum menyunting apa pun:

| Node | Edge | Keterangan |
| --- | --- | --- |
| `RetailImportExecutor` | 105 | mesin impor X-file Levi's |
| `custom_pdp_audit` | 72 | log append-only ber-hash-chain |
| `PettyCashRequest` | 59 | petty cash |
| `custom_core` | 56 | mixin, kripto Fernet, helper HMAC |
| `LevisPosClearing` | 54 | clearing POS Levi's |

### 5.2 Aplikasi di akar repo

| App | Stack | Peran |
| --- | --- | --- |
| `finance-cockpit` | Next.js 15 + SQL langsung | dasbor FA Levi's di `/finance`, role `finance_ro` |
| `sales-cockpit` | Next.js 15 + Recharts | dasbor penjualan di `/cockpit`, role `cockpit_ro` |
| `login-gateway` | Next.js 15 | pintu depan: pemilih vertikal + environment |
| `hub-portal` | Vite 5 + React + Express | UI control plane internal |
| `tenant-orchestrator` | FastAPI + Python 3.12 | lifecycle tenant, backup ke MinIO/S3, HMAC |
| `ai-gateway` | FastAPI | gateway AI multi-provider |

Ditambah `vas-pmo`, `storefront`, `custom-predictor`, `services/baileys` (WhatsApp) dan
`services/finance-sap-bridge` (Kafka).

8 berkas compose: base, `.dev`, `.prod`, `.multitenant`, `.observability`, `.tls-acme`,
`.local-llm` — diorkestrasi lewat `Makefile` (~60 target, mulai dari `make help`).

> **Jebakan rebuild cockpit:** sumbernya **hanya di `/home`**, dan `/home` bisa basi.
> `/opt/odoo-platform/{finance,sales}-cockpit` **tidak ada**. Per 8-Sep lockfile di `/home`
> masih memuat postcss 8.4.31 / sharp 0.34.5, sehingga `docker compose build` dari `/home`
> membangun ulang kerentanan yang sama dan **terlihat sukses**. Jebakan ini ditutup 8-Sep
> dengan `git checkout origin/main --` pada tiga direktori cockpit; efek sampingnya 9 berkas
> tampak "modified" karena branch `/home` tertinggal dari main — **itu wajar, jangan
> di-revert** (`finance-cockpit-dashboard`).

### 5.3 Pipeline pengetahuan repo — pembeda cara kerja di sini

| Skrip | Fungsi |
| --- | --- |
| `scripts/generate_module_knowledge.py` | menulis `MODULE_KNOWLEDGE.md` lewat ai-gateway; lahir `status: draft`, dev mengubahnya ke `reviewed` |
| `scripts/check_knowledge_drift.py` | mode pre-commit warn-only; mode CI `--diff origin/main...HEAD` exit 1. Escape hatch: token `[knowledge-deferred]` di commit message |
| `scripts/gen_module_versions.py` | menegakkan aturan bump versi manifest, lewat `.github/workflows/check-module-versions.yml` |
| `scripts/check_inherit_deps.py` | menjaga `_inherit` selaras dengan `depends` |

Hanya 4 dari 129 dokumen knowledge yang `reviewed`; 111 masih draft generator
(`platform-feature-catalog`).

### 5.4 Skrip operasional

- `scripts/tenants/apply_updates.sh` — menyapu setiap DB tenant (`-u` + seed psql idempoten)
  di dalam container. Jalankan **setelah** `git pull` **dan** setelah restart container Odoo.
  Perhatikan `SKIP_DBS` bawaannya.
- `scripts/tenants/levis/` — 114 berkas bernomor `01_`…`1xx_`, ada `README.md` yang membedakan
  jalur ops (Track A) dari modul `custom_retail_import` (Track B).
- `scripts/tenants/arkaaim/` (50), `wms_demo/` (23), `wms_ecomm/` (9),
  `era_busana_retailindo/`.
- `scripts/ops/` — cron & guard: `pg_backup_all.sh`, `pg_backup_check.sh`,
  `nightly_disk_cleanup.sh`, `queue_job_uuid_guard.sh`, `retail_import_check.sh`,
  `kmk_rate_sync.sh`, `db-manager-tunnel.sh`.
- `scripts/security/` — `origin_lockdown.sh`, `refresh_cloudflare_ranges.sh`,
  `verify_front_door.sh`, `waf_triage.sh`.
- `scripts/chaos/` — mematikan postgres/redis/ai-gateway/orchestrator/pajakku, isi disk.

### 5.5 Dokumen yang sudah ada dan harus dibaca

- `docs/architecture.md` — peta operator: stack, service, tier modul, integrasi eksternal,
  topologi deploy (NOW single VPS vs TARGET split), alur data.
- `docs/runbooks/` — 14 runbook: `disaster-recovery.md`, `backup-restore.md`,
  `incident-postgres-down.md`, `incident-odoo-oom.md`, `odoo-high-cpu.md`, `postgres-slow.md`,
  `pajakku-down.md`, `tenant-data-recovery.md`, `front-door-hardening.md`,
  `database-manager-access.md`, `tls-renewal.md`, dan 3 catatan drill/upgrade bertanggal.
- `docs/sops/` — `tenant-onboarding.md` (green-light → login dalam ≤2 jam),
  `tenant-offboarding.md`.
- `docs/projects/README.md` — tabel otoritatif proyek ↔ pelanggan ↔ DB ↔ modul yang dimiliki.
- `docs/ee-gap/accounting-trio-runbook.md`, `docs/integrations/`, `docs/pdp-compliance.md`,
  `docs/coretax.md`, `docs/prod-deploy-checklist.md`, `docs/adding-vertical.md`.

---

## 6. Pintu depan, ingress & layanan latar

### 6.1 Login gateway

Akar `eal-hub.erajaya.com` **bukan lagi pemilih database Odoo** sejak 5-Agu-2026 — dulu itu
memaparkan daftar setiap database klien plus database manager ke publik
(`front-door-login-gateway`). Sekarang `login-gateway` memetakan (vertikal, environment) ke DB
**di sisi server**, membuat sesi Odoo yang sudah dipatok ke DB itu, lalu meneruskan browser ke
`/web/login`.

Dua pelajaran keamanan dari gerbang ini:

- **`/signin/versi` sekarang staf-saja (404 untuk selain staf).** Dulu ia memberi pengunjung
  anonim branch+commit platform, digest image dasar, versi Odoo/PostgreSQL/Python, dan daftar
  139 modul kustom lengkap nama teknis dan tanggal perubahan terakhir.
- **Cookie stafnya dulu bisa dipalsukan** — nilainya literal `"1"`, jadi `Cookie: lg_staff=1`
  tanpa kredensial apa pun membuka tampilan staf 354 KB berisi seluruh judul commit dan hash.
  Sekarang `<expiry>.<HMAC-SHA256(expiry, STAFF_KEY)>`, dicek constant-time, expiry ada di
  dalam payload bertanda tangan. **Merotasi `LOGIN_GATEWAY_STAFF_KEY` membatalkan semua
  unlock** — staf harus membuka `/signin?staff=<key>` sekali lagi per browser.

> **Men-deploy gerbang ini berarti REBUILD, bukan restart** — ia image Next.js.

### 6.2 Caddy: tiga jebakan yang wajib diketahui

**1. Bind mount Caddyfile memaku inode, bukan path** (`caddy-ingress-gotchas`).
`/opt/odoo-platform/caddy/Caddyfile` di-mount sebagai **satu berkas**. Setiap suntingan yang
*menggantikan* berkas itu — editor yang menulis-temp-lalu-rename, sebagian mode `sed -i`, dan
juga **`git pull` / `git reset --hard` di `/opt`** walau isinya identik — memberi inode baru,
dan container yang berjalan **tetap membaca inode lama, diam-diam**. Gejalanya menipu:
`caddy validate` dan `caddy reload` dua-duanya melaporkan sukses dan tidak ada yang berubah.
Mount-nya read-only, jadi `docker exec ... 'cat > /etc/caddy/Caddyfile'` gagal — satu-satunya
jalan ke inode baru adalah recreate. Urutan aman: **recreate dulu, baru sinkronkan git**, atau
bandingkan `md5sum` host vs container sesudah pull. Periksa dengan
`stat -c %i /opt/odoo-platform/caddy/Caddyfile` sebelum mempercayai reload apa pun.

**2. Recreate memakai definisi overlay SEKARANG, bukan definisi container yang jalan.**
5-Agu-2026 `docker compose up --force-recreate caddy` menurunkan ingress beberapa menit karena
empat drift (`caddy-recreate-overlay-drift`):

- overlay me-mount `./caddy/Caddyfile.multitenant` padahal yang melayani trafik adalah
  `./caddy/Caddyfile`;
- `ACME_EMAIL: ${ACME_EMAIL:-}` membuat variabel **terdefinisi tapi kosong**, sementara default
  `{$ACME_EMAIL:admin@localhost}` hanya berlaku kalau variabel *unset* → baris `email` tanpa
  argumen → parse error → crash-loop → ingress mati;
- port **8443 tidak ada di overlay**, jadi storefront TLS hilang diam-diam;
- `DOMAIN` tidak diteruskan, site block jatuh ke `localhost.localdomain`, dan Caddy menjawab
  **HTTP 200 dengan body KOSONG** (`"msg":"NOP"`, `"status":0`) sementara container tetap
  `healthy`.

> Poin terakhir itu jebakan verifikasi: **memeriksa kode status saja membuat situs mati
> terlihat sehat.** Selalu ukur `size_download` dan ikuti redirect, dan kirim host yang nyata.

**3. Jangan build image ini dengan `xcaddy`** dan jangan memuat ulang config lewat compose
recreate — pakai `docker restart odoo19-platform-caddy` (butir JANGAN 67–68).

### 6.3 Paparan jaringan host

Diaudit 3-Agu-2026 (`host-network-exposure`):

- **Tidak ada firewall cloud untuk diperiksa.** Host ini VMware on-prem/colocation; tidak ada
  metadata service AWS/GCP/Azure/DO yang menjawab.
- **Host tidak memegang alamat publik.** Hanya `192.168.3.140/23` di `ens160`.
  `curl ifconfig.me` melaporkan alamat publik, tapi itu alamat **egress NAT**, bukan alamat
  yang terikat ke mesin ini.
- **"ufw inactive" BUKAN temuannya.** Docker mempublikasikan port lewat DNAT di
  `nat PREROUTING`, yang jalan **sebelum** `filter INPUT` tempat aturan ufw berada — ufw yang
  aktif pun tidak akan memblokir port yang dipublikasikan Docker. Titik kontrol yang benar
  adalah chain **`DOCKER-USER`**, dan chain itu **kosong**, jadi setiap port yang
  dipublikasikan menerima `0.0.0.0/0`.

### 6.4 queue_job

**Hanya satu container Odoo yang boleh memuat `queue_job`.** 31-Jul-2026 tidak ada satu pun
queue job berjalan di database mana pun selama 24 jam karena **tiga** container punya
`queue_job` di `SERVER_WIDE_MODULES`, sehingga tiga job runner masing-masing membuka setiap DB
tenant dan berebut `pg_try_advisory_lock` per database. Runner yang kalah satu lock melempar
`MasterElectionLost`, menutup SEMUA koneksinya, dan mengulang `initialize_databases` — selamanya.
Satu runner asing yang menahan satu database menyandera seluruh platform
(`queue-job-runner-election-deadlock`).

> **Kegagalannya senyap:** `MasterElectionLost` dicatat di level DEBUG. **Diagnosis lewat
> ketiadaan, bukan lewat error.** Tanda sehat: `database connections ready` dan `asking Odoo to
> run job` muncul. Tanda sakit: `queue job runner ready for db …` berulang ratusan baris per
> menit sementara dua baris itu **tidak pernah** muncul.

Petakan pemegang lock dengan
`select count(*), count(distinct pid) from pg_locks where locktype='advisory'`, lalu
`pg_stat_activity.client_addr` → `docker inspect` IP. Query terakhirnya `SELECT 1` (keep-alive
runner). Perbaikannya sempat **hanya ada di host** sampai 4-Agu-2026 — git masih membawa
`SERVER_WIDE_MODULES: "base,web,queue_job"` pada `odoo-mgmt`, jadi siapa pun yang redeploy dari
git akan memasang ulang insidennya.

**Guard UUID ganda:** `scripts/ops/queue_job_uuid_guard.sh` + `/etc/cron.d/odoo-queue-job-guard`
(PR #124) jalan tiap jam di menit **:17**, ~15 detik, tidak menulis apa pun saat bersih
(`queue-job-uuid-guard-cron`). Pemicunya adalah **klon DB buatan tangan**, yang tidak bisa
dijaga oleh jalur kode mana pun — sudah kambuh empat kali (26-Jun, 6-Jul, 3-Agu, 10-Agu)
(`queue-job-duplicate-uuid-levis`). Sisi mana yang mempertahankan UUID: peringkat `prd_` >
`trn_` > `rnd_` > `demo` > sisanya, lalu nama — klon scratch selalu mengalah pada DB asalnya.
Ia **menolak alih-alih menebak**: UUID yang dirujuk baris lain (`graph_uuid`, atau di dalam
payload `dependencies`) dilewati, dilaporkan, exit 1, dan dikirim ke WhatsApp. Kasus itu
meninggalkan runner mati, jadi kesunyian di sana adalah hasil terburuk.

### 6.5 PDP audit — satu titik yang bisa meracuni seluruh request

7-Jul-2026 posting `account.move` di produksi gagal dengan
`InFailedSqlTransaction: current transaction is aborted`, dan traceback-nya menunjuk ke
pencarian withholding `custom_tax_id` — **itu ikan haring merah**; pencarian itu hanya panggilan
ORM pertama setelah transaksinya sudah teracuni (`pdp-audit-txn-poison-schema-drift`).

Akarnya dua lapis:

1. **Kode:** `pdp.audited.mixin._pdp_audit_write` menjalankan `cr.execute` INSERT mentah ke
   `pdp.audit_log` **tanpa savepoint**. Kegagalan di level DB tertangkap `try/except` (sehingga
   exception Python tertelan) tapi meninggalkan transaksi Postgres dalam keadaan aborted →
   setiap query sesudahnya di request itu mati. Diperbaiki dengan membungkus INSERT dalam
   `self.env.cr.savepoint(flush=False)`.
2. **Data:** DB yang dibuat **sebelum** bump skema punya `pdp.audit_log` basi —
   `action varchar(16)` dengan CHECK enum tertutup. Karena bootstrap memakai
   `CREATE TABLE IF NOT EXISTS`, tabel sempit yang sudah ada **tidak pernah dimigrasikan**.
   Setiap action lebih dari 16 karakter atau di luar enum gagal INSERT dan meracuni transaksi.

**Tiga salinan SQL harus tetap identik:** `postgres/init/02-pdp-schema.sql` (init cluster),
`data/02-pdp-schema.sql` addon (dibaca `pre_init_hook`, install-only), dan `data/pdp_schema.sql`
addon (dijalankan `PdpAuditLog.init()` pada **setiap** `-u`). Salinan `02` pernah menyimpang
sehingga fresh install membuat ulang bug-nya. Karena `init()` menjalankan `pdp_schema.sql` saat
upgrade, **`-u custom_pdp_audit` menyembuhkan sendiri DB yang skemanya basi.**

> **Pola yang harus diwaspadai untuk setiap klon:** `IF NOT EXISTS` tidak pernah memigrasi.

---

## 7. CI/CD & git

- Remote **GitHub adalah sumber kebenaran**: `github.com:sarangrumah/odoo-platform`.
  Mirror Bitbucket (`bitbucket.org:ademaryadi/…`) **dibekukan** di `139a627` (3-Agu-2026) dan
  sudah divergen permanen — **jangan di-merge, jangan force-push**
  (`git-remotes-github-bitbucket-split`).
- Konsekuensi: dari `/opt`, `git push` **exit 1 walau sukses** — ia mencetak
  `Everything up-to-date` untuk GitHub lalu `! [rejected]` untuk Bitbucket. Jangan pakai exit
  code sebagai verdict, dan jangan pipe lewat `tail`.
- Sebagian besar workflow dipicu `pull_request:` dengan filter `branches: [main, develop]`,
  dibaca dari **branch tujuan**. Untuk PR bertumpuk, push hanya menjalankan 2 drift check.
- **Mengalihkan basis PR ke `main` TIDAK memicu CI** — retarget menghasilkan event
  `pull_request` bertipe `edited`, sementara workflow menyimak
  `opened`/`synchronize`/`reopened`. Cara memicunya: **tutup lalu buka kembali PR-nya**
  (`ci-retarget-does-not-trigger`).
- `container-scan` mencakup 9 Dockerfile lewat `matrix.include`. Untuk menekan satu **paket**
  di trivy dibutuhkan Rego (`.trivy/ignore-policy.rego`), bukan `.trivyignore` — yang hanya
  mencocokkan ID kerentanan. Saat ini `linux-libc-dev` ditekan (~118 HIGH/CRITICAL dari header
  kernel C yang tidak dieksekusi); **cabut aturannya dan scan ulang saat base image dinaikkan**.
- trivy hanya melaporkan kelas temuan tertinggi per target, jadi **memperbaiki satu CVE bisa
  MEMUNCULKAN yang lain** dan check tetap merah. Jangan memprediksi scan akan hijau — build
  image-nya dan jalankan trivy sendiri.
- `hadolint` di pre-commit menjalankan container **tanpa pin**: rilis 2.15.1 memperketat DL3025
  sehingga CI memerah tanpa satu commit pun di repo. Sekarang di-pin per digest.

---

## 8. Backup & disaster recovery

Keadaan sekarang (`no-automated-tenant-db-backups`, `backup-verify-guard-and-wa-channel`):

- `scripts/ops/pg_backup_all.sh` — cron **02:30** lewat `/etc/cron.d/odoo-pg-backup`, menulis
  ke `/opt/db-backups/auto`. Ia mengenumerasi database **saat run**, jadi tenant yang
  di-provision kemudian ikut terlindungi malam pertamanya.
- Satu `pg_dump -Fc` per DB + `pg_dumpall --globals-only` (role; tanpa itu restore muncul
  tanpa owner). Minggu → `weekly/`, tanggal 1 → `monthly/`, lewat **hardlink**. Retensi 14
  harian / 8 mingguan / 6 bulanan. Ada `flock`, precheck ruang bebas, `.part`-lalu-rename.
- `scripts/ops/pg_backup_check.sh` — cron **07:05**, menurunkan verdict sendiri alih-alih
  mempercayai job dump, karena kegagalan yang mahal itu senyap: cron tak pernah jalan, disk
  penuh, dump terpotong.

Sejarah yang perlu diketahui: sebelum 4-Agu-2026 satu-satunya backup terjadwal adalah
`pgbackup-local` dengan `POSTGRES_DB=postgres` — DB master yang kosong. Ia jalan tiap hari,
melaporkan "SQL backup created successfully", dan menghasilkan ~1,5 KB ketiadaan setiap malam.
**Tidak ada satu pun DB tenant yang pernah ia backup.**

> Job hijau yang diam-diam tidak melindungi apa pun **lebih buruk** daripada tidak ada job —
> ia menghilangkan dorongan untuk mengambil backup yang sungguhan.

Dua hal yang jangan diubah:

1. Probe `pg_restore` **wajib** jalan di `docker run --rm -v "$day_dir:/b:ro"`. Host tidak
   punya `pg_restore`, dan memipa arsip format custom ke `docker exec` mengembalikan **nol**
   entri — setiap dump sehat akan dilaporkan korup.
2. **Jangan pernah hardlink dump nyata ke fixture uji.** `ln` + `>` memotong inode yang
   dipakai bersama; ini pernah menghancurkan `prd_levis_begbal.dump` yang asli. Pakai `cp`.

**Filestore SUDAH ikut sejak skrip diperluas — catatan lama yang mengatakan sebaliknya
sudah basi.** Diverifikasi 28-Sep-2026: `pg_backup_all.sh` men-`tar` filestore tiap DB
berdampingan dengan dump-nya sebagai `daily/<YYYYMMDD>/<db>-filestore.tgz`, dari
`FILESTORE_ROOT=/opt/odoo-platform/data/odoo-filestore/filestore`. Bukti di disk:
`/opt/db-backups/auto/daily/20260928/` memuat **44 berkas = 23 dump + 20 filestore tgz +
`globals.sql`**, total 1,6 GB; log run 07:05 mencatat `OK — 23 dump, 20 filestore, 1,6G`.
Tiga DB tidak punya direktori filestore, jadi dilewati — itu normal, bukan kegagalan.

Dua detail yang perlu diketahui:

- **`tar` keluar dengan rc=1 kalau Odoo menulis ke filestore saat dibaca.** Skrip
  memperlakukan rc=1 sebagai sukses dan mencatat "files changed during read" — jangan
  "perbaiki" itu menjadi gagal.
- **Prune-nya asimetris dan disengaja:** hanya `*-filestore.tgz` yang dibuang dari direktori
  daily yang lebih tua; dump-nya tetap. Jadi retensi dump lebih panjang daripada retensi
  lampiran.

Yang **masih** benar-benar tidak terlindungi:

- **`dropdb` tidak menghapus `data/odoo-filestore/filestore/<db>`.** Setiap DB yang pernah
  dihapus meninggalkan lampirannya di disk. Drop lewat database manager Odoo menghapus
  filestore sekalian; backup format Odoo (zip) memuat keduanya.
- **WAL archiving belum dipasang, jadi RPO nyata 24 jam.**
  `docs/runbooks/disaster-recovery.md` **bertentangan dengan dirinya sendiri**: header baris 4
  menulis `**RPO**: 1 hour (daily full backup + WAL archiving 1h)`, sementara baris 153–154 di
  badan dokumen sudah mengoreksi bahwa *"Current effective RPO is 24h until WAL archiving
  lands in Phase 3."* Yang dibaca orang adalah header-nya. Perbaiki header itu, atau pasang
  WAL archiving.

Pembersihan disk malam: cron 03:30 (`nightly-disk-cleanup`). Host pernah 84% penuh; tiga
penumpuk terbesar adalah build cache buildkit (36,5 GB), filestore yatim (1,0 GB, 60 folder)
dan journald (0,9 GB).

---

## 9. PR terbuka per 28-Sep-2026 (18 buah)

| # | Branch | Dibuka | Judul |
| --- | --- | --- | --- |
| 264 | `feat/levis-x70t-settlement` | 26-Sep | settle tender kartu yang berhenti dilaporkan X70D |
| 263 | `feat/levis-cogs-autopost` | 25-Sep | COGS catch-up sampai jurnal posted, tanpa user |
| 262 | `feat/levis-store-day-cash-matching` | 21-Sep | pisahkan uang kartu dan kas store-day |
| 254 | `feat/grir-match-ppn-correction` | 17-Sep | cocokkan jurnal koreksi PPN ke receipt-nya |
| 243 | `feat/levis-new-stores-sept2026` | 16-Sep | 9 toko Sulawesi/Kalimantan ke store map |
| 233 | `feat/ic-mirror-auto-confirm` | 8-Sep | rule mengonfirmasi mirror SO sendiri |
| 226 | `feat/ppob-node` | 7-Sep | node provisioning PPOB/PPS di server terpisah |
| 216 | `fix/arkaaim-currency-and-income-accounts` | 7-Sep | pricelist currency membajak SO; kategori NULL meracuni invoice |
| 179 | `feat/arkaaim-kmk-rates` | 19-Agu | kurs pajak KMK + cron mingguan |
| 175 | `fix/arkaaim-user-fiqo` | 18-Agu | akun user yang tertunda sejak 7-Agu |
| 173 | `fix/arkaaim-payment-direct-to-bank` | 18-Agu | pembayaran ARKA langsung ke bank |
| 171 | `docs/arkaaim-issue-sheet-aug2026` | 18-Agu | klaim sheet go-live vs isi database |
| 137 | `docs/ppob-implementation` | 11-Agu | paket dokumen implementasi PPOB |
| 70 | `feat/industry-packs` | 24-Jul | sheet post-go-live: laporan PPh/PPN, journal billing |
| 59 | `feat/levis-gr-journal` | 16-Jul | retail import, localization, report gap, rental fix |
| 55 | `feat/levis-ou-normalization` | 9-Jul | normalisasi OU ke EBR + 20 toko |
| 54 | `feat/levis-manual-bill-payment-ou` | 8-Jul | manual-bill Trade/OU, field payment |
| 37 | `feat/arkaaim-numbering-ppn` | 25-Jun | numbering per company + PPN quotation |

> **Umur PR itu bermakna.** #37 dan #54/#55 sudah terbuka sejak Juni–Juli 2026. Jangan
> asumsikan PR lama aman di-merge: beberapa **akan me-revert kode yang sedang jalan** karena
> versinya di bawah yang sudah ada di DB. Lihat daftar JANGAN butir 29–30.

Yang khusus perlu diketahui:

- **PR #177 dan #197 akan me-revert kode live kalau di-merge apa adanya.**
- **Empat PR T00 (#199/#200/#201/#202)** juga di bawah versi live.
- **PR #116 jangan dibuka kembali.** **#215** duplikat dari #218 dan harus ditutup.
  **#55** ditutup setelah #44.
- **PR #263 mendarat dengan saklarnya MATI** — jangan menyalakannya selama FA hold berlaku.
- **Jangan menghapus branch `levis-ou-base` selama PR #55 terbuka** — itu memaksa PR-nya
  tertutup.

---

## 10. Jebakan API Odoo 19

Ini yang paling sering menghabiskan waktu. Semuanya sudah terbukti di platform ini.

### 10.1 Yang gagal SENYAP

- **`_sql_constraints` tidak lagi dihormati.** Odoo 19 hanya mencatat `WARNING ... no longer
  supported` dan **tidak membuat constraint apa pun** — `pg_constraint` tetap kosong, duplikat
  masuk. Pakai `models.Constraint("unique(a, b)", "pesan")` sebagai atribut kelas; nama
  constraint jadi `<tabel>_<namaatribut>`. **Selalu verifikasi**
  `SELECT conname FROM pg_constraint WHERE conrelid='<tabel>'::regclass;` — jangan percaya log
  upgrade yang bersih. Pembersihan seluruh repo selesai 29-Jul-2026: 55 deklarasi di 50 berkas
  / 30 modul, 96/96 constraint terbukti aktif (`odoo19-sql-constraints-ignored`).
- **Domain optimizer menormalkan `=`/`!=` jadi `in`/`not in` SEBELUM** method `search=` sebuah
  field non-stored dipanggil. Method yang ditulis `if operator in ("=", "!=", ...)` karena itu
  **tidak pernah** masuk cabangnya, SQL keluar dengan nilai tak diterjemahkan, dan `search()`
  mengembalikan recordset kosong **tanpa error**. Nilainya bisa list, set, atau **OrderedSet** —
  uji dengan `isinstance(value, str) or not hasattr(value, "__iter__")`
  (`odoo19-search-method-gets-in-operator`).
- **`safe_eval` maksimal 2 argumen posisional.** Bentuk lama 3-posisional melempar `TypeError`
  yang pernah **ditelan `except` defensif** di engine `custom_wms_putaway`, sehingga **setiap
  rule putaway berbasis domain memberi skor 0 dan tidak menempatkan apa pun, senyap, di setiap
  DB Odoo 19**. Ketahuan 22-Jul-2026 hanya karena ada test baru (`odoo19-api-drift-stock-users`).
- **`account.account.code` company-dependent** — tersimpan per company di kolom JSONB
  `code_store`. Membaca `acc.code` untuk akun milik company lain mengembalikan **kosong**.
  Hanya `code` yang terpengaruh; `name`, `account_type`, `reconcile` tetap shared. Ini yang
  memunculkan "TB ARKA kosong". Selalu `.with_company(...)` sebelum membaca. QWeb PDF juga
  kena: report dirender di bawah company **user**, bukan `o.company_id` — polanya
  `o.with_company(o.company_id).line_ids…` (`odoo19-company-dependent-account-code`).
- **`res.currency._get_rates` mengurutkan `company_id.id, name DESC` dengan `limit=1`.** Karena
  `company_id` diurut lebih dulu dan menaik, baris ber-`company_id` **selalu** menang atas baris
  shared (NULL) **tanpa memandang tanggal**. Satu baris kurs company-scoped bertanggal lama
  membajak seluruh tanggal sesudahnya untuk company itu. Obatnya: **hapus baris company-scoped**
  itu — jangan diduplikasi per company (`odoo19-company-rate-shadows-shared`).
- **`button_draft()` tidak lagi memanggil `remove_move_reconcile()`.** Reset pembayaran yang
  sudah ter-rekonsiliasi ke draft, dan baris `account_partial_reconcile` **bertahan**: tagihan
  tetap `amount_residual = 0` dan `payment_state = paid`, sementara pembayarannya draft dan
  karena itu **di luar Trial Balance**. TB dan Aged Payable lalu berbeda tepat sebesar itu,
  tanpa terlihat. Ini **akar tunggal** seluruh keluhan aged-payable Juli Levi's
  (`odoo19-button-draft-keeps-reconciliation`).
- **Tidak ada `_run_fifo_vacuum` di Odoo 19.** `stock.move.value` adalah `Monetary` stored biasa
  yang ditulis sekali di `_action_done`. Move keluar FIFO atas stok kosong dinilai
  `quantity * standard_price` (= 0 bila harga belum diketahui) dan **tidak pernah dinilai
  ulang** saat penerimaan datang. Konsekuensinya untuk Levi's: COGS **tidak bisa** diakui saat
  penjualan. Akun valuasi juga pindah ke `stock.location.valuation_account_id`, dan semua 156
  lokasi di DB Levi's punya itu kosong, sehingga core `stock_account` **tidak memposting apa
  pun** — itu sebabnya `custom_levis_localization` membuat GR journal sendiri
  (`odoo19-no-fifo-vacuum-cogs`).

### 10.2 Yang gagal KERAS tapi pesannya menyesatkan

- **`ir.actions.server.groups_id` → `group_ids`.** Kegagalannya terjadi saat memuat berkas
  data, jadi yang gagal adalah **pemuatan registry seluruh database** — `-u` berakhir
  `CRITICAL: Failed to initialize database` exit 255. Transaksinya di-rollback, tapi modul lain
  dalam `-u` yang sama bisa sudah commit. Grep `name="groups_id"` di `**/data/*.xml` sebelum
  deploy modul yang menambah server action (`odoo19-server-action-group-ids`).
- **`res.groups.category_id` → `privilege_id`, `users` → `user_ids`.** Modul dengan nama lama
  tetap **upgrade mulus** karena `security.xml` biasanya `noupdate="1"`, jadi bug-nya
  bersembunyi sampai ada **fresh install** yang mati dengan `ValueError: Invalid field
  'category_id'` (`odoo19-res-groups-and-test-commit`).
- **`res.users.groups_id` → `group_ids`**; `stock.move.name` **hilang** (pakai `reference` /
  `description_picking`); `stock.location.comment` **hilang**;
  `stock.location.scrap_location` **hilang**.
- **View inheritance tidak boleh memakai `string` sebagai selector** — jangkarkan ke
  `//field[@name='...']`. `<search string="...">` dan `<group expand="0" string="Group By">`
  gagal validasi RNG; pakai `<search>` dan `<group>` polos.

### 10.3 Laporan PDF

- **Setiap wrapper QWeb wajib memuat elemen `<main>`.** `_prepare_html()` melakukan
  `root.xpath('//main')[0]`, jadi wrapper tanpa `<main>` melempar `IndexError` saat print dan
  muncul sebagai RPC_ERROR (`odoo19-report-wrapper-needs-main`).
- **`<head>` dibuang.** `_prepare_html` hanya menyimpan **anak-anak `<main>`**. Jadi blok
  `<style>` di `<head>` hilang (laporan tercetak tanpa gaya, dan tidak ada yang sadar karena ia
  tetap tercetak) dan `<meta charset="utf-8">` hilang (wkhtmltopdf jatuh ke latin-1 → setiap
  karakter non-ASCII jadi mojibake). **Pindahkan `<style>` dan `<meta charset>` menjadi anak
  pertama `<main>`** (`odoo19-report-head-dropped`).
- **Report lambat** karena wrapper `web.html_container` membuat wkhtmltopdf menarik bundel aset
  lewat callback HTTP `report.url`/`web.base.url` — di deployment ini itu TLS round-trip ke IP
  publik lewat Caddy pada setiap print. Obatnya wrapper self-contained dengan CSS inline; hasil
  ~2,5–3 detik. Pelengkapnya: set `report.url=http://localhost:8069` sebagai
  `ir.config_parameter` per DB (`odoo19-slow-pdf-report-callback`).

### 10.4 Shell, psql, dan log

- **`psql -c` exit 0 walau statement-nya error**, kecuali diberi `-v ON_ERROR_STOP=1`. Pernah
  membuat seluruh rangkaian uji jalan di atas DB **kosong** sisa run yang dibunuh, dengan Odoo
  mencatat `0 failed, 0 error(s) of 0 tests` yang sekilas terbaca lulus
  (`psql-c-exit-zero-on-sql-error`).
- **`UserError` yang di-`except` TIDAK membatalkan INSERT sebelumnya** — record yang "ditolak"
  tetap hidup di transaksi. Bungkus dengan `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`.
- **`env.invalidate_all()` melakukan flush dulu** (`flush=True` default), sehingga dipanggil
  setelah rollback ia menulis balik nilai compute hantu. Pakai **`env.clear()`**
  (`odoo19-shell-invalidate-all-flushes`).
- **Peringatan Python mirip traceback.** Odoo 19 mencatat warning lewat `py.warnings` beserta
  import stack-nya; dipotong `tail`, yang tersisa adalah deretan `File "...", line N, in
  <module>` tanpa baris exception — karena memang tidak ada exception. Python mencetak tiap
  warning **sekali per proses**, jadi "tidak bisa direproduksi" bukan bukti sightings pertama
  itu kebetulan (`odoo19-warning-looks-like-traceback`).

### 10.5 Stok

- **`stock.rule` yang menghalangi hapus warehouse biasanya ter-ARSIP** (`active=False`),
  sehingga `search([...])` polos mengembalikan `[]` dan penghalangnya tampak tidak ada. Selalu
  lihat dengan `.with_context(active_test=False)`. Urutan hapus warehouse yang benar:
  transaksi → quant **per produk, bukan per lokasi** → lot → produk → `stock.rule` → warehouse
  → route milik warehouse itu **by id** (jangan "route milik warehouse ini", karena itu juga
  mencocokkan route global **Buy**) → lokasi terakhir
  (`odoo19-archived-rules-block-warehouse-delete`).
- **"Pensiun di repo" tidak berarti "redundan di setiap tenant."**
  `custom_stock_delivery_report_fix` dipensiunkan (`installable: False`) tapi masih
  `state='installed'` di `gentlewoman`, dan di DB itu ia satu-satunya yang menahan
  AttributeError pada delivery slip. Render yang "terlihat normal" **bukan** bukti patch-nya
  redundan — periksa apakah jalur berisikonya memang pernah dilewati
  (`retired-module-still-loadbearing`).

---

## 11. Lubang yang harus diberitahukan terus terang

1. **Knowledge graph tidak punya ekstraktor `.xml`** — ~1.006 berkas view/data/security tidak
   masuk graf dan hanya bisa ditemukan lewat `git ls-files | grep`.
2. **35 dari 158 modul belum punya `MODULE_KNOWLEDGE.md`**, dan hanya 4 dari 129 yang
   `reviewed`.
3. **`pre-commit` bukan git hook** — harus dijalankan manual.
4. **WAL archiving belum dipasang: RPO nyata 24 jam.**
   `docs/runbooks/disaster-recovery.md` bertentangan dengan dirinya sendiri — header-nya
   menulis 1 jam, badan dokumennya sudah mengoreksi ke 24 jam. Header-nya yang dibaca orang.
5. **`tenant-orchestrator/app/routers/vps.py` + `provisioner_ssh.py` sengaja tidak
   diregistrasi** di `app/main.py` (distub `PLATFORM_DEMO_MODE`).
6. **`custom_ai_bridge` menandatangani lewat helper HMAC `custom_core`**, bukan adapter
   framework — inkonsistensi yang sudah diketahui.
7. **`docs/platform-feature-catalog/` ada di disk tapi tidak ter-track git.**
8. **Kode produksi berjalan dari branch PR yang belum di-merge.** Diverifikasi 28-Sep-2026:
   `custom_levis_mdr` (19.0.1.0.0, terpasang di `prd_levis_begbal`) dan
   `scripts/tenants/levis/126_seed_cogs_charge_manual.py` **tidak ada di `main`** maupun di
   pohon kerja `/home` — keduanya hanya terjangkau dari branch **PR #264** dan **PR #263**
   yang masih terbuka. Dan `custom_levis_localization` di `/home` ada di **19.0.1.41.0**
   sementara `/opt` menjalankan **19.0.1.63.0** — 22 versi minor tertinggal. Artinya: menutup
   salah satu PR itu tanpa merge meninggalkan kode produksi tanpa rumah di `main`, dan `-u`
   dari worktree gagal untuk `prd_levis_begbal` karena worktree tidak punya modulnya.
9. **Deck `docs/presentation-erajaya-vas.md` masih menyebut 82 modul — basi.**
10. **`ANTHROPIC_API_KEY` di `.env` kosong**, jadi jalur fallback asisten cockpit tidak bisa
   diuji end-to-end di host ini.
11. **Tidak ada peringatan yang sampai ke manusia.** Diverifikasi 28-Sep-2026:
    `/opt/odoo-platform/.env` memuat **dua flag yang bertentangan** —
    `ALERT_WHATSAPP_ENABLED=true` di baris 173 dan **`ALERT_WHATSAPP_DISABLED=1` di baris
    221**. Kill switch-nya menang, bukan karena urutan baris tapi karena jalur kodenya:
    keempat skrip guard (`pg_backup_check.sh`, `retail_import_check.sh`,
    `queue_job_uuid_guard.sh`, `kmk_rate_sync.sh`) memeriksa flag `DISABLED` lebih dulu dan
    langsung mencatat "dimatikan sementara" ke log. Perhatikan juga skrip membaca
    **`/opt/odoo-platform/.env`**, bukan `.env` di `/home` — mengubah yang salah tidak
    berpengaruh. Ditambah baileys `acct-2` logged out. Ini yang paling mendesak.

---

## 12. Daftar JANGAN (Bahasa Indonesia)

Ini kumpulan larangan yang sudah dibayar dengan insiden nyata. Diurut per tema.

### 12.1 Git & checkout

1. **Jangan commit dari working tree `/home`.** Pakai worktree dari `origin/main`.
2. **Jangan `git pull` / `reset --hard` / `stash` / `clean` di `/opt`.** Pakai
   `reset --mixed|--soft`, atau `git checkout <sha> -- <path>`, dan buktikan dengan md5
   seluruh pohon `addons/`.
3. **Jangan rsync atau `cp -r` seluruh pohon addon ke `/opt`** — itu menghapus
   `custom_report_inline_assets` (terpasang di produksi, tidak ada di riwayat git mana pun)
   dan pekerjaan uncommitted lain. Salin per berkas dari `git diff --name-only`.
4. **Jangan anggap versi manifest yang sama berarti berkasnya sama.** Diff.
5. **Jangan pindahkan atau reset branch di checkout bersama** tanpa membaca ulang
   `git status -sb` dan `git log -1 --date=iso` persis sebelumnya.
6. **Jangan `git add -A` di `/home`**, dan jangan regenerasi `versions.json` dari `/home`.
7. **Jangan `git checkout origin/main --` pada
   `custom_asset_from_receipt/wizard/asset_conversion_wizard.py` di `/opt`** — itu mematikan
   Convert-to-Assets pada GR Non-Trade ARKA.
8. **Jangan pakai exit code `git push` dari `/opt` sebagai verdict**, dan jangan pipe lewat
   `tail`. Jangan merge atau force-push mirror Bitbucket.
9. **Jangan hapus branch `levis-ou-base` selama PR #55 terbuka.**
10. **Divergensi `.gitignore` antara `/opt` dan `main` DISENGAJA dan permanen — jangan
    "diperbaiki".** Empat CSV detail ARKA harus tetap **ter-track**.

### 12.2 Compose & container

11. **Jangan `docker compose up/down` dari `/home`.** `sales-cockpit`/`finance-cockpit` satu-satunya
    pengecualian, dan tetap butuh `--no-deps` + `docker rm -f` container tanpa label.
12. **Jangan hilangkan `--no-deps`**, dan jangan hilangkan berkas compose kedua.
13. **Jangan recreate container caddy** tanpa lebih dulu memeriksa drift mount / DOMAIN /
    ACME_EMAIL / 8443 dan membandingkan Caddyfile yang berjalan dengan berkas di host.
14. **Jangan `docker restart caddy` mengharap perubahan config mendarat** (mount satu-berkas =
    inode terpaku); jangan percaya `caddy validate`/`reload` yang dijalankan **di dalam**
    container yang berjalan.
15. **Jangan arahkan `CADDY_IMAGE` balik ke `caddy:2-alpine`** sebagai rollback.
16. **Jangan `docker image prune -a`**, dan jangan prune tag `rollback-*` / `cand-*` / `:recon`.
17. **Jangan muat `queue_job` di lebih dari satu container Odoo.**
18. **Jangan publikasikan port debugging di `0.0.0.0`**, dan jangan jadikan "ufw inactive"
    sebagai kontrol — pakai `DOCKER-USER`.
19. **Jangan aktifkan `tls client_auth` di Caddy** sebelum Authenticated Origin Pulls menyala di
    Cloudflare. Lihat juga butir **67–68** untuk larangan build image dan restart Caddy.

### 12.3 Upgrade & deploy

20. **Jangan `-u` DB produksi tanpa `pg_dump` segar** — termasuk upgrade yang "murni aditif".
21. **Jangan loop `-u` ke "semua DB yang punya addon ini"**, dan jangan `-u` DB
    `tst_*`/eksperimen yang tidak Anda kenal. **`Some modules are not loaded` = BERHENTI.**
22. **Jangan salin perubahan penambah field ke `/opt` sebelum setiap DB yang memasangnya
    di-`-u`.** Skema dulu, kode kemudian.
23. **Jangan arahkan field di addon shared ke model di luar `depends`-nya** — comodel yang
    hilang merusak **seluruh** registry.
24. **Jangan asumsikan "`-u` gagal = tidak ada yang berubah"** untuk `-u` multi-modul.
25. **Jangan `-u` dari worktree untuk DB yang memuat modul khusus `/opt`** — pakai
    `docker exec` pada container yang me-mount `/opt`.
26. **Jangan upgrade `custom_wms_putaway` dan `custom_wms_hht` dalam satu `-u`** di `rnd_wms`.
27. **Jangan pasang `custom_arka_aim_asset_register` di `trn_arkaaim`**, dan jangan biarkan
    modul `ee_gap/` bergantung pada modul `_tenants/`.
28. **Jangan pasang `custom_payment_admin_fee` berbarengan `custom_levis_localization`.**
29. **Jangan merge PR #177 atau #197 apa adanya** (me-revert kode live). Jangan merge empat PR
    T00 (#199/#200/#201/#202) apa adanya. Jangan buka kembali **#116**. Tutup **#215**
    (duplikat #218) dan **#55** (setelah #44).
30. **Jangan merge PR #216 / membuat akun `1103000002`, `9990000001`, `9990000002` di ARKA
    company 1** sebelum user memberi lampu hijau.
31. **Jangan selesaikan konflik pyOpenSSL dengan versi 25.x** — itu diam-diam menurunkan
    `cryptography`.
32. **Jangan pasang `custom_accounting_recurring_tax_id` di `/opt`.**

### 12.4 Data & akuntansi

33. **Jangan `TRUNCATE … CASCADE` tabel transaksi** — itu menghapus seluruh DB lewat
    `res_company.account_opening_move_id`.
34. **Jangan backdate koreksi ke periode yang sudah dilaporkan ke klien.** Pisahkan tanggal
    pembukuan dari tanggal pengukuran. Kalau sudah diposting dan masih segar: **hapus, jangan
    reverse** — dan hanya bila 0 rekonsiliasi menempel dan ia memegang nomor terakhir sequence.
35. **Jangan posting draft COGS catch-up sebelum skrip 126 dijalankan**, dan **jangan majukan
    `l10n_cogs_reported_through` sebelum COGS periodenya lengkap**.
36. **Jangan bukukan ulang COGS Juli Levi's**, dan jangan reverse Rp 1.116.818 di Agustus.
37. **Jangan jalankan `levis.cogs.run` untuk periode yang sudah dibukukan manual** tanpa
    menyemai `levis.cogs.charge` lebih dulu.
38. **Jangan pakai `stock_move.value` atau `standard_price` sebagai basis harga COGS** — pakai
    harga PO net pajak.
39. **Jangan nyalakan saklar COGS apa pun selama FA hold berlaku** (`autopost` menembus hold
    itu, bukan cuma cron-nya).
40. **Jangan proses perbaikan data besar dalam satu transaksi di produksi** (pernah 22 menit
    row lock).
41. **Jangan perbaiki `owner_id` pada baris stok `done` lewat ORM/UI** — SQL mentah dalam
    `REPEATABLE READ`.
42. **Jangan `unlink` quant lewat ORM untuk memperbaikinya** — pakai SQL, dan selalu jumlahkan
    `reserved_quantity` juga.
43. **Jangan hapus draft invoice id 277 di `prd_arkaaim`** — memposting-nya adalah obatnya.
44. **Jangan tulis field event di HEADER invoice pelanggan** (itu menyetel ulang payment
    terms); tag di baris jurnal. Jangan tulis analytic event lewat SQL.
45. **Jangan balik `is_storable` sebuah produk** tanpa mengukur write-off on-hand lebih dulu.
46. **Jangan cabut enam baris `account.lock_exception` permanen di `prd_levis_begbal`**, dan
    jangan perlakukan itu sebagai temuan.
47. **Jangan cabut `base.group_system` tanpa `base.group_erp_manager`, dan jangan lewat SQL.**
    Jangan cabut hak admin di `prd_levis_AP`.
48. **Jangan restore snapshot `*_bak_20260709`** tanpa menerapkan ulang perbaikan XMLID
    tax-group e-Faktur.
49. **Jangan SUM baris `x70d_store` langsung** (berkas mingguan kumulatif), dan jangan andalkan
    dedup SHA256 untuk itu.
50. **Jangan tandai impor yang dibatalkan guard sebagai `failed`** — pakai `cancelled`, kalau
    tidak monitor malam akan berteriak selamanya.
51. **Jangan biarkan feed/mailbox aktif di klon DB produksi.**
52. **Jangan isi lock date ARKA dari shell** (klien menolak) dan jangan ekspos `hard_lock_date`
    di wizard.
53. **Jangan pisahkan GR/IR ARKA/Levi's berdasarkan related party.**
54. **Jangan terbitkan FK untuk tenant retail** (pakai digunggung).
55. **Jangan "koreksi" MDR QRIS BCA/BNI/BRI menjadi 0,7%** — 0% sudah dikonfirmasi.
56. **Jangan restore `rnd_ppob` ke node PPOB baru** — bangun DB baru.
57. **Jangan hidupkan kembali `pgbackup-local`** atau mengaktifkan `pg-backup-s3` apa adanya.
58. **Jangan hardlink dump nyata ke fixture uji.** Jangan verifikasi dump dengan `pg_restore`
    di host.
59. **Jangan drop DB tanpa mengarsipkan filestore-nya dalam satu tarikan napas.**
60. **Jangan coba "perbaiki" atau restore `/opt/odoohub`.**

### 12.5 Aplikasi & pelaporan

61. **Jangan tambahkan panggilan LLM ke engine rekomendasi cockpit** — setiap kalimat sengaja
    template dari agregat SQL supaya nol biaya inferensi dan hasilnya deterministik. Jangan
    tinggalkan angka pasar placeholder, dan jangan lepaskan cap fair-share.
62. **Jangan jalankan prettier di `login-gateway/`.**
63. **Jangan longgarkan `dbfilter` instance publik.**
64. **Jangan `sudo claude` tanpa `-H`.**
65. **Jangan laporkan sebagai cacat:** `curl -F` 500 di `/signin`, `size=0` 200 dari
    `127.0.0.1`, `/websocket` 404, atau stack `py.warnings`.
66. **Jangan tawarkan solusi yang datanya belum Anda buka sendiri — di KEDUA sisi.**

### 12.6 Tambahan

Empat butir ini ditambahkan 28-Sep-2026 setelah audit silang menemukan larangan yang belum
tertulis. Nomornya melanjutkan urutan supaya rujukan ke butir lama tetap sah.

67. **Jangan pakai `xcaddy build` untuk image Caddy ini.** Build pertama lewat xcaddy gagal
    dan bukan jalur yang dipakai sekarang (`front-door-waf-hardening`).
68. **Jangan `docker compose recreate` container Caddy untuk memuat ulang konfigurasi** —
    pakai `docker restart odoo19-platform-caddy`. Inode mount-nya sama, sehingga recreate
    membawa risiko drift yang tidak perlu (`front-door-websocket-broken`).
69. **Jangan ubah `include_untagged` di produksi** sampai ada instruksi baru — keputusan user
    12-Agu-2026. Modul roles/OU di `/opt` disalin dengan `cp -a`, jadi **jangan `git pull`**
    untuk memperbaruinya. Dan saat mengaudit keanggotaan grup, **jangan menghitung
    `res_groups_users_rel` saja** — angkanya hasil pemberian massal, bukan cerminan modul
    (`roles-and-operating-unit-modules`).
70. **Enam baris `account.lock_exception` di `prd_levis_begbal` jangan dicabut, jangan diberi
    `end_datetime`, dan jangan dilaporkan sebagai temuan** — user menyatakan pemegangnya
    memang punya otoritas itu (`lock-exception-defeats-lock-date`). Ini menegaskan butir 46.

> **Satu larangan sengaja TIDAK dibawa ke dokumen ini:** `memory-index-byte-budget` mengatur
> cara memelihara indeks catatan Claude Code itu sendiri (jangan hapus berkas topik, jangan
> jatuhkan tautan, mampatkan teks bukan tautannya). Ia kehilangan makna begitu catatannya
> diarsipkan dan dihapus, jadi tidak relevan bagi penerus.

---

## 13. Do-not-do list (English)

Same list, condensed, for a reader who does not read Indonesian.

**Git and checkouts.** Never commit from the `/home` working tree — use a worktree off
`origin/main`. Never `git pull`, `reset --hard`, `stash`, or `clean` in `/opt`. Never rsync or
`cp -r` a whole addon tree into `/opt` (it deletes `custom_report_inline_assets`, which is
installed in production and in no git history). Equal manifest versions do not mean equal
files — diff them. Never move or reset a branch in a shared checkout without re-reading
`git status -sb` and `git log -1 --date=iso` immediately first. Never `git add -A` in `/home`.
Never treat `git push` exit code from `/opt` as the verdict, and never merge or force-push the
Bitbucket mirror. The `.gitignore` divergence between `/opt` and `main` is deliberate and
permanent — do not "fix" it.

**Compose and containers.** Never run `docker compose up/down` from `/home`; the two cockpits
are the only exception and still need `--no-deps` plus an explicit `docker rm -f`. Never omit
`--no-deps` or the second compose file. Never recreate Caddy without checking mount, DOMAIN,
ACME_EMAIL and 8443 drift first, and never trust `caddy validate`/`reload` run inside the
running container. Never `docker image prune -a`, and never prune `rollback-*` tags. Never
load `queue_job` in more than one Odoo container. Never publish a debugging port on
`0.0.0.0`. Never enable Caddy `tls client_auth` before Authenticated Origin Pulls is on in
Cloudflare.

**Upgrades and deploys.** Never `-u` a production database without a fresh `pg_dump`, including
"purely additive" upgrades. Never loop `-u` over "all DBs with this addon", and never `-u` an
unfamiliar `tst_*` database. **"Some modules are not loaded" means STOP.** Never copy a
field-adding change to `/opt` before every installing database has been upgraded — schema
first, code second. Never point a field in a shared addon at a model outside its `depends`; a
missing comodel breaks the whole registry. Never assume a failed multi-module `-u` changed
nothing. Never merge PR #177 or #197 as-is, nor the four T00 PRs (#199–#202); never reopen
#116.

**Data and accounting.** Never `TRUNCATE … CASCADE` the transaction tables — it wipes the whole
database through `res_company.account_opening_move_id`. Never backdate an adjustment into a
period already reported to the client; if it is posted and fresh, delete rather than reverse,
and only when no reconciliations are attached. Never use `stock_move.value` or
`standard_price` as the COGS price basis — use the PO price net of tax. Never turn on any COGS
switch while the FA hold stands. Never process a large data fix in one transaction on
production. Never repair `owner_id` on done stock lines through the ORM, and never `unlink`
quants through the ORM — use SQL. Never revoke the six permanent `account.lock_exception` rows
on `prd_levis_begbal`, and never treat them as a finding. Never revoke `base.group_system`
without `base.group_erp_manager`, and never via SQL. Never leave feeds or mailboxes active on
a clone of a production database. Never drop a database without archiving its filestore in the
same breath — `pg_dump` does not carry the filestore and `dropdb` does not remove it.

**Front door.** Never build the Caddy image with `xcaddy build`. To reload Caddy config use
`docker restart odoo19-platform-caddy`, never a compose recreate. Never enable `tls
client_auth` before Authenticated Origin Pulls is on in Cloudflare.

**Roles and operating units.** Never change `include_untagged` in production (user decision,
12 Aug 2026). The roles/OU modules in `/opt` were copied with `cp -a`, so never `git pull` to
update them. When auditing group membership, never count `res_groups_users_rel` alone — the
figure reflects a bulk grant, not the modules.

**Applications and reporting.** Never add an LLM call to the cockpit recommendation engine.
Never loosen the public instance's `dbfilter`. Never report as a defect: a `curl -F` 500 on
`/signin`, a `size=0` 200 from `127.0.0.1`, a `/websocket` 404, or a `py.warnings` stack.
**Never offer a solution whose data you have not opened yourself — on both sides.**

---

## 14. Sepuluh hal untuk diperiksa di hari pertama

1. **Sembilan draft COGS catch-up Rp 3.034.401.903,48** masih belum diposting; run 0007 masih
   `computed`; `cogs_session_start` kosong; cron 51 non-aktif — **FA hold**.
2. **`ALERT_WHATSAPP_DISABLED=1` masih terpasang; baileys `acct-2` masih logged out** →
   tidak ada peringatan yang sampai ke manusia.
3. **`custom_wms_integration` belum terpasang di produksi** — butuh restart empat container
   yang harus dijalankan user.
4. **Clearing Levi's September belum dijalankan**; `7104000001` masih NIL untuk MDR September
   (~Rp 30,2 juta sudah ada di bank).
5. **Persediaan awal belum pernah masuk GL** — gap kini ≈ **Rp 25,31 miliar**, melebar setiap
   kali COGS diposting.
6. **ARKA: Rp 920 juta barang diterima tanpa jurnal** (rantai intercompany terputus; posting
   draft 277).
7. **`custom_levis_mdr` tertinggal status `to upgrade` di 3 DB** setelah deploy 25-Sep.
8. **Feed/mailbox pada DB apa pun yang diklon sejak 20-Sep** —
   `select count(*) from retail_import_feed where active`.
9. **Hari dagang 15-Sep-2026 (22 toko, ~Rp 300 juta) masih hilang** — harus diminta ulang ke
   X-center.
10. **Gate pajak G7–G10, K-2, G11, G15 belum dijawab** → T13/T15/T16/T17 terblokir.

---

## 15. Rantai eskalasi & aset di luar repo

- **Akses host:** sesi tmux `vps-odoo-ERA` di VPS. Jangan `sudo claude` tanpa `-H`.
- **Share berkas klien:** File Browser di `https://eal-hub.erajaya.com/files`, backed by
  `/srv/sftp-share/files` di host, plus akses SFTP. **Direktori itu dipantau feed retail
  Levi's** (`custom_retail_import/models/retail_import_mailbox.py`; di produksi
  `/mnt/data_levis` adalah bind mount darinya) — jangan menaruh berkas yang cocok glob feed
  (`X24*.xlsx`, `X101*`, `X70*`) di sana.
- **Database manager** hanya lewat `odoo-mgmt` di `127.0.0.1:18079`; prosedurnya di
  `docs/runbooks/database-manager-access.md`.
- **Rahasia** ada di `.env` repo (tidak ter-track) dan di env container
  (`$POSTGRES_PASSWORD` hanya ada di container, tidak di `.env` lokal mana pun). Tidak ada
  satu pun rahasia di dokumen handover ini.
- **Submission Erajaya Achievement Award** untuk EAL-Hub disiapkan di
  `docs/awards/eaa-ealhub/` tapi **belum disubmit** — login E-InnoHub memakai NIK user.
  Rubrik penilaian EAA belum tersedia. Lihat `Handover-Pipeline-Prospek.docx`.
- **Dependensi build deck** (`python-pptx`, `reportlab`) tidak terpasang di python sistem —
  pakai venv.
