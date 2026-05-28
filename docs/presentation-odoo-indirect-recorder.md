# Odoo sebagai Indirect Transaction Recorder
## Principal-Led Operations · FTP-fed FICO & Procurement Hub

**Audience:** Executive / Business Stakeholders Erajaya
**Owner:** Product Owner — Value-Added Services, Erajaya
**Status:** Internal pitch deck (Mei 2026)

---

## Slide 1 — Executive Summary

**Pola integrasi indirect recording**: aplikasi principal (vendor/OEM) tetap menjadi sistem operasional utama. Odoo hanya mengambil dua domain: **Procurement (PO)** dan **FICO** (General Ledger, AR/AP, Tax, Reporting).

Aliran data operasional (Sales, GR, Inventory) disuplai dari principal lewat **FTP** dan dimuat ke Odoo via fitur **import bawaan**. Tidak perlu rip-and-replace aplikasi principal.

| Metric | Value |
|---|---|
| Domain Odoo | **PO + FICO + Tax** |
| Domain Principal | **Sales · GR · Inventory · POS** |
| Transport | **SFTP pull (Odoo client)** |
| Go-live Estimate | **~8 minggu** |
| Mandays | **~27 md / principal** |

---

## Slide 2 — Boundary Matrix (Siapa Pegang Apa)

| Proses / Modul | Aplikasi Principal | Odoo |
|---|:---:|:---:|
| Sales Order, Customer ops, POS | ✓ |  |
| Goods Receipt (eksekusi) | ✓ |  |
| Inventory movement, stock balance | ✓ |  |
| Customer Invoice (issuance ke pelanggan) | ✓ |  |
| Purchase Order (RFQ → release ke vendor) |  | ✓ |
| Vendor master, vendor bill (AP) |  | ✓ |
| General Ledger, Bank/Cash, Reconciliation |  | ✓ |
| AR posting (revenue recognition dari principal feed) |  | ✓ |
| Tax: e-Faktur Coretax, Bupot, SPT |  | ✓ |
| Fixed Asset, Konsolidasi, Reporting |  | ✓ |
| Master data: Customer, Product | ✓ (authoritative) | ✓ (mirror) |
| Master data: Vendor, CoA, Tax Code |  | ✓ (authoritative) |

**Prinsip:** principal = system of record operasional; Odoo = system of record finance + procurement upstream.

---

## Slide 3 — System Landscape

```
┌──────────────────────┐       ┌──────────────────┐       ┌──────────────────────┐
│ Principal App        │  CSV  │  FTP Server      │ pull  │  Odoo 19 (Hub)       │
│ Sales · GR · Stock   │ ───▶  │  (SFTP / FTPS)   │ ◀───  │  PO · FICO · Tax     │
│ POS · Inv. Issuance  │       │  /outbound · /ack│       │  custom_ftp_ingest   │
└──────────────────────┘       └──────────────────┘       └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌────────────────────┐
                                                          │ Pajakku ASPP H2H   │
                                                          │ Coretax · DJP      │
                                                          └────────────────────┘
```

**Catatan arsitektur:**
- Odoo **pull** (client SFTP) — principal tidak butuh kredensial ke jaringan kita.
- File CSV UTF-8 dengan header standar; idempotent via `external_id`.
- Tidak ada koneksi langsung principal ↔ Odoo (zero attack surface dari principal).

---

## Slide 4 — Data Contract (FTP Drop Layout)

```
/erajaya/outbound/
  ├── master/
  │     ├── customer_YYYYMMDD.csv
  │     ├── product_YYYYMMDD.csv
  │     └── vendor_YYYYMMDD.csv
  ├── sales/
  │     ├── so_header_YYYYMMDD_NNN.csv
  │     ├── so_line_YYYYMMDD_NNN.csv
  │     ├── invoice_YYYYMMDD_NNN.csv
  │     └── invoice_line_YYYYMMDD_NNN.csv
  ├── gr/
  │     └── gr_YYYYMMDD_NNN.csv      (link: po_number)
  └── stock/
        └── stock_balance_YYYYMMDD.csv

/erajaya/ack/   ← Odoo tulis hasil <filename>.ok | <filename>.err
/erajaya/quarantine/   ← file invalid, manual review
```

**Format:** CSV UTF-8 RFC4180 · header row · `external_id` per row · timestamp ISO-8601 · numerik desimal titik · timezone Asia/Jakarta.

---

## Slide 5 — Ingestion Flow (Scheduled Pull)

```
Cron Odoo (every 1 hour)
  │
  1. Connect SFTP   ← creds di ir.config_parameter (Fernet-encrypted)
  2. List /outbound/* belum diproses (state di model ftp.ingest.file)
  3. Download → /tmp/ingest_<uuid>/
  4. Validate schema (CSV schema map per entity)
  5. Stage → import via base_import.load() API (atomic per file)
  6. Tulis ack file → /ack/<filename>.ok | .err
  7. Notify channel + audit log entry (custom_pdp_audit)
  8. Move processed file → /archive/YYYYMM/ (retention 90 hari)
```

**Komponen baru:** `custom_ftp_ingest` (Hub repo) — scheduled action + dispatcher per entity + schema map registry.

**Re-use:** `base_import` (Odoo CE `load()` API) untuk eksekusi import; `custom_pdp_audit` untuk audit chain.

---

## Slide 6 — PO ↔ GR Cross-System Flow

```
[Odoo]      Create RFQ → Confirm PO → Send PDF/EDI ke vendor + principal
                                          │
[Vendor]    Kirim barang                  │
                                          ▼
[Principal] Receive goods di gudang → Catat GR (link po_number)
                                          │
                                          ▼  (FTP drop /gr/gr_*.csv per jam)
[Odoo]      Ingest gr_*.csv
              → match purchase.order.line by po_number + sku
              → create stock.picking done (informational receipt)
              → 3-way match: PO qty vs GR qty vs Vendor Bill qty
              → Vendor Bill draft → approval → posted → AP outstanding
                                          │
                                          ▼
[Odoo]      Schedule payment → bank file → reconciliation
```

**Critical control:** PO milik Odoo, GR milik principal — match-nya di `po_number`. Mismatch (PO tidak ada, qty over-receipt) → quarantine + alert.

---

## Slide 7 — Sales → Revenue Recognition Flow

```
[Principal] Sales Order → Delivery → Customer Invoice (operasional)
                                          │
                                          ▼  (FTP drop /sales/invoice_*.csv harian)
[Odoo]      Ingest invoice_*.csv
              → posting account.move (AR ledger)
              → revenue account (per product category mapping)
              → tax line (PPN keluaran, dipotong PPh jika perlu)
              → e-Faktur Coretax queue (Pajakku ASPP)
                                          │
                                          ▼
[Odoo]      Daily reconciliation:
              - total principal invoice vs sum account.move AR per tanggal
              - variance > threshold → alert ops + approval engine
```

**Yang TIDAK dibuat di Odoo:** `sale.order`, `stock.picking outgoing`. Odoo hanya menerima hasil akhir (invoice posted) — operasional pre-invoice tetap di principal.

---

## Slide 8 — Master Data Sync Strategy

**Principal authoritative (Odoo mirror, principal wins):**
- `res.partner` customer (key: `customer_code`)
- `product.product` SKU (key: `default_code` / `sku`)
- Sync harian, full snapshot. Conflict → overwrite Odoo dengan nilai principal.

**Odoo authoritative (principal read-only mirror jika butuh):**
- `res.partner` vendor (Odoo PO butuh vendor master)
- `account.account` CoA (PSAK 5-digit)
- `account.tax` (PPN, PPh, DPP Nilai Lain)
- Sync via Odoo export ke `/outbound-odoo/` jika principal butuh referensi.

**Append-only di Odoo:** vendor & CoA — principal tidak boleh tulis ke domain ini.

---

## Slide 9 — Reconciliation & Control (Daily Variance Engine)

**Checks otomatis setiap pagi (07:00):**

| Check | Source A | Source B | Action |
|---|---|---|---|
| Revenue match | sum(invoice CSV principal) per tgl | sum(account.move AR) per tgl | Alert >0.5% |
| GR match | sum(gr CSV) per PO | sum(stock.picking) per PO | Alert mismatch |
| Stock balance | stock_balance.csv (read-only) | stock.quant Odoo | Audit-only report |
| Tax match | invoice tax CSV | account.tax line | Alert mismatch |
| Feed liveness | last file timestamp principal | now() | Alert if >24h silent |

Variance > threshold → ticket otomatis via `custom_approval_engine` → review oleh finance lead.

---

## Slide 10 — Error Handling & Replay

| Error Class | Detection | Recovery |
|---|---|---|
| **Schema invalid** (header missing / type mismatch) | Validator stage di step 4 | Move ke `/quarantine/`, alert, manual fix → replay |
| **Reference miss** (PO/customer/product tidak ada) | base_import resolution error | Retry 3× (1h interval), lalu manual review queue |
| **Duplicate** (`external_id` sudah diproses) | Unique constraint di `ftp.ingest.row` | Skip + log info (idempotent) |
| **Partial commit failure** | Atomic per-file savepoint rollback | File ditandai `.err`, semua row di-revert, replay setelah fix |
| **Feed stalled** (no new file >24h) | Liveness check daily 09:00 | Alert ke ops channel; eskalasi ke principal SPOC |
| **Network / SFTP down** | Connection exception di step 1 | Exponential backoff 3 attempts, alert if all fail |

---

## Slide 11 — Security & Compliance

**Transport & Credential:**
- SFTP **key-based auth** (Ed25519), password disabled
- Private key di Odoo: SOPS-encrypted di repo, Fernet di runtime
- Connection allow-list IP-based (principal SFTP server only)
- TLS 1.3 wrap jika FTPS dipakai sebagai fallback

**Data & Audit:**
- Append-only audit log per ingestion event (`custom_pdp_audit`, hash-chained)
- PII masking di log (customer name → hash); PDP Klasifikasi field-level
- Retention: file principal 90 hari di `/archive`, audit log 7 tahun (sesuai dokumen pajak)
- DSAR ready: customer-level export dari Odoo + cross-ref ke principal

**Pipeline:**
- Pre-commit: gitleaks, ruff, bandit · CI: Semgrep + pip-audit + Trivy
- Modul `custom_ftp_ingest` di-pin version `19.0.x.y` + CI per release

---

## Slide 12 — Modules / Components in Play

| Komponen | Asal | Peran |
|---|---|---|
| `purchase` | Odoo CE | PO, RFQ, Vendor Bill, 3-way match |
| `account`, `account_asset` | Odoo CE | GL, AR/AP, Bank, Fixed Asset |
| `base_import` | Odoo CE | `load()` API untuk CSV import |
| `custom_accounting_full` | Hub repo | PSAK CoA 5-digit, Intercompany, Konsolidasi |
| `custom_coretax`, `custom_coretax_bupot` | Hub repo | e-Faktur, Bupot, NSFP, Pajakku ASPP |
| `custom_approval_engine` | Hub repo | Variance review workflow + escalation |
| `custom_pdp_audit` | Hub repo | Append-only hash-chained audit log |
| **`custom_ftp_ingest` (NEW)** | Hub repo (build) | SFTP poller, schema map registry, dispatcher, ack writer |

**Build effort terkonsentrasi di 1 modul baru** — sisanya re-use dari library Hub yang sudah ready.

---

## Slide 13 — Alternative: Tanpa FTP Adapter (Manual Import Mode)

Skenario "lite" — **tidak build `custom_ftp_ingest`**, hanya pakai fitur **import bawaan Odoo** (Settings → Technical → Import). Principal kirim CSV via email/share drive, ops Odoo upload manual.

**How it Works:**
- Tidak ada SFTP poller, tidak ada scheduled cron
- File CSV principal dikirim via email / shared drive (OneDrive / GDrive) ke ops Odoo
- Ops upload manual lewat Odoo UI per entitas (`base_import.load()` di balik layar — API yang sama)
- Template XLSX/CSV per entity disiapkan supaya principal taat format
- Audit lewat `ir.attachment` + activity log standar Odoo

**Trade-offs:**

| Aspek | FTP Adapter (custom_ftp_ingest) | Manual Import Mode |
|---|---|---|
| Build effort | ~27 md (1 modul baru) | **~15 md** (template + SOP + UAT) |
| Go-live time | ~8 minggu | **~4–5 minggu** |
| Infra | SFTP server + credential | Tidak ada |
| Recurring ops | Cron, monitoring | **~1–2 jam/hari upload manual** |
| Human error risk | Rendah (otomatis) | **Tinggi** (salah file, missed upload, urutan) |
| Liveness alert | Otomatis (>24h alert) | Tidak ada — telat ketahuan |
| Idempotency | Built-in via `external_id` | Tergantung disiplin ops |
| Reconciliation | Otomatis daily 07:00 | Manual run oleh finance |
| Audit trail | Hash-chained `custom_pdp_audit` | `ir.attachment` + login log standar |
| Cocok untuk | Volume harian, lifetime panjang | **Pilot / PoC / volume rendah** |

**Catatan ROI:** Selisih 12 md (~12 hari developer) di-recover dalam ~3 bulan operasional karena ops menghabiskan ~10 jam/minggu (~520 jam/tahun ≈ 65 md/tahun) untuk manual upload. **Manual mode hanya layak sebagai bridge** sebelum FTP adapter di-build, atau untuk principal dengan volume < 50 file/bulan.

---

## Slide 14 — Implementation Mandays (Breakdown per Role)

| Phase | Activity | ITBP (PMO) | IT BA | Developer | QA | Total |
|---|---|---:|---:|---:|---:|---:|
| Setup | SFTP infra + credential exchange dgn principal | 1 | 1 | 1 | — | 3 |
| Build | Modul `custom_ftp_ingest` (poller, schema map, dispatcher, ack) | 1 | 1 | 5 | 1 | 8 |
| Schema Map | 7 entitas: customer, product, vendor, SO, invoice, GR, stock | — | 2 | 3 | 1 | 6 |
| Reconcile | Daily variance engine + dashboard | 1 | 1 | 2 | — | 4 |
| UAT | Cross-system end-to-end (principal ↔ Odoo) | 1 | 1 | 1 | 3 | 6 |
| **Subtotal per Role** | | **4** | **6** | **12** | **5** | **27** |

**Peran:**
- **ITBP (PMO)** — koordinasi cross-team, governance, sign-off, hypercare lead.
- **IT BA** — schema contract design, mapping entity, requirement validation, UAT scenario.
- **Developer** — build `custom_ftp_ingest`, schema map registry, variance engine, integration.
- **QA** — test plan, regression, end-to-end cross-system, sign-off testing report.

**Komparasi:** Integrasi point-to-point dgn custom middleware tradisional: ~80–120 md. Saving ~70% karena re-use `base_import` + library Hub.

---

## Slide 15 — Roadmap & Phasing (8 Minggu)

**Phase 1 — Wk 1–2 · Foundation**
- SFTP handshake dengan principal
- Build `custom_ftp_ingest` skeleton
- Master data sync (customer, product, vendor)

**Phase 2 — Wk 3–4 · Procurement Loop**
- PO export dari Odoo ke principal (PDF/EDI)
- GR ingestion + 3-way match
- Vendor Bill draft → approval → posted

**Phase 3 — Wk 5–6 · Revenue Loop**
- Sales/Invoice CSV ingestion
- AR posting + tax line + Coretax queue
- Reconciliation engine variance check

**Phase 4 — Wk 7–8 · Go-Live**
- UAT cross-system + bug-fix
- Hypercare ops + runbook handover
- Cutover plan eksekusi

---

## Slide 16 — Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Principal schema drift (kolom berubah tanpa notice) | Schema contract + `schema_version` field di CSV header · validator strict mode · alert deviasi |
| Feed stalled (principal sistem down) | Daily liveness check + heartbeat file `/heartbeat_YYYYMMDDHHMM.txt` · eskalasi SPOC |
| Reconciliation gap (timing cut-off beda) | Cut-off contract: principal cut H-1 23:59 WIB, Odoo proses 07:00 H+0 |
| Duplicate posting (re-send dari principal) | Idempotency lewat `external_id` unique constraint |
| Tax submission gagal (Coretax/Pajakku) | Circuit breaker + manual portal fallback + ops alert |
| SFTP credential rotation | Quarterly rotation runbook · zero-downtime via dual-key window |

---

## Slide 17 — Call to Action

1. **Endorsement** — Approve pola indirect recording sebagai blueprint integrasi dengan aplikasi principal.
2. **Pilot Funding** — Allocate untuk 1 principal pertama (lead candidate disepakati sebelum kick-off).
3. **SFTP Infrastructure** — Provision SFTP server + credential exchange dengan principal SPOC Wk-0.
4. **Resource Lock** — 1 backend Odoo + 1 finance SME + 1 PO untuk durasi 8 minggu.
5. **Cut-off Agreement** — Tanda-tangan data contract & cut-off timing dengan principal sebelum build.

---

## Slide 18 — Terima Kasih

**Diskusi & Q&A**

Product Owner — Value-Added Services · Erajaya · Mei 2026
