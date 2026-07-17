# PROJECT CHARTER
## Finance Portal on Odoo (System of Engagement over SAP)

---

### Document Control

| | |
|---|---|
| **Project Name** | Finance Portal on Odoo |
| **Document** | Project Charter |
| **Version** | 1.0 |
| **Date** | 2026-06-23 |
| **Prepared by** | Delivery Team (Custom Platform) |
| **Status** | Draft for Approval |
| **Scope of effort** | **Odoo only** — effort SAP & HC/HRIS **dikeluarkan** |

**Revision History**

| Ver | Tanggal | Penulis | Catatan |
|---|---|---|---|
| 1.0 | 2026-06-23 | Delivery Team | Initial charter |

---

## 1. Latar Belakang & Justifikasi

Proses keuangan (Cash Advance, Reimbursement & Expenses, Vendor Invoice Non-Trade,
Perjalanan Dinas) saat ini belum memiliki portal pengajuan terpadu di sisi pengguna,
sementara **SAP S/4HANA** tetap menjadi *system of record* (posting GL, MIRO, pembayaran,
master data). Dibutuhkan **Finance Portal** sebagai *system of engagement* yang menyediakan
form pengajuan, approval **Tax → Finance**, validasi budget/PR, lalu mendorong dokumen yang
disetujui ke SAP dan menampilkan kembali status pembayaran.

Solusi dibangun di atas **Odoo 19** memanfaatkan komponen platform yang sudah ada
(approval engine, adapter framework, queue/async, audit PDP, reporting) sehingga lebih cepat
dan hemat dibanding membangun aplikasi bespoke. Integrasi ke SAP/HRIS dilakukan melalui
**Kafka + REST** dengan pendekatan *contract-first*.

---

## 2. Tujuan Proyek (Project Objectives)

1. Menyediakan portal terpadu untuk Cash Advance (+Realization), Reimbursement & Expenses,
   Vendor Invoice (PO/Non-PO Non-Trade), dan settlement Perjalanan Dinas.
2. Menjalankan approval dua tahap **Tax Review → Finance Review** dengan matrix konfigurable.
3. Menerapkan validasi **budget per divisi** dan aturan **PR wajib untuk pengajuan > Rp 1.000.000**.
4. Mengintegrasikan portal dengan SAP (push GL/journal/MIRO, terima payment plan & status) dan
   HRIS (read travel) melalui kontrak integrasi yang disepakati.
5. Menyediakan **SSO** (Keycloak) untuk login karyawan & vendor.
6. **Odoo tidak melakukan posting GL** — pembukuan tetap di SAP.

## 3. Kriteria Sukses (Success Criteria / KPI)

| KPI | Target |
|---|---|
| Modul Odoo terinstal & lulus uji (unit + SIT) | 100% modul in-scope |
| End-to-end happy path (submit → Tax → Finance → push SAP → status mirror) | Lulus di SIT & UAT |
| UAT sign-off oleh user Finance/Tax | Tercapai sebelum Go-Live |
| Login SSO (karyawan & vendor) + role mapping benar | 100% skenario |
| Defect Sev-1/Sev-2 saat Go-Live | 0 open |
| Go-Live sesuai timeline | ±W21 |

---

## 4. Ruang Lingkup (Scope)

### 4.1 In-Scope (Odoo)
- Modul: `custom_finance_portal`, `custom_finance_budget`,
  `custom_finance_portal_sap` (adapter sisi Odoo), `custom_finance_portal_sso`.
- Dokumen + workflow approval Tax→Finance, budget control, aturan PR > Rp 1jt.
- Adapter Odoo ke kontrak REST integrasi, upsert master idempoten, webhook status (HMAC),
  push job async, sync log + menu.
- Vendor Portal (login SSO, submit invoice, tracking), SSO Keycloak (config sisi Odoo).
- Reporting (login/transaction/sync log), dashboard, konfigurasi, security/PDP audit, hardening.

### 4.2 Out-of-Scope (DIKELUARKAN dari proyek ini)

| Area | Penjelasan | Pemilik |
|---|---|---|
| **SAP development** | ABAP/CPI/OData, posting GL/journal/MIRO, expose PR/PO/GR non-trade + nilai/status, payment list, attachment SAP Basis, approval status PO | Tim SAP klien |
| **HC / HRIS development** | Konektor HRIS→Kafka, perubahan modul travel, ekstraksi employee master | Tim HC/HRIS klien |
| **Kafka & konektor** | Cluster Kafka, topik, konektor SAP↔Kafka & Kafka↔Portal | Tim integrasi/Kafka klien |
| **Infrastruktur non-Odoo** | Provisioning Keycloak server, jaringan, sertifikat | Tim infra klien |

> Sisi Odoo **build terhadap kontrak** (JSON + topik) sehingga dapat dikerjakan paralel.

---

## 5. Deliverables Utama
- 4 modul Odoo terinstal & teruji.
- Konfigurasi SSO Keycloak (sisi Odoo) + role mapping.
- Dokumentasi: FSD, TSD, kontrak integrasi (JSON + topik), runbook deploy, user guide.
- Laporan UAT & sign-off, rencana cutover, laporan hypercare.

---

## 6. Milestone & Timeline (±24 minggu / ±6 bulan)

| # | Milestone | Target Minggu |
|---|---|---|
| M1 | Requirement & kontrak integrasi final | W3 |
| M2 | Design (FSD/TSD) sign-off | W5 |
| M3 | Feature complete (Build) | W15 |
| M4 | SIT pass *(gated: konektor SAP/Kafka/HRIS ready)* | W17 |
| M5 | UAT sign-off | W20 |
| M6 | **Go-Live** | W21 |
| M7 | Hypercare selesai & handover | W24 |

```
W: 1  3  5         13  15  17  20 21    24
   |Req|Des|---Build----|        |
               |---SIT----|
                       |--UAT--|
                               |Cut|
                                   |Hypercare|
```

---

## 7. Estimasi Effort & Resource (Mandays — Odoo Only)

| Fase | PMO | BA | Dev | QA | Total |
|---|---:|---:|---:|---:|---:|
| 1. Requirement Gathering & Analysis | 8 | 22 | 3 | 4 | 37 |
| 2. Design (FSD/TSD) | 3 | 8 | 10 | 6 | 27 |
| 3. Build / Development | 18 | 35 | 123 | 44 | 220 |
| 4. SIT | 5 | 6 | 12 | 16 | 39 |
| 5. UAT | 5 | 12 | 12 | 8 | 37 |
| 6. Cutover & Go-Live | 4 | 5 | 8 | 3 | 20 |
| 7. Post Go-Live / Hypercare | 4 | 5 | 9 | 3 | 21 |
| **Subtotal** | **47** | **93** | **177** | **84** | **401** |
| Kontingensi 15% | 7 | 14 | 27 | 13 | 61 |
| **TOTAL** | **54** | **107** | **204** | **97** | **≈462** |

**Komposisi tim:** 1 PMO (part-time), 1–2 BA, 2–3 Developer, 1–2 QA.
Detail per modul: lihat `Project-Estimation-Odoo-Finance-Portal.md`.

---

## 8. Organisasi Proyek & Governance

### 8.1 Stakeholder & Peran

| Peran | Tanggung Jawab |
|---|---|
| **Project Sponsor** (klien) | Mandat, keputusan strategis, sign-off budget |
| **Steering Committee** | Arahan, eskalasi, keputusan scope mayor |
| **PMO** | Perencanaan, monitoring, reporting, change control, koordinasi lintas tim (SAP/Kafka/HC) |
| **Business Analyst (BA)** | Requirement, FSD, mapping master/approval, fasilitasi UAT |
| **Developer** | Pengembangan modul Odoo + adapter integrasi sisi Odoo |
| **QA** | Test design, SIT, regression, otomasi |
| **Product Owner** (klien) | Prioritas backlog, validasi fungsional, UAT |
| **Tim SAP/Kafka/HC** (klien) | Konektor & perubahan di SAP/Kafka/HRIS (di luar scope ini) |

### 8.2 RACI (ringkas)

| Aktivitas | PMO | BA | Dev | QA | Sponsor/PO |
|---|:--:|:--:|:--:|:--:|:--:|
| Requirement & FSD | A | R | C | C | C/A |
| Design/TSD | C | C | R | C | A |
| Build modul Odoo | A | C | R | C | I |
| Kontrak integrasi | A | R | C | I | C |
| SIT | A | C | C | R | I |
| UAT | C | A | C | C | R |
| Go-Live | A | C | R | C | A |

*(R=Responsible, A=Accountable, C=Consulted, I=Informed)*

### 8.3 Cadence & Change Control
- **Sprint** 2-mingguan; **demo** akhir sprint; **stand-up** harian tim delivery.
- **Steering Committee** bulanan; **status report** mingguan oleh PMO.
- **Change control**: setiap perubahan scope/kontrak via formulir CR, disetujui PMO + Sponsor.
- **Eskalasi**: blocker > 2 hari kerja dieskalasi ke Steering.

---

## 9. Asumsi
1. 1 manday = 1 orang-hari (±20 hari/bulan); mandays ≠ durasi kalender.
2. Reuse komponen Odoo (approval engine, adapter framework, queue_job, PDP audit, reporting).
3. Kontrak integrasi (JSON + topik) final di fase Requirement; tim SAP/Kafka/HC menyediakannya.
4. **Konektor SAP/Kafka/HRIS siap sebelum SIT (±W13).**
5. Lingkungan dev/staging/prod Odoo + Keycloak disediakan klien tepat waktu.
6. Master data SAP berkualitas memadai.

## 10. Batasan (Constraints)
- Odoo **tidak** memposting GL — pembukuan tetap di SAP.
- Integrasi hanya via kontrak REST/Kafka yang disepakati (tidak akses langsung DB SAP).
- Kepatuhan **UU PDP** (audit trail, masking data sensitif: NIK, rekening).
- Timeline bergantung pada kesiapan dependency eksternal.

## 11. Dependensi
- Konektor & endpoint SAP/Kafka/HRIS (eksternal).
- Keycloak realm/client + role mapper (infra klien).
- Akses & approval data master dari SAP/HRIS.

---

## 12. Risiko Tingkat Tinggi (RAID)

| # | Risiko | Dampak | Mitigasi |
|---|---|---|---|
| 1 | Konektor SAP/Kafka/HRIS belum siap saat SIT | Geser SIT→Go-Live | Contract-first + stub/mock; SIT gated milestone |
| 2 | Kualitas master data SAP | Rework mapping | Cleansing dini di Build |
| 3 | Attachment SAP Basis & approval status PO belum ada | Potensi CR | Tandai sebagai opsi/CR di awal |
| 4 | Ketersediaan user UAT | UAT molor | Jadwalkan slot UAT sejak Design |
| 5 | Perubahan kontrak integrasi | Effort bertambah | Change control via PMO |

---

## 13. Kriteria Penerimaan (Acceptance)
- Seluruh deliverable in-scope diterima & sign-off.
- KPI Bab 3 tercapai; 0 defect Sev-1/Sev-2 terbuka saat Go-Live.
- UAT sign-off oleh Product Owner & user Finance/Tax.
- Handover dokumentasi & runbook ke tim support.

---

## 14. Persetujuan (Sign-off)

| Peran | Nama | Tanda Tangan | Tanggal |
|---|---|---|---|
| Project Sponsor | | | |
| Steering Committee | | | |
| Project Manager / PMO | | | |
| Product Owner (klien) | | | |
| Delivery Lead | | | |

---

*Lampiran: detail estimasi per modul → `Project-Estimation-Odoo-Finance-Portal.md`;
fit-gap & arsitektur → `README.md`; kontrak integrasi → `services/finance-sap-bridge/app/contracts.md`.*
