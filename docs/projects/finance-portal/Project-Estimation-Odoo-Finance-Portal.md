# Project Document — Finance Portal on Odoo
## Estimasi Effort (Mandays) & Timeline — **Scope Odoo Only**

| | |
|---|---|
| **Dokumen** | Project Estimation — Finance Portal (Odoo) |
| **Versi** | 1.0 |
| **Tanggal** | 2026-06-23 |
| **Sumber requirement** | "Finance Portal - Integration.xlsx" |
| **Arsitektur** | Odoo = *System of Engagement*; SAP S/4HANA = *System of Record* |
| **Scope effort** | **Hanya pengembangan di Odoo.** Effort di SAP & HC/HRIS **DIKELUARKAN** |

---

## 1. Ringkasan Eksekutif

Pembangunan **Finance Portal** di atas Odoo 19 sebagai lapisan *engagement* di depan SAP:
Cash Advance (+ Realization), Reimbursement & Expenses, Vendor Invoice (PO / Non-PO
Non-Trade) + Vendor Portal, Perjalanan Dinas (settlement), dengan approval **Tax → Finance**,
budget/PR validation, master-data sync, SSO (Keycloak), dan reporting.

| Metrik | Nilai |
|---|---:|
| **Total effort (tanpa kontingensi)** | **401 mandays** |
| **Total effort (dengan kontingensi 15%)** | **≈ 462 mandays** |
| **Durasi** | **≈ 24 minggu (±6 bulan)** |
| **Komposisi tim** | 1 PMO (PT), 1–2 BA, 2–3 Developer, 1–2 QA |

> Effort di atas **murni Odoo**. Pengembangan konektor SAP, perubahan SAP (GL/MIRO/posting),
> serta konektor & perubahan HC/HRIS adalah tanggung jawab tim klien dan **tidak** dihitung di sini.

---

## 2. Ruang Lingkup

### 2.1 In-Scope (Odoo)
- 4 modul Odoo: `custom_finance_portal`, `custom_finance_budget`,
  `custom_finance_portal_sap` (adapter sisi Odoo), `custom_finance_portal_sso`.
- Dokumen + workflow approval Tax→Finance, budget control, aturan PR > Rp 1jt.
- **Adapter sisi Odoo** ke kontrak REST integrasi (memanggil/menyediakan endpoint), upsert
  master idempoten, webhook status (HMAC), push job async (`queue_job`), sync log + menu.
- SSO Keycloak (config `auth_oauth` + role mapping) di sisi Odoo.
- Vendor Portal (login SSO, submit invoice, tracking) di Odoo.
- Reporting, dashboard, konfigurasi, security/PDP audit, hardening sisi Odoo.

### 2.2 Out-of-Scope (DIKELUARKAN dari effort ini)
| Area | Penjelasan | Pemilik |
|---|---|---|
| **SAP development** | ABAP/CPI/PI/OData, posting GL/journal/MIRO, expose PR/PO/GR non-trade + nilai/status, payment list, attachment SAP Basis, approval status PO | Tim SAP klien |
| **HC / HRIS development** | Konektor HRIS→Kafka, perubahan modul travel, ekstraksi employee master | Tim HC/HRIS klien |
| **Kafka & konektor Kafka↔Portal** | Cluster Kafka, topik, konektor SAP↔Kafka & Kafka↔Portal (sesuai bagian "Kafka" pada spreadsheet) | Tim integrasi/Kafka klien |
| **Infrastruktur non-Odoo** | Provisioning Keycloak server, jaringan, sertifikat | Tim infra klien |

> Sisi Odoo **build terhadap kontrak** (JSON + topik) yang sudah disepakati, sehingga dapat
> dikerjakan paralel dengan tim SAP/Kafka/HC. Scaffold bridge (referensi) sudah tersedia dan
> dapat diserahkan ke tim Kafka sebagai acuan — **tidak dibilling** di estimasi ini.

---

## 3. Asumsi
1. **1 manday = 1 orang-hari**, ±20 hari kerja/bulan. Mandays ≠ durasi kalender (ada paralelisasi).
2. **Reuse Odoo** menurunkan effort: `custom_approval_engine`, `custom_adapter_framework`,
   `queue_job`, PDP audit, reporting infra sudah ada.
3. **Kontrak integrasi** (JSON payload + peta topik) difinalkan di fase Requirement; tim
   SAP/Kafka/HC menyediakan/mengonsumsi kontrak tersebut.
4. **Konektor SAP/Kafka/HRIS siap sebelum SIT (±W13).** Keterlambatan menggeser SIT→Go-Live.
5. Master data dari SAP berkualitas memadai (COA, cost budget, supplier, approval matrix).
6. Lingkungan dev/staging/prod Odoo + Keycloak disediakan klien tepat waktu.
7. Kontingensi 15% untuk ketidakpastian normal (di luar risiko dependency eksternal).

---

## 4. Estimasi Mandays per Role × Fase

| Fase | PMO | BA | Dev | QA | Total |
|---|---:|---:|---:|---:|---:|
| 1. Requirement Gathering & Analysis | 8 | 22 | 3 | 4 | **37** |
| 2. Design (FSD/TSD, mockup, integration spec) | 3 | 8 | 10 | 6 | **27** |
| 3. Build / Development | 18 | 35 | 123 | 44 | **220** |
| 4. SIT (integrasi via kontrak) | 5 | 6 | 12 | 16 | **39** |
| 5. UAT (support + defect fix) | 5 | 12 | 12 | 8 | **37** |
| 6. Cutover & Go-Live | 4 | 5 | 8 | 3 | **20** |
| 7. Post Go-Live / Hypercare | 4 | 5 | 9 | 3 | **21** |
| **Subtotal** | **47** | **93** | **177** | **84** | **401** |
| Kontingensi 15% | 7 | 14 | 27 | 13 | **61** |
| **TOTAL** | **54** | **107** | **204** | **97** | **≈ 462** |

---

## 5. Detail Effort Fase Build per Modul (Dev / BA / QA)

| Workstream (Odoo) | Dev | BA | QA |
|---|---:|---:|---:|
| Foundation (SSO Odoo-side, base module, security, CI/CD) | 12 | 2 | 3 |
| Master data + sync upsert (Odoo-side) + cron | 14 | 6 | 4 |
| Cash Advance + Realization (+ approval Tax→Finance) | 14 | 4 | 5 |
| Reimbursement & Expenses | 9 | 3 | 4 |
| Vendor Invoice (PO/Non-PO Non-Trade) + Vendor Portal SSO | 18 | 4 | 6 |
| Perjalanan Dinas (read HRIS via kontrak + settlement) | 7 | 3 | 3 |
| Budget control + aturan PR > Rp 1jt | 8 | 3 | 3 |
| Integration Odoo-side (adapter + push job + webhook + sync log) | 16 | 4 | 6 |
| Reporting (login/transaction/sync log) + Dashboards | 12 | 3 | 4 |
| Configuration + Limitation master | 4 | 2 | 2 |
| Non-functional (PDP audit, security, perf, resilience) | 9 | 1 | 4 |
| **Subtotal Build** | **123** | **35** | **44** |

> Catatan: "Integration Odoo-side" **tidak** mencakup pembuatan konektor Kafka/SAP (di luar scope) —
> hanya adapter Odoo yang memanggil/menerima kontrak REST.

---

## 6. Timeline & Milestone (±24 minggu)

| Fase | Durasi | Minggu | Milestone |
|---|---|---|---|
| 1. Requirement Gathering & Analysis | 3 mgg | W1–W3 | FSD draft + **kontrak integrasi final** |
| 2. Design (FSD/TSD) | 2 mgg | W3–W5 | TSD & data model sign-off |
| 3. Build (sprint 2-mingguan) | 10 mgg | W5–W15 | Demo per sprint; feature complete |
| 4. SIT | 4 mgg | W13–W17 | *Gated:* konektor SAP/Kafka/HRIS ready; E2E pass |
| 5. UAT | 3 mgg | W17–W20 | UAT sign-off |
| 6. Cutover & Go-Live | 1 mgg | W20–W21 | **Go-Live** |
| 7. Post Go-Live / Hypercare | 3 mgg | W21–W24 | Stabilisasi & handover ke support |

```
W: 1  3  5        13   15  17  20 21    24
   |Req|Des|--Build-----|        |
              |----SIT----|
                      |--UAT--|
                              |Cut|
                                  |Hypercare|
```

---

## 7. Komposisi Tim (turunan dari mandays / ±24 minggu)

| Role | Mandays | FTE | Saran |
|---|---:|---:|---|
| PMO | 54 | ~0.45 | 1 PMO (part-time) |
| BA | 107 | ~0.9 | 2 BA di Req/Design, 1 BA di Build/late |
| Developer | 204 | ~1.7 | 2–3 dev (peak 3 saat Build; 1 fokus integrasi Odoo-side) |
| QA | 97 | ~0.8 | 1 QA (2 saat SIT/UAT) |

---

## 8. Dependensi & Risiko

| # | Risiko | Dampak | Mitigasi |
|---|---|---|---|
| 1 | Konektor SAP/Kafka/HRIS belum siap saat SIT | Geser SIT→Go-Live | Contract-first + stub/mock (sudah disiapkan); SIT gated milestone |
| 2 | Kualitas master data SAP (COA, budget, approval matrix) | Rework mapping | Data cleansing dini di fase Build |
| 3 | Attachment SAP Basis & approval status PO belum ada | Potensi change request | Tandai sebagai opsi/CR di awal |
| 4 | Ketersediaan user untuk UAT | UAT molor | Jadwalkan slot UAT sejak Design |
| 5 | Perubahan ruang lingkup kontrak integrasi | Effort tambah | Change control via PMO |

---

## 9. Deliverables (Odoo)
- 4 modul Odoo terinstal & teruji (unit test + SIT).
- Konfigurasi SSO Keycloak (sisi Odoo) + role mapping.
- Dokumentasi: FSD, TSD, kontrak integrasi (JSON + topik), runbook deploy, user guide.
- Laporan UAT & sign-off, rencana cutover, laporan hypercare.

---

## 10. Catatan
- **Head start**: scaffold awal (4 modul + referensi bridge) sudah dibuat dan tervalidasi statis
  (py_compile/XML/ACL) — menutup sebagian Foundation/Cash Advance/SSO; dianggap *de-risking*
  (belum dipotong dari angka di atas).
- Estimasi dapat disesuaikan bila tim diperbesar (durasi turun) atau scope opsional (mis. dashboard
  lanjutan, OCR receipt) ditambahkan.
