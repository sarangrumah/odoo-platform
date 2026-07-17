# Finance Portal (SAP) — Arsitektur Sistem
**Versi 2.0 · 2026-06-25 · Odoo 19 CE · Finance Portal DB (terpisah)**

---

## Document Control

| | |
|---|---|
| **Proyek** | Finance Portal on Odoo |
| **Versi** | 2.0 |
| **Tanggal** | 2026-06-25 |
| **Scope** | Odoo 19 CE (Finance Portal DB) + SAP Bridge microservice |
| **Perubahan dari v1** | DB terpisah · Multi-company · Kafka-only · Vendor self-reg · OCR Tesseract |

---

## 1. Architecture Decision Record (ADR)

| # | Keputusan | Pilihan | Alasan |
|---|---|---|---|
| ADR-01 | Peran Odoo | System of Engagement (tanpa GL posting) | SAP tetap System of Record; Odoo hanya form + approval + tracking |
| ADR-02 | Database | **DB baru terpisah** dari existing Odoo DB | Isolasi lifecycle; tidak ganggu operasional existing |
| ADR-03 | Multi-PT Erajaya | **Single Finance Portal DB + `res.company` per PT** | Consolidated dashboard native; shared vendor master; satu SSO |
| ADR-04 | Integrasi SAP | **Kafka-only — Bridge tidak boleh call SAP REST langsung** | Historical constraint: direct SAP connection tidak disarankan |
| ADR-05 | Bridge pattern | Bridge = Kafka consumer/producer + Redis cache + HMAC REST relay | Odoo tidak kenal Kafka; Bridge sebagai satu-satunya integration point |
| ADR-06 | SSO karyawan | Keycloak OIDC via `auth_oauth` | HRIS maintain employee identity |
| ADR-07 | Login vendor | **Odoo native portal: self-registration + invite** | HRIS tidak maintain vendor data; vendor bukan employee |
| ADR-08 | OCR engine | **Tesseract 4 LSTM (primary) + pdfplumber (digital PDF fallback)** | CPU-only (VM tanpa GPU); scanned PDF sebagai format utama |
| ADR-09 | Travel dinas | Read-only mirror dari HRIS | HRIS yang owns travel engine |
| ADR-10 | Async push | `queue_job` (OCA) `with_delay()` | Hindari timeout di Odoo webhook; decouple dari SAP latency |

---

## 2. System Context

> **Finance Portal DB** adalah Odoo tenant baru yang berjalan di samping existing Odoo DB.
> Seluruh komunikasi ke SAP/HRIS **hanya melalui Kafka** — Bridge tidak pernah call SAP REST.

```mermaid
flowchart TB
    classDef person    fill:#08427b,color:#fff,stroke:#052e56,rx:8
    classDef odoo      fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef bridge    fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef kafka     fill:#d4860b,color:#fff,stroke:#a36008
    classDef external  fill:#6b6b6b,color:#fff,stroke:#4a4a4a
    classDef existing  fill:#c0392b,color:#fff,stroke:#922b21

    EMP(["👤 Karyawan\n(Employee)"]):::person
    VND(["👤 Vendor"]):::person
    FIN(["👤 Tim Finance & Tax"]):::person
    GRP(["👤 Finance Group\n(Holding — semua PT)"]):::person

    subgraph NEWDB["Finance Portal DB  ←  BARU, TERPISAH"]
        direction TB
        subgraph MODULES["Odoo 19 CE — Finance Portal"]
            FP["custom_finance_portal\nDokumen + Approval + Vendor Portal"]:::odoo
            FB["custom_finance_budget\nBudget & PR Validation"]:::odoo
            FSAP["custom_finance_portal_sap\nAdapter + Webhook + Sync Log"]:::odoo
            FSSO["custom_finance_portal_sso\nKeycloak + Vendor Auth"]:::odoo
        end
    end

    EDBX["Existing Odoo DB\n(tidak disentuh)"]:::existing

    BRG["SAP Bridge\nFastAPI · Kafka Consumer/Producer\nRedis Cache"]:::bridge

    KC["Keycloak\nOIDC IdP"]:::external
    KF["Kafka Bus"]:::kafka
    SAP["SAP S/4HANA\nSystem of Record"]:::external
    HRIS["HRIS\nTravel + Employee"]:::external

    EMP  -->|HTTPS + SSO Keycloak| NEWDB
    VND  -->|HTTPS + Odoo Portal Login| NEWDB
    FIN  -->|HTTPS + SSO Keycloak| NEWDB
    GRP  -->|HTTPS + SSO Keycloak\nAkses semua PT| NEWDB

    FSSO -->|OIDC autentikasi| KC
    FSAP -->|HMAC REST — internal| BRG

    BRG  -->|consume: sap.to.portal.*\nhris.to.portal.*| KF
    BRG  -->|produce: portal.to.sap.*| KF
    KF   <-->|GL·MIRO·Payment·Master| SAP
    KF   <-->|Travel·Employee| HRIS

    NEWDB -.-|"berjalan di Odoo instance\nyang sama, DB terpisah"| EDBX
```

---

## 3. Arsitektur Modul Odoo

```mermaid
flowchart BT
    classDef suite fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef core  fill:#2980b9,color:#fff,stroke:#1a6fa0
    classDef base  fill:#ecf0f1,color:#2c3e50,stroke:#bdc3c7

    subgraph Base["Odoo 19 CE Base"]
        direction LR
        MAIL["mail"]:::base
        PORTAL["portal"]:::base
        HR["hr"]:::base
        ACCT["account"]:::base
        OAUTH["auth_oauth"]:::base
    end

    subgraph Core["Platform Core"]
        direction LR
        CCORE["custom_core\nsecure_endpoint\nconfig params"]:::core
        CAE["custom_approval_engine\napproval.mixin\napproval.matrix"]:::core
        CAF["custom_adapter_framework\nBaseAdapter · @register_adapter"]:::core
        CPDP["custom_pdp_audit\npdp.audited.mixin"]:::core
        JWT["auth_jwt\n(vendored OCA)"]:::core
        QJ["queue_job\n(OCA)"]:::core
    end

    subgraph Suite["Finance Portal Suite"]
        direction TB
        FP["custom_finance_portal\nfinance.document.mixin\nCA · Reimb · Invoice · Travel\nMaster · Vendor Portal · Report"]:::suite
        FB["custom_finance_budget\nfinance.budget\n_check_document_budget"]:::suite
        FSAP["custom_finance_portal_sap\nSapBridgeAdapter · HrisBridgeAdapter\nqueue_job push · cron sync\nwebhook · sync.log"]:::suite
        FSSO["custom_finance_portal_sso\n_auth_oauth_signin override\nVendor self-reg controller\nrole → group mapping"]:::suite
    end

    FP   --> CCORE & CAE & CPDP & MAIL & PORTAL & HR & ACCT
    FB   --> FP
    FSAP --> FB & CAF & QJ
    FSSO --> FP & OAUTH & CCORE & JWT
```

---

## 4. Integrasi — Kafka Only (REVISED)

### 4.1 Prinsip Desain

| Prinsip | Implementasi |
|---|---|
| **No direct SAP connection** | Bridge TIDAK PERNAH buka koneksi HTTP/JDBC ke SAP |
| **Kafka-only ke SAP** | Semua data dari SAP masuk via Kafka topic yang di-produce SAP |
| **Bridge sebagai cache layer** | Bridge consume semua topik SAP → simpan di Redis → Odoo query Bridge |
| **Odoo tidak kenal Kafka** | Odoo hanya bicara REST (HMAC) ke Bridge di Docker internal network |
| **Event-driven untuk kritis** | PR/PO/GR/Payment: event-driven (bukan batch) agar cache selalu fresh |
| **Async push outbound** | Odoo enqueue via `queue_job`; Bridge produce ke Kafka; tidak ada blocking |

### 4.2 Bridge Cache Architecture

```mermaid
flowchart LR
    classDef sap     fill:#6b6b6b,color:#fff,stroke:#4a4a4a
    classDef kafka   fill:#d4860b,color:#fff,stroke:#a36008
    classDef bridge  fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef redis   fill:#c0392b,color:#fff,stroke:#922b21
    classDef odoo    fill:#1168bd,color:#fff,stroke:#0d52a0

    SAP["SAP S/4HANA"]:::sap
    HRIS["HRIS"]:::sap

    subgraph KF["Kafka Bus"]
        direction TB
        T1["sap.to.portal.pr-master"]:::kafka
        T2["sap.to.portal.po-gr-master"]:::kafka
        T3["sap.to.portal.vendor-master"]:::kafka
        T4["sap.to.portal.budget-master"]:::kafka
        T5["sap.to.portal.payment-status"]:::kafka
        T6["sap.to.portal.posting-confirm"]:::kafka
        T7["hris.to.portal.employee-master"]:::kafka
        T8["hris.to.portal.travel-request"]:::kafka
        T9["portal.to.sap.*"]:::kafka
    end

    subgraph BRG["SAP Bridge (FastAPI)"]
        direction TB
        CONS["Kafka Consumer\nThreads"]:::bridge
        REDIS["Redis Cache\npr_master · po_gr · vendor\nbudget · employee · travel\nTTL: PR/PO=1h · master=24h"]:::redis
        REST["HMAC REST\nEndpoints"]:::bridge
        PROD["Kafka Producer\nThreads"]:::bridge
        CONS --> REDIS
        REST --> REDIS
        REST --> PROD
    end

    ODO["Odoo Finance Portal\n(HMAC REST only)"]:::odoo

    SAP  -->|produce| T1 & T2 & T3 & T4 & T5 & T6
    HRIS -->|produce| T7 & T8
    KF   -->|consume| CONS
    ODO  <-->|HMAC REST\ninternal Docker network| REST
    PROD -->|produce| T9
    T9   -->|consume| SAP
```

### 4.3 Kafka Topic Map

| # | Kafka Topic | Producer | Consumer | Frekuensi | Keterangan |
|---|---|---|---|---|---|
| 1 | `sap.to.portal.pr-master` | SAP | Bridge | Event-driven | PR create/update/close |
| 2 | `sap.to.portal.po-gr-master` | SAP | Bridge | Event-driven | PO/GR create/update |
| 3 | `sap.to.portal.vendor-master` | SAP | Bridge | Daily + on-change | Supplier master |
| 4 | `sap.to.portal.budget-master` | SAP | Bridge | Daily + on-revision | Budget per divisi |
| 5 | `sap.to.portal.item-category` | SAP | Bridge | Weekly | Item/kategori |
| 6 | `sap.to.portal.bank-master` | SAP | Bridge | Weekly | Bank master |
| 7 | `sap.to.portal.payment-status` | SAP | Bridge | Event-driven | Payment plan + actual |
| 8 | `sap.to.portal.posting-confirm` | SAP | Bridge | Event-driven | GL/MIRO confirmation |
| 9 | `hris.to.portal.employee-master` | HRIS | Bridge | Daily + on-change | Employee + divisi + rekening |
| 10 | `hris.to.portal.travel-request` | HRIS | Bridge | Event-driven | Travel approved/updated |
| 11 | `portal.to.sap.cash-advance` | Bridge | SAP | Event-driven | CA GL posting request |
| 12 | `portal.to.sap.reimbursement` | Bridge | SAP | Event-driven | Reimb GL posting |
| 13 | `portal.to.sap.vendor-invoice` | Bridge | SAP | Event-driven | MIRO request |
| 14 | `portal.to.sap.travel-settlement` | Bridge | SAP | Event-driven | Travel settlement GL |

> Nama topik, retention, dan partition count disepakati tim Kafka klien. Bridge adalah **satu-satunya** sistem yang produce/consume dari sisi portal.

### 4.4 Aliran Outbound (Odoo → SAP via Kafka)

```mermaid
sequenceDiagram
    autonumber
    participant ODO  as Odoo<br/>(Finance Portal)
    participant QJ   as queue_job<br/>Worker
    participant ADPT as SapBridgeAdapter
    participant BRG  as SAP Bridge
    participant KF   as Kafka Bus
    participant SAP  as SAP S/4HANA

    ODO  ->> ODO  : Finance Approve → state=approved
    ODO  ->> QJ   : with_delay()._job_push_to_sap()<br/>sap_sync_state = queued

    Note over QJ,ADPT: Async — tidak blocking Odoo

    QJ   ->> ADPT : push_document(payload)
    ADPT ->> BRG  : POST /from-odoo/finance/push<br/>X-Timestamp + X-Signature (HMAC)
    BRG  ->> BRG  : verify HMAC
    BRG  ->> KF   : produce → portal.to.sap.cash-advance
    KF   ->> SAP  : consume event
    SAP  ->> SAP  : GL Posting / MIRO

    Note over SAP,KF: Konfirmasi dikirim via Kafka (event-driven)

    SAP  ->> KF   : produce → sap.to.portal.posting-confirm
    KF   ->> BRG  : consume
    BRG  ->> ODO  : POST /finance/sap/status (HMAC)<br/>event_type=posted, sap_document_no
    ODO  ->> ODO  : _finance_apply_sap_status()<br/>state: pushed → posted
```

### 4.5 Aliran Inbound — Payment Status (SAP → Odoo)

```mermaid
sequenceDiagram
    autonumber
    participant SAP  as SAP S/4HANA
    participant KF   as Kafka Bus
    participant BRG  as SAP Bridge
    participant ODO  as Odoo<br/>secure_endpoint

    SAP  ->> KF   : produce → sap.to.portal.payment-status<br/>{odoo_ref, payment_plan_date, payment_amount}
    KF   ->> BRG  : consume (consumer thread)
    BRG  ->> BRG  : update Redis cache payment status
    BRG  ->> ODO  : POST /finance/sap/status<br/>HMAC signed
    ODO  ->> ODO  : _verify_hmac()<br/>canonical: ts.encode() + raw_body
    ODO  ->> ODO  : _finance_apply_sap_status(vals)<br/>state: posted → paid<br/>payment_plan_date terisi
    ODO  -->> ODO : Dashboard requester terupdate
```

### 4.6 Lookup PR / PO-GR — via Bridge Cache

```mermaid
sequenceDiagram
    autonumber
    participant USR  as User (Odoo Form)
    participant ODO  as Odoo
    participant ADPT as SapBridgeAdapter
    participant BRG  as Bridge + Redis Cache
    participant KF   as Kafka ← SAP (background)

    Note over KF,BRG: Background: SAP produce PR events<br/>Bridge consume → Redis update (event-driven)

    USR  ->> ODO  : Input pr_number di form
    ODO  ->> ADPT : lookup_pr(pr_number)
    ADPT ->> BRG  : GET /from-odoo/finance/pr/lookup?pr=PR-001<br/>HMAC signed

    BRG  ->> BRG  : Redis GET pr:PR-001

    alt Cache HIT
        BRG -->> ADPT: {is_valid, status, value, cost_center}
        ADPT -->> ODO : PR valid → pre-fill cost_center
        ODO  -->> USR : Konfirmasi PR + nilai tampil di form
    else Cache MISS (PR baru / belum sync)
        BRG -->> ADPT: {found: false, retry_after: 30}
        ADPT -->> ODO : PR not found
        ODO  -->> USR : "PR sedang disinkronisasi dari SAP,<br/>coba lagi dalam 30 detik"
    end
```

---

## 5. Document Lifecycle — State Machine

```mermaid
stateDiagram-v2
    direction LR

    [*]            --> draft       : Buat dokumen

    draft          --> submitted   : submit()\n[validasi PR + budget]
    submitted      --> tax_review  : approval.mixin trigger\ntier 1 — Tax group
    tax_review     --> fin_review  : Tax Approve
    tax_review     --> rejected    : Tax Reject
    fin_review     --> approved    : Finance Approve
    fin_review     --> rejected    : Finance Reject

    approved       --> pushed      : _finance_push_to_sap()\nqueue_job → Bridge → Kafka → SAP
    pushed         --> posted      : SAP posting-confirm webhook\nsap_document_no terisi
    posted         --> paid        : SAP payment-status webhook\npayment_plan_date + amount terisi

    submitted      --> cancelled   : Requester cancel
    tax_review     --> cancelled   : Requester cancel
    fin_review     --> cancelled   : Requester cancel
    approved       --> cancelled   : Admin cancel (sebelum push)
    rejected       --> draft       : Revise & resubmit

    paid           --> [*]
    cancelled      --> [*]
```

---

## 6. HMAC Security Model

> Canonical message: **`timestamp.encode() + raw_body_bytes`** — byte-identical di ketiga titik.
> Drift ±300 detik; nonce di-cache untuk cegah replay.

```mermaid
flowchart LR
    classDef odoo   fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef bridge fill:#2d6a4f,color:#fff,stroke:#1b4332

    subgraph OdooOut["Odoo — Outbound"]
        AO["BaseAdapter._build_headers()\nX-Timestamp: ts\nX-Signature: HMAC-SHA256(\n  secret,\n  ts.encode() + body_bytes\n)"]:::odoo
    end

    subgraph OdooIn["Odoo — Inbound"]
        AI["secure_endpoint('finance_sap')\n_verify_hmac()\nCanonical: ts.encode() + raw_body\nDrift ±300s · nonce cache"]:::odoo
    end

    subgraph BridgeIn["Bridge — Inbound"]
        BI["hmac_util.verify()\nCanonical: ts + body (bytes)\nDrift ±300s"]:::bridge
    end

    subgraph BridgeOut["Bridge — Outbound"]
        BO["hmac_util.sign()\nX-Timestamp + X-Signature"]:::bridge
    end

    AO -->|"PUSH outbound\nPOST /from-odoo/finance/push"| BI
    BO -->|"Webhook inbound\nPOST /finance/sap/status"| AI
```

| Arah | Secret (Odoo config param) | Bridge env var |
|---|---|---|
| Odoo → Bridge | `custom_finance_portal_sap.sap_bridge_secret` | `BRIDGE_INBOUND_SECRET` |
| Bridge → Odoo | `custom_core.secure_endpoint.finance_sap.secret` | `BRIDGE_OUTBOUND_SECRET` |

---

## 7. Autentikasi — SSO & Vendor

### 7.1 Employee SSO (Keycloak OIDC)

```mermaid
sequenceDiagram
    autonumber
    actor EMP   as Karyawan
    participant ODO  as Odoo Finance Portal
    participant KC   as Keycloak

    EMP  ->> ODO  : GET /web/login
    ODO  -->> EMP : Redirect → Keycloak /auth
    EMP  ->> KC   : Login (username/password + MFA)
    KC   -->> ODO : Callback: id_token + access_token
    ODO  ->> ODO  : _auth_oauth_signin() · verify JWKS
    ODO  ->> ODO  : _finance_sso_apply_roles()\nparse realm_access.roles
    ODO  -->> EMP : Redirect /odoo/finance/dashboard\ncompany switcher aktif
```

### 7.2 Vendor Self-Registration

```mermaid
sequenceDiagram
    autonumber
    actor VND   as Vendor
    participant ODO  as Odoo Vendor Portal
    participant FIN  as Finance Admin
    participant SAP  as Bridge Redis Cache

    VND  ->> ODO  : GET /finance/vendor/register
    VND  ->> ODO  : POST form: nama PT, NPWP, email PIC, telp
    ODO  ->> ODO  : Cari res.partner by NPWP\n(dari SAP vendor master sync)
    alt NPWP ditemukan di master SAP
        ODO  ->> ODO  : Link pendaftaran ke res.partner
        ODO  ->> FIN  : Notifikasi: "Vendor X mendaftar, perlu approval"
        FIN  ->> ODO  : Approve → Grant portal access
        ODO  ->> VND  : Email aktivasi akun
        VND  ->> ODO  : Aktivasi + set password
        ODO  ->> ODO  : Assign group_finance_vendor
        ODO  -->> VND : Redirect /my/finance/invoices
    else NPWP tidak ditemukan
        ODO  -->> VND : "NPWP belum terdaftar sebagai vendor aktif.\nHubungi tim Procurement."
    end
```

### 7.3 Vendor Invite (dari Finance)

```mermaid
sequenceDiagram
    autonumber
    participant FIN  as Finance Admin
    participant ODO  as Odoo
    participant VND  as Vendor (email)

    Note over ODO: res.partner sudah ada\ndari SAP vendor master sync
    FIN  ->> ODO  : Buka res.partner vendor
    FIN  ->> ODO  : Klik "Grant Portal Access"
    ODO  ->> ODO  : Buat res.users (portal)\nAssign group_finance_vendor
    ODO  ->> VND  : Email invite: "Aktivasi akun Finance Portal"
    VND  ->> ODO  : Klik link → set password
    ODO  -->> VND : Redirect /my/finance/invoices
```

---

## 8. OCR Pipeline

> **Format utama: scanned PDF.** Tesseract adalah path primer; pdfplumber sebagai shortcut untuk digital PDF.
> **Prinsip: pre-fill + wajib konfirmasi vendor** — tidak ada auto-submit berdasarkan OCR.

```mermaid
flowchart TD
    classDef process fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef decision fill:#d4860b,color:#fff,stroke:#a36008
    classDef error   fill:#c0392b,color:#fff,stroke:#922b21
    classDef success fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef check   fill:#8e44ad,color:#fff,stroke:#6c3483

    A(["Vendor Upload PDF"])
    B{{"Cek metadata:\nDPI ≥ 200?\nBlur score OK?"}}:::decision
    C(["Tolak upload\nPesan: 'Scan ulang min 300 DPI,\ndokumen rata'"]):::error
    D{{"Ada text layer?\n(pdfplumber check)"}}:::decision
    E(["pdfplumber\nextract text langsung"]):::process
    F(["pdf2image\n→ 300 DPI PNG per halaman"]):::process
    G(["OpenCV Pre-processing\n1. Grayscale\n2. Denoise\n3. Deskew\n4. Binarize (Otsu)\n5. Upscale jika < 300 DPI"]):::process
    H(["Tesseract 4 LSTM\nlang: ind+eng\nPSM 3"]):::process
    I(["Regex Parser\n· Invoice no, tanggal, NPWP\n· Total, PPN, PPh\n· PO/DO number\n· Line items"]):::process
    J(["Confidence Scoring\nper field"]):::check
    K{{"confidence ≥ 0.88?"}}:::decision
    L{{"confidence 0.70–0.87?"}}:::decision
    M(["Pre-fill HIJAU\nVendor konfirmasi"]):::success
    N(["Pre-fill KUNING\nVendor WAJIB periksa\n+ tampil teks mentah OCR"]):::process
    O(["Field MERAH — kosong\nVendor isi manual\n+ tampil teks mentah sebagai hint"]):::error
    P(["Form review vendor\n→ Submit"]):::success

    A --> B
    B -->|Tidak OK| C
    B -->|OK| D
    D -->|Ya| E
    D -->|Tidak| F
    E --> I
    F --> G
    G --> H
    H --> I
    I --> J
    J --> K
    K -->|Ya| M
    K -->|Tidak| L
    L -->|Ya| N
    L -->|Tidak| O
    M & N & O --> P
```

**Akurasi ekspektasi (CPU Tesseract, tanpa GPU):**

| Kualitas Scan | DPI | Field numerik | Tabel/line items |
|---|:---:|:---:|:---:|
| Bersih + datar | ≥ 300 | ~87–90% | ~75–82% |
| Normal, sedikit miring | 200–300 | ~78–84% | ~65–72% |
| Buruk / terlipat | < 200 | ~55–68% | ~40–55% |

**Panduan upload (ditampilkan di UI):**
- ✓ PDF hasil scan, DPI ≥ 300
- ✓ Hitam-putih / grayscale lebih bersih dari berwarna
- ✓ Dokumen rata, tidak terlipat, tidak ada bayangan
- ✗ Foto dari kamera HP tidak disarankan

---

## 9. Multi-Company Architecture

> Satu Finance Portal DB berisi `res.company` untuk setiap PT Erajaya.
> Isolasi data via `company_id` pada semua model dokumen + budget + approval.

```mermaid
flowchart TB
    classDef holding fill:#8e44ad,color:#fff,stroke:#6c3483
    classDef pt      fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef shared  fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef config  fill:#d4860b,color:#fff,stroke:#a36008

    subgraph FPDB["Finance Portal DB (single DB)"]
        direction TB

        GRP["👤 Finance Group Manager\ncompany_ids = [PT-A, PT-B, PT-C, ...]\nDashboard: lihat semua PT"]:::holding

        subgraph PTA["res.company: PT ERA Busana Retailindo"]
            A1["Dokumen (company_id=PTA)\nCA · Reimb · Invoice · Travel"]:::pt
            A2["Approval Matrix (PTA)\nTax Approver A · Finance Approver A"]:::config
            A3["Budget (PTA + fiscal_year)"]:::config
        end

        subgraph PTB["res.company: PT Erajaya Swasembada"]
            B1["Dokumen (company_id=PTB)"]:::pt
            B2["Approval Matrix (PTB)\nTax Approver B · Finance Approver B"]:::config
            B3["Budget (PTB + fiscal_year)"]:::config
        end

        subgraph PTC["res.company: PT [Brand Lain]"]
            C1["Dokumen (company_id=PTC)"]:::pt
            C2["Approval Matrix (PTC)"]:::config
            C3["Budget (PTC + fiscal_year)"]:::config
        end

        subgraph SHARED["Shared across all companies"]
            VM["res.partner (Vendor Master)\nSatu vendor → supply ke banyak PT\nSatu akun portal vendor"]:::shared
            EM["hr.employee (Employee Master)\nDari HRIS sync · satu record per orang"]:::shared
            BNK["res.bank (Bank Master)"]:::shared
        end
    end

    GRP -.->|monitor| PTA & PTB & PTC
```

**Perubahan teknis di modul:**

```python
# Semua model dokumen + budget + approval matrix
company_id = fields.Many2one("res.company", required=True,
                              default=lambda self: self.env.company)

# Security rule: user hanya lihat dokumen company yang dia punya akses
[('company_id', 'in', self.env.user.company_ids.ids)]

# SAP outbound payload: sertakan company_code SAP
{
    "company_code": self.company_id.x_sap_company_code,
    ...
}
```

---

## 10. Budget & PR Validation

```mermaid
flowchart TD
    classDef process  fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef decision fill:#d4860b,color:#fff,stroke:#a36008
    classDef error    fill:#c0392b,color:#fff,stroke:#922b21
    classDef ok       fill:#2d6a4f,color:#fff,stroke:#1b4332

    A(["submit() dipanggil"]):::process
    B{{"amount >\n_finance_pr_threshold()?"}}:::decision
    C(["Resolve threshold:\n1. finance.limitation._resolve_for(doc)\n   (match: submission_type + division)\n2. Fallback: config param\n3. Default: Rp 1.000.000"]):::process
    D{{"pr_number diisi?"}}:::decision
    E(["UserError:\n'Pengajuan > Rp X wajib\nmenyertakan nomor PR'"]):::error
    F(["SapBridgeAdapter.lookup_pr()\n→ Bridge Redis Cache"]):::process
    G{{"Cache HIT?\nPR valid + open?"}}:::decision
    H(["UserError:\n'PR tidak ditemukan atau\nsudah closed di SAP'"]):::error
    I(["Cek budget:\nfinance.budget._check_document_budget()"]):::process
    J{{"enforce mode =\nhard (param=True)?"}}:::decision
    K{{"amount ≤ sisa budget?"}}:::decision
    L(["UserError:\n'Over budget divisi'"]):::error
    M(["Log warning over-budget\n(soft mode)"]):::process
    N(["Submit OK\n→ approval trigger\nstate: submitted"]):::ok

    A --> B
    B -->|Ya| C
    C --> D
    D -->|Tidak| E
    D -->|Ya| F
    F --> G
    G -->|Tidak| H
    G -->|Ya| I
    B -->|Tidak| I
    I --> J
    J -->|Ya| K
    K -->|Tidak| L
    K -->|Ya| N
    J -->|Tidak| M
    M --> N
```

---

## 11. Vendor Portal

```mermaid
sequenceDiagram
    autonumber
    actor VND   as Vendor
    participant ODO  as Odoo Vendor Portal
    participant ADPT as SapBridgeAdapter
    participant BRG  as Bridge Redis Cache

    VND  ->> ODO  : Login (/web/login — Odoo native)
    ODO  ->> ODO  : group_finance_vendor check\nRecord rule: vendor_id.user_ids ∋ user

    VND  ->> ODO  : GET /my/finance/po-list\n(lihat PO & GR milik vendor)
    ODO  ->> ADPT : lookup_po_gr(vendor_id=V-10001)
    ADPT ->> BRG  : GET /from-odoo/finance/po-gr/lookup<br/>(HMAC signed)
    BRG  -->> ADPT: PO/GR list dari Redis cache
    ODO  -->> VND : Daftar PO + GR + unbilled qty

    VND  ->> ODO  : POST /my/finance/invoice/new\n(upload scanned invoice PDF)
    ODO  ->> ODO  : OCR pipeline\n→ pre-fill form
    VND  ->> ODO  : Review + konfirmasi + submit
    ODO  ->> ODO  : Buat finance.vendor.invoice\nValidasi: po_non_trade wajib po_number

    VND  ->> ODO  : GET /my/finance/invoices\n(tracking status)
    ODO  -->> VND : Status + payment_plan_date dari SAP
```

---

## 12. Data Model (ERD Ringkas)

```mermaid
erDiagram
    FINANCE_DOCUMENT_MIXIN {
        int     company_id       "FK res.company (NEW)"
        char    state
        char    sap_sync_state
        char    sap_document_no
        date    sap_payment_plan_date
        char    sap_payment_status
        char    pr_number
        decimal amount_total
    }

    FINANCE_CASH_ADVANCE {
        char name
        date advance_date
        date expected_return_date
    }

    FINANCE_VENDOR_INVOICE {
        char name
        char invoice_subtype
        char po_number
        char gr_number
    }

    FINANCE_TRAVEL_SETTLEMENT {
        char hris_travel_id
        char settlement_state
    }

    FINANCE_BUDGET {
        int  company_id   "FK res.company (NEW)"
        int  fiscal_year
        int  division_id
        decimal total_budget
        decimal consumed_amount
    }

    APPROVAL_MATRIX {
        int  company_id   "FK res.company (NEW)"
        char model
        char condition_domain
    }

    RES_COMPANY {
        char name
        char x_sap_company_code  "Kode SAP per PT"
    }

    RES_PARTNER {
        char x_sap_external_id
        char npwp
        char bank_account_no
    }

    RES_COMPANY ||--o{ FINANCE_DOCUMENT_MIXIN : "company_id"
    RES_COMPANY ||--o{ FINANCE_BUDGET : "company_id"
    RES_COMPANY ||--o{ APPROVAL_MATRIX : "company_id"
    HR_EMPLOYEE ||--o{ FINANCE_CASH_ADVANCE : "employee_id"
    RES_PARTNER ||--o{ FINANCE_VENDOR_INVOICE : "vendor_id"
    FINANCE_DOCUMENT_MIXIN ||--|| FINANCE_CASH_ADVANCE : "inherits"
    FINANCE_DOCUMENT_MIXIN ||--|| FINANCE_VENDOR_INVOICE : "inherits"
    FINANCE_DOCUMENT_MIXIN ||--|| FINANCE_TRAVEL_SETTLEMENT : "inherits"
    FINANCE_BUDGET ||--o{ FINANCE_DOCUMENT_MIXIN : "soft-check on submit"
    APPROVAL_MATRIX ||--o{ FINANCE_DOCUMENT_MIXIN : "model binding"
```

---

## 13. Deployment

### 13.1 Finance Portal DB — Terpisah dari Existing

```mermaid
flowchart TB
    classDef nginx   fill:#27ae60,color:#fff,stroke:#1e8449
    classDef odoo    fill:#1168bd,color:#fff,stroke:#0d52a0
    classDef db      fill:#8e44ad,color:#fff,stroke:#6c3483
    classDef infra   fill:#6b6b6b,color:#fff,stroke:#4a4a4a
    classDef bridge  fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef warn    fill:#c0392b,color:#fff,stroke:#922b21

    subgraph VPS["VPS / On-Prem  —  Docker Compose"]
        NX["nginx :443\nTLS + reverse proxy"]:::nginx

        subgraph ODOO_STACK["Odoo Instance (shared)"]
            APP["odoo-app :8069\nmulti-worker\nFinance Portal modules"]:::odoo
            MGT["odoo-mgmt :8072\n1 worker · admin only"]:::odoo
        end

        subgraph PG["Postgres :5432"]
            EDBX["DB: existing_db\n(tidak disentuh)"]:::db
            FPDB["DB: finance_portal\n(Finance Portal — BARU)"]:::db
        end

        RD["Redis :6379\nqueue_job broker"]:::infra
        BRG["finance-sap-bridge :8080\ninternal only\nKafka ↔ HMAC REST\nRedis cache SAP data"]:::bridge
        FS[("filestore\n./data/odoo-filestore\nSHARED: app + mgmt ⚠️")]:::warn
    end

    subgraph CLIENT["Infrastruktur Klien (terpisah)"]
        KC["Keycloak :8443"]:::infra
        KF["Kafka Cluster"]:::infra
        SAPS["SAP S/4HANA"]:::infra
        HRISS["HRIS System"]:::infra
    end

    NX --> APP & MGT
    APP --> EDBX & FPDB & RD & FS
    MGT --> EDBX & FPDB & FS
    APP -->|"HMAC REST\ninternal"| BRG
    BRG -->|"Kafka TLS"| KF
    KF <-->|Events| SAPS & HRISS
    APP -->|OIDC| KC
```

> ⚠️ `odoo-app` dan `odoo-mgmt` **wajib** mount volume `./data/odoo-filestore` yang sama.

### 13.2 DB Routing via nginx

```nginx
# nginx.conf — routing ke DB yang tepat via subdomain/path
server {
    server_name finance.erajaya.com;
    location / {
        proxy_pass http://odoo-app:8069;
        proxy_set_header X-Odoo-dbfilter "^finance_portal$";
    }
}
server {
    server_name erp.erajaya.com;    # existing DB
    location / {
        proxy_pass http://odoo-app:8069;
        proxy_set_header X-Odoo-dbfilter "^existing_db$";
    }
}
```

### 13.3 Urutan Deploy Finance Portal

```bash
# 1. Buat DB baru
make create-db DB=finance_portal

# 2. Install modul
make install MODULE=custom_finance_portal      DB=finance_portal
make install MODULE=custom_finance_budget      DB=finance_portal
make install MODULE=custom_finance_portal_sap  DB=finance_portal
make install MODULE=custom_finance_portal_sso  DB=finance_portal

# 3. Restart wajib (Python tidak re-import dari make update)
docker compose restart odoo-app

# 4. Deploy bridge
docker compose up -d finance-sap-bridge

# 5. Konfigurasi di Odoo (Settings):
#    - Bridge URL + HMAC secret
#    - Keycloak OAuth provider
#    - res.company per PT Erajaya + x_sap_company_code
#    - Approval matrix per company
#    - Aktifkan cron sync master
```

---

## 14. Data yang Dikonsumsi Odoo (via Kafka → Bridge Cache)

> **SEMUA data dari SAP/HRIS masuk ke Odoo melalui Kafka → Bridge Redis cache → Bridge REST.**
> Bridge tidak pernah call SAP REST langsung. Odoo tidak pernah call Kafka langsung.

### 14.1 Master Data dari SAP (cron-push via Kafka)

#### Supplier / Vendor Master — topik: `sap.to.portal.vendor-master`

| Field | Tipe | Wajib | Keterangan |
|---|---|:---:|---|
| `external_id` | String | ✓ | Natural key upsert `x_sap_external_id` → `res.partner` |
| `name` | String | ✓ | Nama vendor |
| `npwp` | String `[PDP]` | ✓ | Validasi pajak; masking non-finance |
| `street`, `city`, `country_code` | String | ✓ | Alamat |
| `bank_account_no` | String `[PDP]` | ✓ | Rekening payment; masking 4 digit terakhir |
| `bank_name` | String | ✓ | Nama bank |
| `currency_code` | String (ISO 4217) | ✓ | Matching dokumen |
| `payment_terms_days` | Integer | — | Informasi SLA |
| `is_active` | Boolean | ✓ | Nonaktifkan vendor yang tidak berlaku |
| `sap_company_codes` | Array[String] | ✓ | PT mana saja yang bisa pakai vendor ini |

#### Division / Cost Center — topik: `sap.to.portal.vendor-master`

| Field | Tipe | Wajib | Keterangan |
|---|---|:---:|---|
| `external_id` | String | ✓ | Natural key → `finance.vertical` |
| `name`, `code` | String | ✓ | Label + kode SAP |
| `company_code` | String | ✓ | Mapping ke `res.company` |
| `is_active` | Boolean | ✓ | Filter dropdown |

#### Cost Budget — topik: `sap.to.portal.budget-master`

| Field | Tipe | Wajib | Keterangan |
|---|---|:---:|---|
| `external_id` | String | ✓ | Natural key → `finance.budget` |
| `division_external_id` | String | ✓ | FK ke `finance.vertical` |
| `fiscal_year` | Integer | ✓ | Period matching |
| `total_budget` | Decimal | ✓ | Ceiling budget check |
| `company_code` | String | ✓ | Mapping ke `res.company` |

### 14.2 Lookup via Bridge Cache

#### PR Lookup — Bridge GET `/from-odoo/finance/pr/lookup`

| Field Response | Wajib | Keterangan |
|---|:---:|---|
| `pr_number` | ✓ | Konfirmasi |
| `is_valid` | ✓ | Tolak submit jika `false` |
| `status` | ✓ | `open`/`partial`/`closed`/`cancelled` |
| `pr_description` | ✓ | Tampil di form sebagai konfirmasi |
| `total_value`, `remaining_value` | ✓ | Ceiling validasi |
| `currency_code` | ✓ | Normalisasi |
| `cost_center_external_id` | ✓ | Auto-fill divisi |

```json
{
  "pr_number": "PR-2025-00123",
  "is_valid": true,
  "status": "open",
  "pr_description": "Pengadaan ATK Q1 2025",
  "total_value": 5000000.00,
  "remaining_value": 5000000.00,
  "currency_code": "IDR",
  "cost_center_external_id": "CC-FINANCE-01"
}
```

#### PO/GR Lookup — Bridge GET `/from-odoo/finance/po-gr/lookup`

| Field Response | Wajib | Keterangan |
|---|:---:|---|
| `po_number`, `po_status` | ✓ | Validasi bisa ditagihkan |
| `vendor_external_id` | ✓ | Validasi vendor = yang login |
| `total_po_value`, `currency_code` | ✓ | Ceiling invoice |
| `items[].po_line`, `.description` | ✓ | Baris invoice |
| `items[].unbilled_quantity` | ✓ | Sisa yang bisa ditagih |
| `items[].gr_number` | — | GR reference |

### 14.3 Inbound Webhook dari SAP

#### Posting Confirmation — topik: `sap.to.portal.posting-confirm`

```json
{
  "odoo_ref": "CA/2025/00042",
  "sap_document_no": "5100000123",
  "sap_posting_date": "2025-01-08",
  "event_type": "posted"
}
```

#### Payment Status — topik: `sap.to.portal.payment-status`

```json
{
  "odoo_ref": "CA/2025/00042",
  "sap_document_no": "5100000123",
  "event_type": "payment_scheduled",
  "payment_plan_date": "2025-01-15",
  "payment_amount": 3500000.00,
  "payment_currency": "IDR"
}
```

### 14.4 Data HRIS — topik: `hris.to.portal.*`

#### Employee Master

| Field | Wajib | PDP | Keterangan |
|---|:---:|:---:|---|
| `employee_id` | ✓ | | Natural key → `hr.employee` |
| `name`, `email` | ✓ | | Login SSO matching |
| `division_external_id`, `cost_center_external_id` | ✓ | | Auto-fill + budget scope |
| `bank_account_no`, `bank_name` | ✓ | ✓ | Rekening payment |
| `nik` | ✓ | ✓ | UU PDP; masking non-privileged |
| `employment_status` | ✓ | | Blokir pengajuan jika `inactive` |

#### Travel Request

| Field | Wajib | Keterangan |
|---|:---:|---|
| `hris_travel_id` | ✓ | Natural key → `finance.travel.settlement` |
| `employee_id` | ✓ | FK |
| `purpose`, `destination_city` | ✓ | Tampil di form |
| `departure_date`, `return_date` | ✓ | Periode |
| `approved_advance` | ✓ | Ceiling realisasi |
| `status` | ✓ | Filter: hanya `approved`/`travelling` |
| `allowance_items[]` | ✓ | Rincian per hari (per_diem, transport, accommodation) |

### 14.5 Readiness Tracker

| # | Data Feed | Kafka Topic | Frekuensi | **Status** | Blocker |
|---|---|---|---|:---:|---|
| 1 | Supplier/Vendor | `sap.to.portal.vendor-master` | Daily+change | `TBD` | Vendor Invoice |
| 2 | Division/Cost Center | `sap.to.portal.vendor-master` | Daily | `TBD` | Budget check |
| 3 | Cost Budget | `sap.to.portal.budget-master` | Daily+revision | `TBD` | Budget enforcement |
| 4 | Item Category | `sap.to.portal.item-category` | Weekly | `TBD` | Dropdown kosong |
| 5 | Approval Matrix | `sap.to.portal.vendor-master` | Daily | `TBD` | W: manual config |
| 6 | Bank Master | `sap.to.portal.bank-master` | Weekly | `TBD` | W: manual input |
| 7 | **PR Master (event-driven)** | `sap.to.portal.pr-master` | **Event** | `TBD` | **PR validation** |
| 8 | **PO/GR Master (event-driven)** | `sap.to.portal.po-gr-master` | **Event** | `TBD` | **Vendor Invoice PO** |
| 9 | Posting Confirmation | `sap.to.portal.posting-confirm` | Event | `TBD` | State → posted |
| 10 | Payment Status | `sap.to.portal.payment-status` | Event | `TBD` | Payment tracking |
| 11 | Employee Master | `hris.to.portal.employee-master` | Daily+change | `TBD` | User onboarding |
| 12 | Travel Request | `hris.to.portal.travel-request` | Event | `TBD` | Travel Settlement |

**Legend:** `✅ Ready` · `⚠️ Partial` · `❌ Not Ready` · `TBD` = diisi tim SAP/HRIS klien saat M1

### 14.6 Outbound Payloads (Odoo → Bridge → Kafka → SAP)

#### Cash Advance GL Posting

```json
{
  "odoo_ref": "CA/2025/00042",
  "doc_type": "cash_advance",
  "company_code": "1000",
  "posting_date": "2025-01-08",
  "employee_id": "EMP-00234",
  "cost_center_external_id": "CC-FINANCE-01",
  "currency_code": "IDR",
  "total_amount": 3500000.00,
  "pr_number": "PR-2025-00010",
  "bank_account_no": "1234567890",
  "bank_name": "BCA",
  "lines": [
    {"item_external_id": "ITEM-001", "description": "Tiket pesawat", "amount": 1000000.00},
    {"item_external_id": "ITEM-002", "description": "Hotel 2 malam", "amount": 1600000.00}
  ],
  "attachments": [{"filename": "surat_tugas.pdf", "content_base64": "..."}]
}
```

#### Vendor Invoice MIRO

```json
{
  "odoo_ref": "INV/2025/00015",
  "doc_type": "vendor_invoice",
  "invoice_subtype": "po_non_trade",
  "company_code": "1000",
  "vendor_external_id": "V-10001",
  "invoice_date": "2025-01-05",
  "vendor_invoice_no": "INV-VENDOR-2024-456",
  "po_number": "PO-2024-00456",
  "currency_code": "IDR",
  "amount_net": 25000000.00,
  "tax_code": "PPh23_2pct",
  "tax_amount": 500000.00,
  "total_amount": 24500000.00,
  "cost_center_external_id": "CC-FINANCE-01",
  "lines": [
    {"po_line": 1, "gr_number": "GR-2024-00789", "description": "Jasa IT", "quantity": 1.0, "unit_price": 25000000.00}
  ],
  "attachments": [
    {"filename": "invoice_vendor.pdf", "content_base64": "..."},
    {"filename": "faktur_pajak.pdf", "content_base64": "..."}
  ]
}
```

---

## 15. PDP Compliance

| Field | Model | Klasifikasi | Perlakuan |
|---|---|---|---|
| `nik` | `hr.employee` | Spesifik (UU PDP Pasal 4) | `pdp_class="specific"` + masking view non-privileged |
| `bank_account_no` | `res.partner`, `hr.employee` | Spesifik | Masking 4 digit terakhir; full hanya `group_finance_officer`+ |
| `npwp` | `res.partner` | Spesifik | Masking 6 digit tengah; full hanya `group_finance_officer`+ |
| Transisi state semua dokumen | `finance.document.mixin` | — | `pdp.audited.mixin` → `INSERT INTO pdp.audit_log` (raw SQL) |
| Log adapter call | `custom.adapter.call.log` | — | `BaseAdapter._sanitize_log()` strip field PDP sebelum logging |

---

## 16. Ringkasan Komponen

| Komponen | Stack | Lokasi | In-Scope Build |
|---|---|---|:---:|
| `custom_finance_portal` | Odoo 19 Python/XML | `addons/ee_gap/custom_finance_portal/` | ✅ |
| `custom_finance_budget` | Odoo 19 Python/XML | `addons/ee_gap/custom_finance_budget/` | ✅ |
| `custom_finance_portal_sap` | Odoo 19 Python/XML | `addons/ee_gap/custom_finance_portal_sap/` | ✅ |
| `custom_finance_portal_sso` | Odoo 19 Python/XML | `addons/ee_gap/custom_finance_portal_sso/` | ✅ |
| `finance-sap-bridge` | FastAPI Python 3.12 + Redis | `services/finance-sap-bridge/` | ✅ scaffold |
| OCR service | pdfplumber + Tesseract + OpenCV | `services/ocr-service/` atau inline bridge | ✅ |
| Keycloak | Keycloak 24+ | Infra klien | ❌ |
| Kafka + Konektor | Confluent / MSK | Infra klien | ❌ |
| SAP S/4HANA + Kafka producer | ABAP / CPI | Tim SAP klien | ❌ |
| HRIS + Kafka producer | Vendor HRIS | Tim HC klien | ❌ |
