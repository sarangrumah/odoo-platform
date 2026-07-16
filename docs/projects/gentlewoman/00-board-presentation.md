# Gentle Woman — Headless Commerce Initiative
## Board / Director Briefing

**Prepared for:** Board of Directors
**Initiative owner:** Erajaya Active Lifestyle — Product Owner: Ade Maryadi
**Brand:** Gentle Woman (Indonesia)
**Platform:** Odoo Platform (multi-tenant) + Next.js headless storefront
**Status:** Working pilot live on tenant `gentlewoman`
**Classification:** Internal — Board use

---

## 1. Executive Summary

Gentle Woman needs a modern, branded online sales channel that reflects an
editorial fashion identity while running on real, governed back-office systems.
Off-the-shelf webshops force a trade-off between **brand experience** and
**operational control**. This initiative removes that trade-off.

We have built and proven a **headless commerce storefront**: a fast, fully
brand-controlled customer website (Next.js) that uses **Odoo as the single
system of record** for catalog, stock, pricing, orders, customers, promotions
and fulfilment. Editorial content the catalog cannot supply (hero banners,
campaign imagery, announcements) is managed in Odoo too — **no second software
system to license or operate.**

A live pilot is running today with end-to-end shopping, store locator,
click-&-collect, customer accounts, an affiliate program, bilingual content
(Indonesian / English) and a hardened, encrypted security posture.

**Ask of the Board:** endorse moving the pilot toward production launch, and
approve the two external dependencies that gate full go-live — the **Eraspace
payment integration** and (optionally) the **AI personal-shopper** budget.

---

## 2. The Business Need

| Need | Why it matters | How this initiative answers it |
|---|---|---|
| A branded, editorial storefront | Fashion sells on experience; generic templates dilute the brand | Fully custom Next.js front-end the brand team controls |
| One source of truth | Avoid stock/price/order mismatches across channels | Odoo is authoritative; the website only *presents* it |
| Omnichannel (online + stores) | Customers expect "buy online, pick up / find in store" | Store locator + real-time in-store stock + click-&-collect |
| Low operating overhead | Every extra system is cost + risk | Editorial CMS lives inside Odoo — zero new services |
| Growth levers | Acquire & retain cost-effectively | Affiliate program, promotions, wishlist, newsletter |
| Compliance & trust | UU PDP (data protection); brand reputation | Consent capture, strict security, encrypted customer data |

---

## 3. What Has Been Delivered (Live Pilot)

**Shopping & catalog**
- Product listing & detail with image galleries, size/variant availability,
  material composition, tags, "New" badges, and promotional strike-through
  pricing — all driven from Odoo.
- Price-range and tag filtering; bilingual catalog (ID/EN).

**Omnichannel**
- **Store Locator** with "nearest store" geolocation, opening hours, directions.
- **Real-time in-store stock** per outlet on the product page.
- **Click & Collect** — reserve and pick up at a chosen store.

**Customers & growth**
- Customer accounts, **guest checkout** (no account required), saved shipping &
  billing addresses, order history.
- **Wishlist** with one-click move-to-cart.
- **Affiliate program** — self-serve dashboard, trackable links, social sharing,
  automatic commission attribution and payout tracking.
- Newsletter sign-up; promotional banners and campaigns.

**Content (editorial CMS, inside Odoo)**
- Hero banner, lookbook, editorial sections, collection tiles, footer, and a
  dismissible announcement bar — all editable by the brand team in Odoo,
  bilingual, no developer needed.

**Trust & security**
- HTTPS everywhere; customer session tokens held in hardened, encrypted cookies;
  customer personal data **encrypted at rest**; defenses against common web
  attacks (injection, cross-site scripting, request forgery, abuse).
- Consent capture aligned to **UU PDP**.

---

## 4. Business Value

- **Brand-led conversion.** A bespoke, editorial experience that no template can
  match — the storefront is a brand asset, not a rented page.
- **Operational integrity.** Real inventory, real pricing, real orders — one
  system, no reconciliation. Fewer errors, lower support cost.
- **Omnichannel revenue.** In-store stock visibility and click-&-collect bring
  online demand into physical stores and reduce lost sales.
- **Lower total cost of ownership.** Editorial content runs inside the existing
  Odoo platform — no separate CMS license, server, or admin team.
- **Scalable acquisition.** The affiliate engine turns customers and influencers
  into a measurable, commission-based sales force.
- **Compliance & reputation.** Privacy consent and strong security reduce
  regulatory and brand risk.

---

## 5. Roadmap & Dependencies

**Phase 1 — Foundation (DONE, live pilot)**
Catalog, content, store locator, in-store stock, click-&-collect, accounts,
guest checkout, wishlist, affiliate, promotions, i18n, security hardening.

**Phase 2 — Go-live enablers (gated)**
- **Payment — Eraspace API (BLOCKED on vendor documentation).** Checkout is built
  through to order creation; the payment step is stubbed behind a feature flag and
  activates the moment the Eraspace API spec is provided.
- Affiliate payouts operationalization; richer promotions/loyalty.

**Phase 3 — Differentiation (decision required)**
- **AI Personal Shopper / Stylist** (outfit recommendations grounded in live
  catalog & stock). Requires external AI services and an operating budget.
- Virtual try-on / 3D for accessories (R&D).

---

## 6. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Eraspace payment doc delayed | Medium | Checkout decoupled behind a provider interface; launch-ready except payment |
| Single-tenant scaling | Low | Platform is multi-tenant by design; storefront is stateless/containerized |
| Data protection (UU PDP) | Medium | Consent capture + at-rest PII encryption already implemented |
| Vendor/key management | Low | Documented secret-rotation procedure; encryption keys externalized |
| AI cost overrun | Medium | AI is opt-in, budget-gated, and not on the launch critical path |

---

## 7. Recommendation

1. **Endorse** progression of the pilot to a production launch plan for Gentle
   Woman on the existing Odoo platform.
2. **Unblock payment** — direct the Eraspace integration documentation to the
   delivery team to complete the single remaining go-live dependency.
3. **Decide on AI** — approve (or defer) the AI personal-shopper budget as a
   Phase-3 differentiator, independent of launch.

**Supporting documentation:** Project Initiation Document, Business Requirements
(BRD), Functional Specification (FSD), and Technical Specification (TSD) accompany
this briefing and are available for download from the platform.
