# Detail Estimasi Build — Finance Portal (Odoo)
## Breakdown per Fitur — Fase Build (Fase 3 dari 7)

| | |
|---|---|
| **Dokumen** | Project Estimation Detail — Build Phase, Finance Portal (Odoo) |
| **Versi** | 1.1 |
| **Tanggal** | 2026-07-01 |
| **Referensi** | Project-Estimation-Odoo-Finance-Portal.md (Section 5) |
| **Scope** | Odoo-only. SAP dev, HC/HRIS dev, Kafka connector = **Out of Scope** |

> **Catatan penting:** Dokumen ini adalah breakdown detail **Fase 3 (Build/Development)** saja.
> Total fase Build (tanpa PMO) = **BA 35 + Dev 123 + QA 44 = 202 mandays**.
> Total proyek keseluruhan (7 fase, tanpa PMO, dengan kontingensi 15%) = **408 mandays**.
> Total proyek termasuk PMO (54) = **462 mandays** — sesuai Project Charter.

---

## Rumus Kompleksitas

| Complexity | BA | Dev | QA | Total/baris |
|:---:|---:|---:|---:|---:|
| Low | 0.5 | 1.5 | 0.5 | **2.5** |
| Medium | 1 | 3 | 1 | **5** |
| High | 2 | 5 | 2 | **9** |

> Beberapa baris menggunakan nilai kustom (bukan formula di atas) karena ada reuse komponen atau skala tugas yang tidak pas di satu kategori.

---

## A. Foundation & SSO
> Subtotal target: **BA=2 · Dev=12 · QA=3**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| A.1 | Foundation | Multi-company base scaffold | Manifest, `__init__`, `__manifest__`, install check, base model mixin | `custom_finance_portal` | Internal | Low | 0 | 2 | 0.5 | **2.5** |
| A.2 | Foundation | Keycloak SSO sisi Odoo | `auth_oauth` config, role mapping, tenant isolation, redirect URI | `custom_finance_portal_sso` | SSO/Keycloak | High | 1 | 6 | 1.5 | **8.5** |
| A.3 | Foundation | Security groups & access rules | Groups per role (Submitter/Tax/Finance/Admin), record rules | `custom_finance_portal` | Internal | Low | 0.5 | 2 | 0.5 | **3** |
| A.4 | Foundation | CI/CD & static validation | `py_compile`, XML/ACL lint, install smoke test script | DevOps | Internal | Low | 0 | 1 | 0 | **1** |
| A.5 | Foundation | Vendor Portal SSO login | Vendor login flow (auth_oauth), session management sisi Odoo | `custom_finance_portal` | SSO/Keycloak | Low | 0.5 | 1 | 0.5 | **2** |
| | | | | | | **Subtotal A** | **2** | **12** | **3** | **17** |

---

## B. Master Data & Sync (Odoo-side)
> Subtotal target: **BA=6 · Dev=14 · QA=4**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| B.1 | Master Data | Submission Type | Model CRUD + seed data (CA, Expense, PD, Invoice) | `custom_finance_portal` | Internal | Low | 0.5 | 0.5 | 0 | **1** |
| B.2 | Master Data | Invoice Routine Type | Model CRUD (Routine / Non-Routine) | `custom_finance_portal` | Internal | Low | 0.5 | 0.5 | 0 | **1** |
| B.3 | Master Data | Invoice Type | Model CRUD (PO / Non-PO Non-Trade) | `custom_finance_portal` | Internal | Low | 0.5 | 0.5 | 0 | **1** |
| B.4 | Master Data | Item Category | Odoo model + upsert idempoten dari SAP webhook | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| B.5 | Master Data | Item of Submission | Odoo model + upsert idempoten dari SAP webhook | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| B.6 | Master Data | Supplier / Vendor Master | Upsert `res.partner` dari SAP webhook, dedup by vendor code | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| B.7 | Master Data | COA (Chart of Accounts) | Upsert `account.account` (filter GL relevan) dari SAP | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 1 | **3.5** |
| B.8 | Master Data | Cost Budget per Divisi | Model budget + upsert dari SAP | `custom_finance_budget` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| B.9 | Master Data | Approval Matrix (Submission) | Upsert approval matrix + mapping approver Odoo user | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| B.10 | Master Data | Finance Approval Matrix | CRUD local (mapping PIC Finance per vertical) | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| B.11 | Master Data | Vertical / Business Plant | Upsert dari SAP, linked ke `res.company` | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 0.5 | 0 | **1** |
| B.12 | Master Data | User Master (sync dari SAP/HRIS) | Upsert `res.users` + cron job scheduler | `custom_finance_portal_sap` | SAP-API/HRIS | Low | 0 | 0.5 | 0 | **0.5** |
| B.13 | Master Data | User Role (sync dari SAP) | Upsert `res.groups` mapping dari role SAP | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 0.5 | 0.5 | **1.5** |
| | | | | | | **Subtotal B** | **6** | **14** | **4** | **24** |

---

## C. Cash Advance + Cash Advance Realization
> Subtotal target: **BA=4 · Dev=14 · QA=5**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| C.1 | Cash Advance | Request CA — List & Filter | List/kanban view, search panel, filter status/date, search by CA number | `custom_finance_portal` | Internal | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| C.2 | Cash Advance | Request CA — Create/Edit form | Form semua field: CA No, PR/PO, requester, NIK, company, division, amount, tgl payment, metode, bank, rekening, penerima, approver, note | `custom_finance_portal` | Internal | High | 1 | 3 | 1 | **5** |
| C.3 | Cash Advance | Validasi PR (> Rp 1jt wajib PR) | Constraint + lookup nomor PR dari SAP (real-time) | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| C.4 | Cash Advance | Approval workflow Tax→Finance | Approval engine (2 level: Tax Review → Finance Review) | `custom_finance_portal` | Internal | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| C.5 | Cash Advance | Push CA ke SAP | Adapter: POST ke SAP endpoint, async via `queue_job` | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| C.6 | CA Realization | Realization CA — List & Filter | List view, filter by CA / status | `custom_finance_portal` | Internal | Low | 0 | 0.5 | 0.5 | **1** |
| C.7 | CA Realization | Realization CA — Create/Edit form | Link ke CA asal, tabel detail realisasi, sisa budget, tgl realisasi | `custom_finance_portal` | Internal | Medium | 1 | 2 | 1 | **4** |
| C.8 | CA Realization | Approval Realization Tax→Finance | Reuse approval engine (beda state machine) | `custom_finance_portal` | Internal | Low | 0 | 0.5 | 0.5 | **1** |
| C.9 | CA Realization | Terima status payment dari SAP | Webhook handler: update state CA + notif user | `custom_finance_portal_sap` | SAP-API | Low | 0 | 0.5 | 0 | **0.5** |
| | | | | | | **Subtotal C** | **4** | **14** | **5** | **23** |

---

## D. Reimbursement & Expenses
> Subtotal target: **BA=3 · Dev=9 · QA=4**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| D.1 | Reimb. | List & Filter | List view, filter by status/type/date | `custom_finance_portal` | Internal | Low | 0 | 1.5 | 0.5 | **2** |
| D.2 | Reimb. | Create/Edit form | Form field expense/reimbursement + attachment | `custom_finance_portal` | Internal | High | 1 | 3 | 1 | **5** |
| D.3 | Reimb. | Validasi PR (> Rp 1jt wajib PR) | Reuse constraint + SAP PR lookup dari C.3 | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 0.5 | 0.5 | **1.5** |
| D.4 | Reimb. | Approval workflow Tax→Finance | Reuse approval engine | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| D.5 | Reimb. | Push expense ke SAP | Adapter: POST ke SAP endpoint, async via `queue_job` | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| D.6 | Reimb. | Terima status payment dari SAP | Webhook handler (reuse dari C.9, beda state) | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1 | 1 | **2.5** |
| | | | | | | **Subtotal D** | **3** | **9** | **4** | **16** |

---

## E. Vendor Invoice (Non-PO & PO Non-Trade) + Vendor Portal
> Subtotal target: **BA=4 · Dev=18 · QA=6**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| E.1 | Inv. Non-PO | List & Filter | List view + filter status/date/vendor | `custom_finance_portal` | Internal | Low | 0 | 1.5 | 0.5 | **2** |
| E.2 | Inv. Non-PO | Create/Edit form Non-PO | Form view: nomor inv, GL Account, COA, attachment, approval | `custom_finance_portal` | Internal | High | 1 | 3 | 1 | **5** |
| E.3 | Inv. Non-PO | Approval workflow Tax→Finance | Reuse approval engine | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| E.4 | Inv. Non-PO | Push MIRO posting ke SAP | Adapter: POST invoice posting ke SAP, async `queue_job` | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 1 | **3.5** |
| E.5 | Inv. PO | List & Filter PO-linked | List view + lookup PO/GR dari SAP | `custom_finance_portal` | SAP-API | Low | 0 | 1.5 | 0.5 | **2** |
| E.6 | Inv. PO | Create form PO-linked | Auto-populate dari PO/GR SAP, validasi qty/nilai GR | `custom_finance_portal_sap` | SAP-API | High | 1 | 3 | 1 | **5** |
| E.7 | Inv. PO | Approval workflow Tax→Finance | Reuse approval engine | `custom_finance_portal` | Internal | Low | 0 | 1 | 0.5 | **1.5** |
| E.8 | Inv. PO | Push MIRO posting ke SAP | Adapter (reuse E.4, beda payload PO-linked) | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 1.5 | 0.5 | **2.5** |
| E.9 | Vendor Portal | Login Vendor (SSO) + landing | Vendor auth flow via `auth_oauth`, landing page submit invoice | `custom_finance_portal` | SSO/Keycloak | Low | 0.5 | 2 | 0.5 | **3** |
| E.10 | Vendor Portal | Submit invoice + tracking status | Vendor-facing simplified form + polling status dari SAP | `custom_finance_portal_sap` | SAP-API | Low | 0 | 1.5 | 0.5 | **2** |
| | | | | | | **Subtotal E** | **4** | **18** | **6** | **28** |

---

## F. Perjalanan Dinas (Request + Realization)
> Subtotal target: **BA=3 · Dev=7 · QA=3**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| F.1 | PD Request | List & Filter | List view + filter by date/status | `custom_finance_portal` | HRIS-API | Low | 0 | 1 | 0.5 | **1.5** |
| F.2 | PD Request | Create/Edit form Request PD | Form field sesuai kontrak HRIS: tujuan, tanggal, anggaran, tipe PD | `custom_finance_portal` | HRIS-API | Medium | 1 | 2 | 0.5 | **3.5** |
| F.3 | PD Request | Approval workflow Tax→Finance | Reuse approval engine | `custom_finance_portal` | Internal | Low | 0.5 | 0.5 | 0 | **1** |
| F.4 | PD Realization | List & Filter Realization | List view | `custom_finance_portal` | Internal | Low | 0 | 1 | 0.5 | **1.5** |
| F.5 | PD Realization | Create/Edit Realization form | Settlement: link ke PD asal, actual expense, lampiran bukti | `custom_finance_portal` | Internal | Low | 1 | 1.5 | 1 | **3.5** |
| F.6 | PD Realization | Approval Realization | Reuse approval engine | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| | | | | | | **Subtotal F** | **3** | **7** | **3** | **13** |

---

## G. Budget Control + Aturan PR/PO/GR
> Subtotal target: **BA=3 · Dev=8 · QA=3**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| G.1 | Budget Control | Budget limit check per divisi | Computed field sisa budget pada form dokumen | `custom_finance_budget` | Internal | Low | 0.5 | 2 | 0.5 | **3** |
| G.2 | Budget Control | Validasi & lookup PR number (≥ Rp 1jt) | SAP PR lookup adapter + onchange constraint | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| G.3 | Budget Control | Lookup & validasi PO/GR (vendor invoice PO) | SAP PO/GR adapter + populate fields | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 0.5 | **3** |
| G.4 | Budget Control | Remaining budget display (computed real-time) | Computed field: budget - committed - realisasi | `custom_finance_budget` | Internal | Low | 0.5 | 1 | 0 | **1.5** |
| G.5 | Budget Control | Alert + blocking rule over-budget | Warning popup + hard-block state constraint | `custom_finance_budget` | Internal | Low | 1 | 1 | 1.5 | **3.5** |
| | | | | | | **Subtotal G** | **3** | **8** | **3** | **14** |

---

## H. Integration Odoo-side (Adapter + Async Job + Webhook + Sync Log)
> Subtotal target: **BA=4 · Dev=16 · QA=6**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| H.1 | Integration | Adapter base (REST caller + retry) | Base class HTTP REST caller, timeout, retry 3x, error mapping | `custom_finance_portal_sap` | SAP-API | High | 1 | 3 | 1 | **5** |
| H.2 | Integration | Push job async via `queue_job` | CA, expense, MIRO push job + priority queue | `custom_finance_portal_sap` | Internal | Low | 0.5 | 3 | 1 | **4.5** |
| H.3 | Integration | Webhook receiver + HMAC validator | HTTP controller endpoint, signature validation, dispatch handler | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 3 | 1 | **4.5** |
| H.4 | Integration | Sync log menu | Tree/form view log (sukses/gagal/pending) per dokumen + retry button | `custom_finance_portal_sap` | Internal | Low | 0.5 | 3 | 1 | **4.5** |
| H.5 | Integration | Master data upsert cron (scheduler) | `ir.cron` jobs untuk upsert harian semua master dari SAP | `custom_finance_portal_sap` | SAP-API | Low | 0.5 | 2 | 1 | **3.5** |
| H.6 | Integration | Dead-letter retry + alert email | `queue_job` failure handler, email notification ke admin | `custom_finance_portal_sap` | Internal | Low | 1 | 2 | 1 | **4** |
| | | | | | | **Subtotal H** | **4** | **16** | **6** | **26** |

---

## I. Reporting + Dashboard
> Subtotal target: **BA=3 · Dev=12 · QA=4**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| I.1 | Dashboard | Cash Advance Dashboard | Stat blocks (New/On Process/Reject/Pending) + filter date + search CA# | OWL/`ir.ui.view` | Internal | Low | 0.5 | 2 | 0.5 | **3** |
| I.2 | Dashboard | Reimbursement Dashboard | Stat blocks + list mini | OWL/`ir.ui.view` | Internal | Low | 0 | 1 | 0 | **1** |
| I.3 | Dashboard | Invoice Vendor Dashboard (Non-PO & PO) | Stat blocks + filter | OWL/`ir.ui.view` | Internal | Low | 0 | 1 | 0 | **1** |
| I.4 | Dashboard | Perjalanan Dinas Dashboard | Stat blocks + list mini | OWL/`ir.ui.view` | Internal | Low | 0 | 1 | 0 | **1** |
| I.5 | Reporting | Login log | Wrapper `ir.logging` + list view + filter user/date | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| I.6 | Reporting | Transaction audit log | Audit trail model (create/update/approve/reject) + wizard export | `custom_finance_portal` | Internal | Low | 0.5 | 2 | 1 | **3.5** |
| I.7 | Reporting | Cash Advance report (Excel/PDF) | QWeb report template + xlsx export | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| I.8 | Reporting | Reimbursement report | QWeb report template + xlsx export | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| I.9 | Reporting | Invoice Vendor report | QWeb report template + xlsx export | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| I.10 | Reporting | Sync log report / export | List view + CSV export | `custom_finance_portal_sap` | Internal | Low | 0 | 1 | 0.5 | **1.5** |
| | | | | | | **Subtotal I** | **3** | **12** | **4** | **19** |

---

## J. Configuration
> Subtotal target: **BA=2 · Dev=4 · QA=2**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| J.1 | Configuration | Finance Portal settings panel | `ir.config_parameter` + settings view (base URL SAP, secret token, flags) | `custom_finance_portal` | Internal | Low | 1 | 2 | 0.5 | **3.5** |
| J.2 | Configuration | Limitation for Submission master | Model + CRUD view (limit per submission type/divisi) | `custom_finance_portal` | Internal | Low | 0.5 | 1 | 0.5 | **2** |
| J.3 | Configuration | Sync config (endpoint, topic, token) | Settings form per integrasi (SAP/HRIS) + test-connection button | `custom_finance_portal_sap` | Internal | Low | 0.5 | 1 | 1 | **2.5** |
| | | | | | | **Subtotal J** | **2** | **4** | **2** | **8** |

---

## K. Non-Functional (PDP, Security, Performance, Resilience)
> Subtotal target: **BA=1 · Dev=9 · QA=4**

| No | Modul | Menu / Fitur | Sub-Fitur / Task Odoo | Komponen Odoo | Interfacing | Complexity | BA | Dev | QA | Total |
|---|---|---|---|---|---|:---:|---:|---:|---:|---:|
| K.1 | Non-functional | PDP classification audit | Data category fields, access log, `custom_pdp_classification` reuse | `custom_pdp_classification` | Internal | Low | 0.5 | 2 | 1 | **3.5** |
| K.2 | Non-functional | Security hardening | SQL injection, XSS, IDOR review + perbaikan sisi Odoo | All modules | Internal | Low | 0 | 2 | 1 | **3** |
| K.3 | Non-functional | Performance (N+1 / prefetch) | Profiling query, tambah `prefetch_ids`, pagination | All modules | Internal | Low | 0 | 2 | 1 | **3** |
| K.4 | Non-functional | Resilience (circuit breaker + timeout) | Adapter timeout config, fallback state, exponential backoff | `custom_finance_portal_sap` | Internal | Low | 0.5 | 3 | 1 | **4.5** |
| | | | | | | **Subtotal K** | **1** | **9** | **4** | **14** |

---

## Rekap Fase Build

| Workstream | BA | Dev | QA | Total |
|---|---:|---:|---:|---:|
| A. Foundation & SSO | 2 | 12 | 3 | **17** |
| B. Master Data & Sync | 6 | 14 | 4 | **24** |
| C. Cash Advance + Realization | 4 | 14 | 5 | **23** |
| D. Reimbursement & Expenses | 3 | 9 | 4 | **16** |
| E. Vendor Invoice + Vendor Portal | 4 | 18 | 6 | **28** |
| F. Perjalanan Dinas | 3 | 7 | 3 | **13** |
| G. Budget Control + PR/PO/GR | 3 | 8 | 3 | **14** |
| H. Integration Odoo-side | 4 | 16 | 6 | **26** |
| I. Reporting + Dashboard | 3 | 12 | 4 | **19** |
| J. Configuration | 2 | 4 | 2 | **8** |
| K. Non-Functional | 1 | 9 | 4 | **14** |
| **Subtotal Build** | **35** | **123** | **44** | **202** |

---

## Rekap Total Proyek (semua fase)

| Fase | PMO | BA | Dev | QA | Total |
|---|---:|---:|---:|---:|---:|
| 1. Requirement & Analysis | 8 | 22 | 3 | 4 | **37** |
| 2. Design (FSD/TSD) | 3 | 8 | 10 | 6 | **27** |
| **3. Build (detail di atas)** | **18** | **35** | **123** | **44** | **220** |
| 4. SIT | 5 | 6 | 12 | 16 | **39** |
| 5. UAT | 5 | 12 | 12 | 8 | **37** |
| 6. Cutover & Go-Live | 4 | 5 | 8 | 3 | **20** |
| 7. Hypercare | 4 | 5 | 9 | 3 | **21** |
| **Subtotal** | **47** | **93** | **177** | **84** | **401** |
| Kontingensi 15% | 7 | 14 | 27 | 13 | **61** |
| **TOTAL** | **54** | **107** | **204** | **97** | **≈ 462** |

---

## Catatan

- **Reuse** komponen (approval engine, adapter base, PR lookup) diperhitungkan: baris D.3, E.7, F.3, F.6 menggunakan estimasi lebih rendah karena memanfaatkan modul yang dibangun di C/E.
- **Kafka connector** (SAP↔Kafka, Kafka↔Portal) tidak ada di tabel ini — tanggung jawab tim integrasi klien.
- **SAP ABAP/CPI** (posting GL, MIRO, expose PR/PO/GR non-trade) tidak ada di tabel ini — tanggung jawab tim SAP klien.
- **HRIS** (konektor travel, employee master) tidak ada di tabel ini — tanggung jawab tim HC/HRIS klien.
- Baris bertanda `(reuse)` dapat dikerjakan paralel dengan backlog sprint sebelumnya untuk menekan durasi.
