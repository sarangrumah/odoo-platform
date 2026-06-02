# Business Requirements Document (BRD)
## Gentle Woman — Headless Commerce Storefront

**Audience:** Business stakeholders, Product Owner, Sponsor
**Version:** 1.0
**Companion documents:** PID, FSD, TSD

---

## 1. Introduction

This BRD captures the *business* requirements for the Gentle Woman storefront —
what the business needs and why — independent of implementation detail (covered
in the FSD/TSD). Requirements are labelled **BR-x** and prioritized with MoSCoW
(Must / Should / Could).

## 2. Business Objectives

- B1. Sell Gentle Woman products online through a brand-defining experience.
- B2. Keep all commercial data (stock, price, orders, customers) in one governed
  system (Odoo).
- B3. Connect online demand to physical stores (omnichannel).
- B4. Acquire and retain customers cost-effectively.
- B5. Operate with minimal additional systems, licenses and headcount.
- B6. Comply with Indonesian data-protection law (UU PDP) and protect customer
  trust.

## 3. Stakeholders

| Stakeholder | Interest |
|---|---|
| Product Owner / Sponsor | ROI, time-to-launch, brand fit |
| Marketing / Brand | Content control, campaigns, acquisition |
| Store Operations | Stock accuracy, click-&-collect fulfilment |
| Finance | Pricing, promotions, commissions, settlement |
| Customers | Easy, trustworthy, bilingual shopping |
| Compliance / DPO | Consent, data handling, retention |

## 4. Business Requirements

### 4.1 Catalog & Merchandising
- **BR-1 (Must)** Present products with imagery, price, availability, variants
  (size), material and categories — sourced from Odoo.
- **BR-2 (Must)** Show promotional pricing (original vs. sale) and discount
  badges; highlight "New" arrivals.
- **BR-3 (Should)** Allow customers to filter by category, tag and price range,
  and to search by name.
- **BR-4 (Should)** Present catalog in Indonesian and English.

### 4.2 Omnichannel
- **BR-5 (Must)** Provide a store locator with address, hours, map directions and
  "nearest to me".
- **BR-6 (Must)** Show real-time product availability per physical store.
- **BR-7 (Should)** Allow click-&-collect (reserve & pick up in store).

### 4.3 Customer & Checkout
- **BR-8 (Must)** Support both registered accounts and guest checkout.
- **BR-9 (Must)** Capture shipping (and optional billing) address; support saved
  addresses for members.
- **BR-10 (Must)** Provide order history and order detail to customers.
- **BR-11 (Must)** Capture explicit UU PDP consent at registration / guest
  checkout (data processing mandatory; marketing optional).
- **BR-12 (Should)** Provide a wishlist with quick move-to-cart.

### 4.4 Growth & Marketing
- **BR-13 (Must)** Operate an affiliate program: unique codes, trackable links,
  click capture, order attribution, commission calculation and payout tracking,
  with anti-fraud (block self-referral, ignore unknown codes).
- **BR-14 (Should)** Provide a self-serve affiliate dashboard with social sharing.
- **BR-15 (Should)** Capture newsletter subscribers (explicit consent).
- **BR-16 (Could)** Run editorial campaigns (lookbook, promo banner, announcement).

### 4.5 Content
- **BR-17 (Must)** Let the brand team manage non-catalog editorial content (hero
  banner, section imagery, headings, footer, announcement) without a developer
  and without a separate CMS system.
- **BR-18 (Should)** Editorial content is bilingual (ID/EN).

### 4.6 Trust, Security & Compliance
- **BR-19 (Must)** Encrypt all customer-facing traffic (HTTPS).
- **BR-20 (Must)** Protect customer sessions from theft via common web attacks.
- **BR-21 (Must)** Protect customer personal data at rest.
- **BR-22 (Must)** Resist injection, cross-site scripting, request forgery, and
  brute-force abuse.

### 4.7 Payment
- **BR-23 (Must)** Complete checkout through to an order; process payment via the
  Eraspace payment service (pending vendor API).

## 5. Business Rules

- Inventory, price and order truth always come from Odoo; the website never
  invents values.
- Promotions are derived from the active pricelist; the displayed "sale" price
  reflects it.
- An order can be attributed to only one affiliate; commission is computed on
  the goods value (excl. tax/shipping) and held until the return window passes.
- Guest checkout must never be allowed to access a registered account's data.
- A customer may only use/select address records that belong to them.

## 6. Assumptions & Dependencies

- Store master data (addresses, hours, geolocation) and per-store stock are
  maintained in Odoo.
- Payment go-live depends on the external Eraspace API documentation.
- Encryption keys are supplied via secure environment configuration.

## 7. Out of Scope (current)

- Storing card/payment-instrument data (delegated to the payment provider).
- A separate third-party CMS (replaced by Odoo-managed content).
- AI personal shopper and virtual try-on (Phase 3, separate decision/budget).

## 8. Risks (business view)

| Ref | Risk | Mitigation |
|---|---|---|
| R1 | Payment dependency delays launch | Checkout decoupled; launch-ready bar payment |
| R2 | Data-protection non-compliance | Consent capture + PII encryption at rest |
| R3 | Stock inaccuracy harms click-&-collect | Real-time stock from Odoo; store ops ownership |
| R4 | Affiliate fraud | Self-referral block, dedup, unknown-code ignore |
| R5 | Brand inconsistency | Editorial content centrally managed in Odoo |

## 9. Acceptance Criteria (business)

- A customer can discover, browse (ID/EN), and purchase a product online and via
  click-&-collect.
- Guest and registered journeys both complete an order.
- The brand team can change the hero/banner/announcement content unaided.
- An affiliate link produces a tracked, attributed, commissionable order.
- Customer PII is encrypted at rest; consent is recorded.
