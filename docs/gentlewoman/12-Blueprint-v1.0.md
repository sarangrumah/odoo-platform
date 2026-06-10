# Solution Blueprint
## GentleWoman — Headless Commerce Storefront × Odoo 19

**Erajaya — Value-Added Services**
*Architecture & Integration Blueprint*

---

### Document Control / Kendali Dokumen

| Item | Detail |
|---|---|
| Document Title | Solution Blueprint — GentleWoman Headless Commerce |
| Document ID | GW-BP-001 |
| Version | 1.0 |
| Status | Final for Approval |
| Classification | Confidential — Internal |
| Date | Juni 2026 |
| Author / Owner | Product Owner — Value-Added Services (Erajaya) |
| Audience | Architecture, Engineering, Security, Delivery Leadership |
| Related Documents | TSD (GW-TSD-001), FSD (GW-FSD-001), Business Presentation (GW-PRES-001) |

### Revision History / Riwayat Revisi

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | Juni 2026 | Product Owner — VAS | Initial release / Rilis awal |

### Approval / Lembar Pengesahan

| Role | Name | Signature | Date |
|---|---|---|---|
| Prepared by — Product Owner, Value-Added Services | ______________________ | ______________ | __________ |
| Reviewed by — IT Business Analyst / Technical Lead | ______________________ | ______________ | __________ |
| Approved by — Head of Value-Added Services / IT | ______________________ | ______________ | __________ |

> **Catatan bahasa / Language note.** Bilingual: Bahasa Indonesia + English technical terms.

---

# 1. Konteks Eksekutif / Executive Context

**ID.** GentleWoman adalah inisiatif *headless commerce* untuk fashion: storefront
Next.js memberi kendali penuh atas pengalaman brand (editorial, 3D, AI), sementara Odoo 19
menjadi sumber kebenaran tunggal untuk katalog, harga, stok, order, pelanggan, promosi,
afiliasi, dan konten. Pendekatan ini memisahkan *presentasi* (frontend) dari *proses
bisnis* (backend) sehingga keduanya berevolusi independen tanpa mengorbankan integritas
data.

**EN.** GentleWoman is a *headless commerce* initiative for fashion: the Next.js storefront
owns the brand experience (editorial, 3D, AI) while Odoo 19 is the single source of truth
for catalog, price, stock, orders, customers, promotions, affiliate, and content. This
decouples *presentation* (frontend) from *business processes* (backend), letting each
evolve independently without sacrificing data integrity.

# 2. Solution Blueprint (Logical)

```
┌──────────────────────────────────────────────────────────────────┐
│  EXPERIENCE LAYER — Storefront (Next.js 15)                        │
│  Editorial UI · 3D PDP · AI Shopper · i18n ID/EN · SEO/OG          │
├──────────────────────────────────────────────────────────────────┤
│  INTEGRATION LAYER — BFF (Next.js route handlers)                  │
│  /api/store · /api/img · /api/shopper · /api/docs · /api/affiliate │
│  inject auth + tenant · seal/refresh token · rate-limit            │
├───────────────┬──────────────────────────────────────────────────┤
│  TLS sidecar  │  (storefront-tls, cert-pinned)                     │
├───────────────┴──────────────────────────────────────────────────┤
│  COMMERCE LAYER — Odoo 19 CE (System of Record)                    │
│  custom_storefront_api · custom_affiliate · custom_ecommerce       │
│  custom_payment_id · custom_core · custom_pdp_* · website_sale     │
├──────────────────────────────────────────────────────────────────┤
│  AI LAYER — ai-gateway (FastAPI, multi-provider)                   │
│  Claude / Ollama · retrieval · HMAC · rate-limit · prompt cache    │
├──────────────────────────────────────────────────────────────────┤
│  DATA LAYER — PostgreSQL (db-per-tenant: gentlewoman) · Redis      │
└──────────────────────────────────────────────────────────────────┘
```

# 3. Component Blueprint

| Component | Peran / Role |
|---|---|
| Storefront (Next.js) | UI + Backend-for-Frontend; pemilik presentasi |
| BFF route handlers | Batas keamanan; proxy ke Odoo & ai-gateway; auth/tenant injection |
| storefront-tls | TLS sidecar cert-pinned untuk hop internal BFF↔Odoo |
| `custom_storefront_api` | API headless 3-lapis (public/JWT/HMAC), cart/checkout, content, store locator |
| `custom_affiliate` | Program afiliasi: link, klik, konversi, payout, atribusi |
| `custom_core` | HMAC secure-endpoint, Fernet field encryption |
| `custom_ecommerce` / `custom_payment_id` | Kurir & ongkir; adapter payment (Eraspace stub) |
| `custom_pdp_*` | Klasifikasi data, consent, audit, masking, retention (UU PDP) |
| ai-gateway | Multi-provider AI (Claude/Ollama), retrieval shopper |
| PostgreSQL / Redis | Persistensi per-tenant; cache/rate-limit |

# 4. Integration Blueprint

**ID.** Inti integrasi adalah BFF: browser tidak pernah memegang secret atau menyentuh
Odoo langsung. Tiga lapis otentikasi dipakai sesuai sensitivitas.

| Layer | Mechanism | Scope |
|---|---|---|
| Public | `auth=public` + CORS | Katalog, PDP, tags, stores, content, shipping quote (read-only) |
| Customer | JWT (HS256) bearer, sealed HttpOnly cookie | Cart, order, address, wishlist (partner-scoped) |
| Admin | HMAC-SHA256 (`X-Signature`/`X-Timestamp`) | Webhook server-to-server (health, sync, status) |

## 4.1 Sequence — Browse (Public)

```
Browser            BFF (/api/store)          Odoo (public_api)
  │  GET PLP            │                          │
  │───────────────────►│  + X-Odoo-Database        │
  │                    │─────────────────────────►│  serialize products
  │                    │                          │  (price/stock/tags/i18n)
  │                    │◄─────────────────────────│  JSON + price_bounds
  │◄───────────────────│                          │
```

## 4.2 Sequence — Login & Token

```
Browser            BFF                       Odoo (auth_jwt)
  │ POST /auth/login   │                          │
  │───────────────────►│─────────────────────────►│ verify, mint access(900s)+refresh
  │                    │◄─────────────────────────│ {access, refresh, customer}
  │                    │ seal AES-256-GCM →        │
  │                    │ cookies gw_at / gw_rt     │
  │◄───────────────────│ return {customer} only    │
```

## 4.3 Sequence — Add to Cart (JWT)

```
Browser            BFF                       Odoo (customer_api)
  │ POST /cart/items   │ open(gw_at) → Bearer      │
  │───────────────────►│─────────────────────────►│ jwt_partner_id from email claim
  │                    │                          │ _cart_add → draft sale.order
  │                    │                          │ pricelist + tax (native)
  │                    │◄─────────────────────────│ serialized cart
  │◄───────────────────│ (refresh on 401, retry)   │
```

## 4.4 Sequence — Checkout

```
Browser            BFF                       Odoo
  │ POST /checkout     │                          │
  │───────────────────►│─────────────────────────►│ set address (IDOR-guarded)
  │                    │                          │ carrier XOR pickup
  │                    │                          │ sale.order.action_confirm
  │                    │◄─────────────────────────│ confirmed order
  │ POST /checkout/<id>/pay ──────────────────────►│ payment.transaction (stub adapter)
```

## 4.5 Sequence — AI Personal Shopper

```
Browser         BFF (/api/shopper)     ai-gateway (/v1/shopper)     Odoo
  │ message         │ HMAC sign            │                          │
  │────────────────►│─────────────────────►│ 1 EXTRACT intent          │
  │                 │                     │ 2 RETRIEVE ───────────────►│ products
  │                 │                     │ 3 SYNTHESIZE              │
  │                 │                     │ 4 GUARD (real only)       │
  │◄────────────────│◄────────────────────│ reply + product cards     │
```

## 4.6 Sequence — Affiliate Attribution

```
Visitor klik link ?aff=CODE → cookie (consent-gated) → checkout membawa code
   → Odoo set sale.order.custom_affiliate_id → on confirm: conversion + komisi (pending)
   → Affiliate dashboard (JWT): klik, konversi, earnings
```

# 5. Data Blueprint — Ownership

**ID.** Odoo adalah pemilik data otoritatif. Storefront tidak menyimpan salinan data bisnis
selain state UI sementara.

| Entity | Owner | Catatan |
|---|---|---|
| Product, variant, tag, category | Odoo | `product.*` native + ekstensi `custom_*` |
| Price & promo | Odoo | pricelist; `compare_at`/`discount_pct` dihitung saat serialize |
| Stock & in-store availability | Odoo | `qty_available`; per-warehouse `location`-scoped |
| Cart & order | Odoo | draft → confirmed `sale.order` |
| Customer & address | Odoo | `res.partner`; PII at-rest Fernet |
| Affiliate | Odoo | `custom.affiliate*` |
| Editorial content & newsletter | Odoo | `custom.storefront.content/subscriber` |
| UI state (cart badge, locale) | Storefront | sementara (Zustand) |
| Session token | Storefront cookie | JWT sealed AES-256-GCM (HttpOnly) |

# 6. Security Blueprint (Defense-in-Depth)

```
[ Transport ]  HTTPS (Caddy) + internal TLS sidecar (cert-pinned)
[ Session   ]  HttpOnly cookie + AES-256-GCM sealed + transparent refresh + hashed refresh
[ App       ]  strict CSP · DOMPurify · anti-SSRF image proxy · rate-limit + body cap · anti-IDOR
[ Data      ]  PII Fernet at-rest · ORM-only (no raw SQL) · audit (custom_pdp_audit)
[ Privacy   ]  UU PDP consent capture · retention · DSAR/masking (custom_pdp_*)
[ Tenancy   ]  DB-per-tenant · X-Odoo-Database · HMAC tenant allow-list
[ Secrets   ]  externalized env/secret config · rotation procedures
```

# 7. Deployment Blueprint

```
┌──────────── Linux Host (Docker Engine + Compose) ───────────┐
│  Caddy (TLS LB)                                              │
│     ├─► storefront (Next.js, read-only FS, non-root)        │
│     │        └─► storefront-tls ─► odoo:8069                │
│     ├─► odoo (workers)                                       │
│     ├─► ai-gateway (FastAPI)                                 │
│     └─► nginx (shared)                                       │
│  postgres (db-per-tenant: gentlewoman)   redis (cache/RL)    │
│  Persistent volumes: filestore · DB · logs · backup         │
└─────────────────────────────────────────────────────────────┘
```

- **Isolasi tenant.** Perubahan storefront ter-scope ke `gentlewoman`; tenant lain tidak
  terpengaruh.
- **Deploy.** Storefront = rebuild image + recreate; modul Odoo = `-u <module> -d gentlewoman`.

# 8. AI Blueprint

```
ai-gateway (FastAPI)
  ├─ provider abstraction: Claude (Haiku/Sonnet, prompt cache) | Ollama (qwen2.5 / llama3.2)
  ├─ /v1/shopper: EXTRACT → RETRIEVE(Odoo) → SYNTHESIZE → GUARD
  ├─ HMAC-validated calls · per-IP rate-limit · Redis cache
  └─ privacy: consent-gated visitor profile, limited retention
```

# 9. Environment & Infrastructure

- **OS/Runtime.** Linux (Docker 24+ / Compose v2); container non-root; image hardened.
- **Network.** Bridge internal; hanya Caddy expose 80/443; TLS ACME auto-renew.
- **Observability.** Prometheus/Grafana/Loki; health check storefront & Odoo.
- **Backup.** pg_dump per-tenant + filestore; restore terdokumentasi.

# 10. Non-Functional & SLA

| Aspek | Target |
|---|---|
| Availability | 99.5% (mengikuti SLA platform) |
| Security posture | Defense-in-depth (§6) terpenuhi |
| Privacy | UU PDP compliant |
| Scalability | Storefront stateless (scale-out); rate-limit → Redis saat multi-instance |
| i18n | ID & EN penuh |

# 11. Roadmap / Phasing

| Fase | Cakupan |
|---|---|
| Fase 1 (Live Pilot) | Catalog/PLP/PDP, 3D PDP, AI Shopper MVP, Cart/Checkout/Wishlist, Store Locator + Click&Collect, Affiliate, i18n, Promo, Security/PDP |
| Fase 2 | CMS lanjutan, share-to-social lengkap, AI Admin (auto-deskripsi/tagging) |
| Fase 3 | Avatar / Virtual Try-On (2D→3D/AR), integrasi payment Eraspace (saat API tersedia) |

# Appendix — Glossary

| Term | Arti |
|---|---|
| BFF | Backend-for-Frontend (route handler Next.js sisi server) |
| PLP / PDP | Product List Page / Product Detail Page |
| HMAC | Hash-based Message Authentication Code (integritas pesan server-to-server) |
| JWT | JSON Web Token (otentikasi customer) |
| IDOR | Insecure Direct Object Reference (dicegah oleh ownership check) |
| SSRF | Server-Side Request Forgery (dicegah oleh image proxy terkunci) |
| UU PDP | Undang-Undang Pelindungan Data Pribadi (UU 27/2022) |
| SoR | System of Record (Odoo sebagai sumber kebenaran) |

---

*GW-BP-001 · v1.0 · Confidential — Internal · Erajaya Value-Added Services · Juni 2026*
