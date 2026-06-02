# Project Initiation Document (PID)
## Gentle Woman — Headless Commerce Storefront

**Document owner:** Delivery Team (Odoo Platform)
**Sponsor / Product Owner:** Ade Maryadi (Erajaya Active Lifestyle)
**Tenant:** `gentlewoman`
**Version:** 1.0 — Pilot baseline

---

## 1. Purpose

Establish the mandate, scope, governance and success criteria for delivering a
branded, headless e-commerce storefront for Gentle Woman on the existing Odoo
Platform, with Odoo as the system of record and a Next.js front-end as the
customer experience layer.

## 2. Background

Gentle Woman is a fashion brand introduced in Indonesia by Erajaya Active
Lifestyle. Standard Odoo eCommerce / template webshops do not deliver the
editorial brand experience required, while ad-hoc storefronts risk diverging
from real inventory, pricing and order data. A **headless** architecture
resolves this: full presentation freedom on the front-end, full operational
governance in Odoo.

## 3. Objectives

1. Launch a brand-controlled storefront backed by Odoo (catalog, stock, price,
   orders, customers, promotions, fulfilment).
2. Enable omnichannel: store locator, in-store stock, click-&-collect.
3. Provide growth levers: affiliate program, promotions, wishlist, newsletter.
4. Manage editorial content (non-catalog) inside Odoo — no separate CMS service.
5. Meet UU PDP data-protection obligations and a strong security baseline.

## 4. Scope

**In scope (Phase 1 — delivered)**
- Catalog browse (PLP/PDP), filtering, search, bilingual content (ID/EN).
- Cart, guest & registered checkout, saved addresses, order history.
- Store locator, in-store stock, click-&-collect fulfilment routing.
- Wishlist; affiliate program (links, tracking, commission, payouts, dashboard).
- Promotions (pricelist strike-through), "New" drops, tags.
- Editorial CMS in Odoo (hero, lookbook, sections, banner, footer, newsletter).
- Security hardening + encryption (transport, session, PII at rest).

**Phase 2 (gated)**
- Eraspace payment integration (blocked on vendor API documentation).
- Affiliate payout operations; loyalty/coupons.

**Phase 3 (decision)**
- AI personal shopper / stylist; virtual try-on / 3D for accessories.

**Out of scope (current)**
- Card data storage (PCI scope avoided — handled by the payment provider).
- A separate third-party headless CMS (intentionally replaced by Odoo content).

## 5. Deliverables

| # | Deliverable | Status |
|---|---|---|
| D1 | Headless storefront (Next.js) | Live (pilot) |
| D2 | Storefront API + content + affiliate modules (Odoo) | Live (pilot) |
| D3 | Editorial content managed in Odoo | Live |
| D4 | Security & encryption hardening | Live |
| D5 | Payment integration (Eraspace) | Blocked (vendor) |
| D6 | Documentation set (PID, BRD, FSD, TSD, Board brief) | This package |

## 6. Governance & Roles

| Role | Responsibility |
|---|---|
| Sponsor / Product Owner | Priorities, sign-off, unblock dependencies (payment, AI budget) |
| Delivery Team | Architecture, build, security, deployment, documentation |
| Brand / Marketing | Editorial content, campaigns, affiliate onboarding |
| Store Operations | Store data, stock accuracy, click-&-collect fulfilment |
| Compliance / DPO | UU PDP consent, data-retention policy, rotation procedures |

## 7. Milestones (indicative)

| Milestone | Outcome |
|---|---|
| M1 — Foundation pilot | Phase 1 features live on `gentlewoman` (achieved) |
| M2 — Payment unblocked | Eraspace API received & integrated; checkout fully transactional |
| M3 — Production launch | DNS/cert, content finalized, UAT sign-off, go-live |
| M4 — Growth | Affiliate onboarding, campaigns, optional AI shopper |

## 8. Success Criteria (KPIs)

- Functional: end-to-end order placed online (and via click-&-collect).
- Operational: zero stock/price divergence between site and Odoo.
- Performance: storefront pages serve under target latency; high availability.
- Security: passes the documented security checklist (see TSD §Security).
- Growth: affiliate-attributed orders measurable; newsletter capture active.

## 9. Constraints & Assumptions

- Single live tenant (`gentlewoman`); changes are tenant-scoped and must not
  affect other tenants on the shared platform.
- Encryption master keys are provided via environment/secret management.
- Payment go-live depends entirely on the external Eraspace API documentation.
- AI features depend on external services and an approved operating budget.

## 10. High-level Risks

See the Board Briefing §6 and BRD §Risks. Principal risk to launch is the
**external payment dependency**; principal ongoing risks are **data protection**
and **secret/key management**, both already mitigated in the pilot.
