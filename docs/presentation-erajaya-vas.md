# Erajaya Value-Added Services
## Odoo Hub — Centralized ERP Platform for Erajaya Group

**Audience:** Executive / Business Stakeholders  
**Owner:** Product Owner — Value-Added Services, Erajaya  
**Status:** Internal pitch deck (Mei 2026)

---

## Slide 1 — Executive Summary

**Odoo Hub** adalah platform terpusat untuk percepatan delivery ERP lintas vertikal Erajaya Group. Tiga pilar:

1. **Centralized Module Repository** — 1 sumber kebenaran modul, reusable lintas vertikal.
2. **Simplified Deployment** — provisioning tenant baru otomatis via orchestrator (~30 menit).
3. **Centralized Monitoring** — 1 control plane untuk seluruh tenant operasional.

Konsekuensinya: **mandays implementasi turun signifikan** karena modul standar sudah siap pakai.

| Metric | Value |
|---|---|
| Modul Siap Pakai | **82** |
| Modul Reusable Lintas Vertikal | **~70%** |
| Mandays Standar / Tenant | **~77** |
| SLA Target | **99.5%** |

---

## Slide 2 — Hub Platform Stack

```
┌─────────────────────────────────────────────────────────────┐
│  AI Layer                                                   │
│  ai-gateway (Claude / OpenAI / Ollama) · Ask-AI · NLQ ·     │
│  anomaly inbox · OCR receipt · churn prediction             │
├─────────────────────────────────────────────────────────────┤
│  Observability Plane                                        │
│  Prometheus · Grafana · Loki · Alertmanager · predictor     │
├─────────────────────────────────────────────────────────────┤
│  Multi-Tenant Runtime                                       │
│  Odoo 19 + 82 custom modules · DB-per-tenant · Caddy/TLS    │
├─────────────────────────────────────────────────────────────┤
│  Tenant Orchestrator                                        │
│  FastAPI: SSH bootstrap · Docker stack · DB · modules · mail│
├─────────────────────────────────────────────────────────────┤
│  Centralized Module Repository                              │
│  Single source of truth 82 modul · LGPL-3 · CI-tested       │
└─────────────────────────────────────────────────────────────┘
```

---

## Slide 3 — High-Level Architecture (Linux-based)

Stack berjalan di atas Linux host dengan Docker — open, portable, dan tanpa lock-in OS.

```
┌──────────────────────────────────────────────────────┐
│  Linux Host  (Ubuntu 22.04 LTS · bare-metal / VPS)   │
├──────────────────────────────────────────────────────┤
│  Docker Engine 24+  ·  Compose v2  ·  systemd        │
├──────────────────────────────────────────────────────┤
│  Container Network (bridge)                          │
│                                                      │
│  ┌────────┐   ┌────────┐   ┌────────┐                │
│  │ Caddy  │ → │  Odoo  │ ← │ AI GW  │                │
│  │ TLS LB │   │workers │   │FastAPI │                │
│  └───┬────┘   └───┬────┘   └───┬────┘                │
│      │            │            │                     │
│  ┌───▼────┐   ┌───▼────┐   ┌───▼────┐                │
│  │ Redis  │   │Postgres│   │ Ollama │                │
│  │ cache  │   │  15+   │   │ local  │                │
│  └────────┘   └────────┘   └────────┘                │
│                                                      │
│  ┌──────────┐ ┌─────────┐ ┌──────┐ ┌─────────────┐   │
│  │Prometheus│ │ Grafana │ │ Loki │ │Alertmanager │   │
│  └──────────┘ └─────────┘ └──────┘ └─────────────┘   │
├──────────────────────────────────────────────────────┤
│  Persistent Volumes  (filestore · DB · logs · backup)│
├──────────────────────────────────────────────────────┤
│  Kernel hardening: AppArmor · seccomp · namespaces   │
└──────────────────────────────────────────────────────┘
```

**Decisions kunci:**

- **OS:** Ubuntu 22.04 LTS — 5 tahun security update.
- **Runtime:** Docker 24+ + Compose v2, non-root user di tiap container.
- **Image hardening:** distroless / Alpine base, CIS-aligned.
- **Storage:** persistent volumes (filestore, DB, log, backup) bind-mount.
- **Network:** bridge internal; hanya Caddy expose port 80/443.
- **Firewall:** UFW / iptables — port 22 (SSH ops VPN), 80, 443 saja.
- **TLS:** Caddy ACME (Let's Encrypt) auto-renew.
- **Patch:** `unattended-upgrades` untuk security patches OS.
- **Backup:** `pg_dumpall` nightly + filestore rsync ke object storage.
- **Portable:** stack sama untuk on-prem, VPS, atau cloud (AWS/GCP/Azure).

---

## Slide 4 — Centralized Module Repository (Reuse Matrix)

Modul kunci dipakai ulang lintas 6 vertikal Erajaya — bukan develop ulang per tenant.

| Module | F&B | Active | Eraspace | Distrib | Service | Corp |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| custom_core | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_accounting_full | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_hr_payroll_id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_attendance | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_approval_engine | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_pdp_* (6 modul) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_coretax + bupot | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_helpdesk | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_whatsapp | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| custom_pos_id | ✓ | ✓ | ✓ | — | — | — |
| custom_ecommerce | ✓ | ✓ | ✓ | — | — | — |
| custom_wms_* (3 modul) | — | ✓ | ✓ | ✓ | ✓ | — |
| custom_field_service | — | — | — | — | ✓ | — |
| custom_subscription | — | — | — | — | — | ✓ |

**~70% modul shared · ~30% extension vertical-specific.** Modul baru → masuk repo sekali → tersedia untuk semua tenant.

---

## Slide 5 — Module Library — Capability Highlights

- **Finance & Tax (Indonesian-localized, ready)** — PSAK 5-digit CoA · Intercompany & consolidation · Fixed asset depreciation · PPh 21 TER · BPJS · SPT 1721 A1 · PPN DPP Nilai Lain · e-Faktur Coretax · Bupot Unifikasi.
- **Human Capital (Indonesian-localized, ready)** — Geofence attendance · Cuti UU Cipta Kerja · Performance appraisal 360 · Recruitment + job-board webhook · Expense OCR · Billable timesheet → payroll.
- **Sales · CRM · Commerce** — Predictive lead scoring · Drip campaigns · Midtrans/Xendit/DOKU · JNE/JNT/SiCepat/AnterAja · Subscription MRR · Rental BAST · WhatsApp QR ticket.
- **Service Operations** — Helpdesk SLA · Field Service dispatch · Repairs w/ warranty · Appointments · Livechat → AI reply · Frontdesk visitor.
- **Manufacturing & WMS** — MRP PLM (ECO + BoM) · Quality + CAPA · Maintenance MTBF/MTTR · WMS putaway/cycle-count/to-engine · Mobile barcode · Zebra HHT · IoT webhook.
- **Productivity & Cross-Cutting** — Studio-Lite · Dashboards KPI + AI NLQ · Spreadsheet · Documents · E-signature · Knowledge wiki · Generic approval engine.

---

## Slide 6 — Indonesian Localization Ready

Aturan akunting, perpajakan, ketenagakerjaan, dan data protection Indonesia — built-in, package siap pakai per tenant.

| Domain | Cakupan Localized |
|---|---|
| **Akunting (PSAK)** | CoA 5-digit aligned PSAK · Intercompany automation · Consolidation + eliminations · Fixed asset depreciation · Faktur Pengganti workflow |
| **Perpajakan (DJP)** | e-Faktur Coretax (NSFP 17 digit PER-11/PJ/2025) · Bupot PPh 21/23/26/Unifikasi · PPh 21 TER (PP 58/2023) · PPN DPP Nilai Lain (PMK 131/2024) · Sertel Fernet-encrypted · Pajakku ASPP H2H adapter |
| **HR & Ketenagakerjaan** | BPJS Kesehatan & Ketenagakerjaan (JHT/JKK/JKM/JP) · PTKP & THR · SPT 1721 A1 · Cuti UU Cipta Kerja · Payslip approval flow |
| **Data Protection (UU PDP)** | Klasifikasi data field-level · Consent management · DSAR endpoint · Audit log append-only hash-chained · PII masking · Retention auto-purge |

**Pendekatan adapter pattern:** ASP / regulasi berubah → swap implementasi tanpa ubah workflow tenant.

---

## Slide 7 — Simplified Deployment (Tenant Orchestrator)

Provisioning tenant baru otomatis — ~30 menit dari permintaan ke siap UAT.

**Pipeline 7 langkah:**

1. **SSH bootstrap** target VPS (Docker + Caddy install)
2. **Pull stack**: Odoo + Postgres + Redis + module repo
3. **Create database** tenant + apply addons path
4. **Install modul standar** (sesuai profile vertikal)
5. **Generate Caddy route** + TLS otomatis (ACME)
6. **Konfigurasi mail** (SMTP / IMAP) + integrasi (Pajakku, payment)
7. **Smoke test** + handover ke PO untuk UAT

Tidak butuh DevOps mandays manual — orchestrator yang eksekusi.

---

## Slide 8 — Centralized Monitoring

**Apa yang dimonitor:**

- Odoo runtime metrics per tenant (requests, latency, error rate)
- Database health (connections, slow query, replication lag)
- AI gateway cost & latency per tenant
- Pajakku ASPP circuit state (open / closed / half-open)
- Audit chain integrity (PDP hash-chain verifier nightly)
- Tenant resource usage (CPU, memory, disk, filestore size)
- Capacity forecast 7-hari via custom-predictor
- TLS expiry, backup status, scheduler health

**Manfaat operasional:**

- 1 dashboard Grafana untuk N tenant — bukan login per server
- Alert centralized via Alertmanager → ops on-call
- Proactive scaling — predictor rekomendasi upgrade hardware sebelum bottleneck
- MTTR turun — runbook + log + metric satu tempat
- Tenant SLA visible — laporan uptime per bulan otomatis
- Cost attribution per tenant (AI, storage, compute)
- Audit-ready: alert log + immutable trail

Stack: Prometheus (scrape 15s) · Grafana · Loki · Alertmanager · custom-predictor sidecar.

---

## Slide 9 — Security Posture

**Application & Data Isolation:**

- DB-per-tenant isolation — bukan schema-per-tenant
- RBAC: Odoo groups + record rules per modul
- Multi-tier approval w/ delegation, OOO, SLA escalation
- Append-only audit log + PostgreSQL trigger
- Tenant allow-list per request (HMAC-validated)
- Secrets via SOPS-encrypted di repo + Fernet for sertel

**Infrastructure & Pipeline:**

- CIS-hardened distroless containers, non-root
- AppArmor + seccomp profiles
- TLS termination + HSTS (Caddy / nginx)
- Pre-commit: gitleaks, ruff, bandit, hadolint
- CI: Semgrep (SAST) + pip-audit + Trivy + cosign signing
- Nightly `pg_dumpall` + DR runbook (drill executed Q2 2026)

---

## Slide 10 — AI Layer

**Infrastruktur:**

- `ai-gateway` (FastAPI sidecar) — multi-provider abstraction
- Provider switch via env: Claude / OpenAI / Ollama (local)
- HMAC-validated Odoo → gateway calls
- Prompt caching, per-tenant rate limit & quota
- `custom-predictor` — tabular ML, capacity forecasting 7-hari

**Fitur AI di Modul Bisnis:**

- Ask AI server-action di 9 model utama (invoice, payslip, picking)
- Anomaly Inbox — scan harian + severity + suggested action
- NLQ Chat — query natural language dengan PDP masking
- Document Auto-Classify · AI churn prediction · AI suggested reply
- AI OCR receipt · task breakdown · predictive lead scoring · spreadsheet helpers

---

## Slide 10b — AI Provider Tradeoffs (Anthropic vs Local Ollama)

Gateway mendukung **provider switch** per-environment dan per-tenant.
Pilihan ini memengaruhi biaya, latensi, dan data residency — bukan
hanya kualitas jawaban.

| Aspek                | **Anthropic Claude** (default) | **Local Ollama** (self-hosted) |
| -------------------- | ------------------------------- | ------------------------------- |
| Kualitas reasoning   | Tinggi (kelas Sonnet/Opus)      | Sedang (model 3B–8B)            |
| Latensi tipikal      | 1–4 detik / request             | 3–15 detik di VPS CPU-only      |
| Biaya                | Per-token (variable, scale-up)  | Flat — hanya RAM/CPU VPS        |
| Data residency       | Keluar ke API Anthropic         | 100% on-prem / on-VPS           |
| Throughput           | Horizontal, multi-tenant aman   | Terbatas 1 VPS, antri sequential|
| Offline / air-gapped | Tidak                           | Ya                              |
| Setup ops            | API key + quota                 | Pull model 2–8 GB + 12 GB RAM   |
| Update model         | Otomatis (Anthropic-managed)    | Manual `ollama pull`            |

**Rekomendasi penggunaan:**

- **Produksi multi-tenant, fitur reasoning berat** (NLQ Chat, anomaly
  explain, doc auto-classify) → **Anthropic**.
- **Demo, PoC, tenant dengan klausul data-residency ketat** (mis. data
  HRIS sensitif, dokumen legal) → **Ollama**.
- **Hybrid**: gateway default Anthropic, lalu override per-tenant ke
  Ollama via *Settings → AI Intelligence → Provider Override*.

**Dampak yang harus user pahami:**

- Switch ke Ollama → jawaban lebih pendek, kadang kurang akurat untuk
  prompt panjang/multi-step. Toleransi error harus lebih tinggi.
- Switch ke Ollama → SLA latensi UI (Ask AI) bisa naik 3–4× di VPS
  tanpa GPU. Cron job (Anomaly Inbox) tidak terasa, UI realtime terasa.
- Switch ke Anthropic → wajib monitor token budget; quota per-tenant
  sudah ada di gateway, alert di Grafana board "AI Spend".

Banner notifikasi tradeoff ini juga muncul **otomatis di Odoo Settings
→ Custom Platform → AI Intelligence** sehingga PIC tenant sadar
konsekuensi saat ubah provider.

Deploy lokal: `docs/ollama-local-deploy.md`.

---

## Slide 11 — Business Value — Implementation Mandays per Tenant

Estimasi standar onboarding 1 vertikal baru di Odoo Hub dengan semua modul standar siap pakai. Angka dalam tanda kurung = mandays **opsional** (hanya jika ada custom development).

| Implementation Phase | ITBP | PO | DevOps | Developer (opt) |
|---|---:|---:|---:|---:|
| Requirement gathering / BRD | 5 | 8 | — | — |
| Tenant provisioning (orchestrator) | — | 1 | 2 | — |
| Module activation (standard) | 3 | 5 | 2 | — |
| Master data setup (CoA, partner, employee) | 5 | 3 | — | — |
| Configuration (RBAC, approval, workflow) | 3 | 5 | 1 | — |
| Integration setup (Pajakku, payment, WA) | 2 | 2 | 3 | (2) |
| Custom module development | — | (3) | — | (15) |
| UAT + bug-fix | 5 | 5 | 1 | (5) |
| Training | 3 | 5 | — | — |
| Go-live + hypercare | 3 | 3 | 2 | — |
| **Subtotal — tanpa custom dev** | **29** | **37** | **11** | **0** |
| **Subtotal — dengan custom dev** | **29** | **40** | **11** | **22** |

**Highlight:**

- Standar (no dev): **~77 mandays / tenant** lintas 3 role.
- Dengan 1 custom module: **~102 mandays / tenant**.
- Baseline implementasi Odoo tradisional (tanpa hub, tanpa repo, manual deploy): **~200–300 mandays**.
- **Saving 60–70%** per onboarding setelah library modul ready.

---

## Slide 12 — VAS Productization (5 Product Lines)

| VAS Product | Modul Penopang | Target Market |
|---|---|---|
| ERP-as-a-Service Multi-Tenant | Hub stack lengkap + orchestrator | Internal tenants & afiliasi Erajaya |
| Localized Compliance Bundle | `custom_coretax*` + Pajakku + `custom_pdp_*` + `custom_hr_payroll_id` | UMKM ekosistem Erajaya (Eraspace partners, F&B franchisee) |
| AI Operations Layer | `ai-gateway` + `custom_ai_features` + predictor | Bundled tiap tenant; advanced tier opt-in |
| HHT / Field Ops Bridge | `custom_hht_bridge` (Zebra PWA) + `field_service` | Service Center, distribution, warehouse |
| Vertical Template Accelerator | Repo modul + onboarding journey | Vertikal baru di dalam Erajaya Group |

---

## Slide 13 — Roadmap

**Q2 2026 — DONE / IN PROGRESS**
- 82 modul base shipping
- Multi-tenant orchestrator
- Pajakku ASPP adapter
- Hub-Portal UI (Vite+React)
- Production drill #1 executed

**Q3 2026**
- Onboard 3 internal vertical (F&B, Service Center, Corp Svcs)
- Centralized monitoring dashboard rollout
- HHT rollout untuk service vertical
- AI cost optimization (cache hit target 60%)

**Q4 2026**
- Onboard tenant 4–10 (target Y1)
- Module reuse audit + dedup
- ESG report otomatis (POJK 51/2017)
- Marketplace add-on (3rd-party vertical modules)

**2027**
- Tenant 11–25 (post-ROI threshold)
- Open partner program (ASPP, integrator)
- Localized Compliance Bundle GTM eksternal

---

## Slide 14 — Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Odoo 19 upstream upgrade breaks customs | `custom_studio_lite` declarative, modules pinned `19.0.x.y`, CI per release |
| Pajakku API / Coretax submission gagal | Circuit breaker + manual fallback Coretax portal + ops alert |
| Tenant data leakage | DB-per-tenant + HMAC + tenant allow-list di ai-gateway |
| AI cost explosion | Per-tenant quota + prompt cache + local Ollama fallback |
| Mandays meleset karena scope creep | BRD freeze sebelum provisioning · change request via approval engine · re-baseline per onboarding |

---

## Slide 15 — Call to Action

1. **Endorsement** — Odoo Hub sebagai backbone delivery ERP Erajaya Group.
2. **Pilot Funding** — 3 vertikal pertama (F&B, Service Center, Corporate Services) — Q3 2026.
3. **Mandays Baseline Calibration** — lock estimasi mandays per vertikal selama 2 onboarding pertama.
4. **Hiring Runway** — 2 senior backend, 1 SRE, 1 PO untuk scale Y1 → Y2.
5. **GTM Eksternal** — Localized Compliance Bundle sebagai produk eksternal Q4 2026.

---

## Slide 16 — Terima Kasih

**Diskusi & Q&A**

Product Owner — Value-Added Services · Erajaya · Mei 2026

---

## Appendix A — Tech Stack Reference

| Component | Tech |
|---|---|
| ERP Core | Odoo 19 CE (LGPL-3) |
| Backend custom | Python 3.11, Odoo ORM |
| AI Gateway | FastAPI, async httpx |
| Hub-Portal | Vite + React 18 + TypeScript |
| Tenant Orchestrator | FastAPI + Paramiko (SSH bootstrap) |
| DB | PostgreSQL 15+ |
| Cache / Queue | Redis |
| Reverse proxy | Caddy (TLS-ACME) / nginx (prod) |
| Container | Docker Compose |
| Observability | Prometheus, Grafana, Loki, Promtail, Alertmanager |
| Local LLM | Ollama |
| Secrets | SOPS |
| CI/CD | GitHub Actions (Semgrep, Trivy, pip-audit, cosign) |

## Appendix B — Repository Layout

```
addons/
  core/           — 5 modules (custom_core, ai_bridge, adapter_framework, bast, hht_bridge)
  ee_gap/         — 60 modules (CE→EE gap fulfillment)
  compliance/     — 9 modules (PDP × 6, Coretax × 3, PPh × 1 — overlap by category)
  operations/     — 3 modules (ops_monitor, dev_cycle, brd_analyzer)
  verticals/      — 5 modules (super_admin, tenant_infra, hub_console, onboarding, _template)
services/         — baileys (WhatsApp), [future: more sidecars]
ai-gateway/       — FastAPI app
tenant-orchestrator/ — FastAPI + bootstrap_templates
hub-portal/       — Vite+React control plane UI
custom-predictor/ — ML forecasting sidecar
caddy/, nginx/    — reverse proxies
observability/    — Prometheus, Grafana, Loki configs
security/         — AppArmor, seccomp, policies
docs/             — architecture, compliance, runbooks, deploy checklists
tools/            — build_presentation.py (single-source PPTX+PDF builder)
```

---

*End of deck — Versi 2.0 · Mei 2026 · Internal Erajaya VAS*
