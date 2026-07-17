# Functional Specification Document (FSD)
## Gentle Woman — Headless Commerce Storefront

**Audience:** Product, QA, Delivery
**Version:** 1.0
**Traceability:** references BRD requirements (BR-x)

---

## 1. Solution Overview

A Next.js storefront presents the experience; a Backend-for-Frontend (BFF) layer
proxies to Odoo, which is the system of record. All customer traffic is
same-origin to the storefront; the storefront talks to Odoo server-side.

```
Customer ─ HTTPS ─► Next.js Storefront (UI + BFF)
                         │  server-side
                         ▼
                       Odoo  (catalog, stock, price, orders, customers,
                              promotions, fulfilment, affiliate, content)
```

## 2. Functional Modules

### 2.1 Catalog (BR-1..BR-4)
- **Product Listing (PLP):** grid of products with image, name, price, promo
  badge ("−30%"), "New" badge, sold-out state. Controls: category select, tag
  chips (multi-select), price-range (min/max), sort (newest, price, A–Z),
  language (ID/EN). Pagination via "load more".
- **Product Detail (PDP):** gallery + optional 3D viewer, name, price with
  strike-through when discounted, reference code, tags, description, material &
  composition, size/variant availability (sold-out greyed), add-to-cart,
  add-to-wishlist, share, and an **in-store availability** panel.
- **Behaviour:** prices reflect the active pricelist; "New" is derived from a
  drop/launch date within a configurable window; translated fields switch with
  language.

### 2.2 Store Locator & In-store Stock (BR-5, BR-6)
- **Store Locator page:** list of published stores (name, address, hours, phone),
  "directions" link, and a "nearest to me" action using browser geolocation
  (distance-sorted; location never leaves the device except for the map link).
- **In-store stock (PDP):** per-store on-hand quantity and availability for the
  product, read live from Odoo warehouse stock.

### 2.3 Cart & Checkout (BR-7..BR-11, BR-23)
- **Cart:** add/update/remove lines; totals (incl. tax) computed by Odoo.
- **Fulfilment choice:** **Delivery** (carrier selection + shipping address) or
  **Pickup in store** (click-&-collect — choose a store; no shipping fee).
- **Address:** guests enter an inline address; members select a saved address or
  add a new one; optional separate **billing** address.
- **Consent:** mandatory data-processing consent (UU PDP); optional marketing.
- **Payment:** order is created; payment initiates via Eraspace (pending vendor
  API — currently a stubbed step behind a feature flag).
- **Guest checkout:** a password-less guest session is issued from an email +
  name + consent; the full cart/checkout works identically to a member.

### 2.4 Accounts & Addresses (BR-8..BR-10)
- Register (name, email, phone, password, consent) → account becomes an Odoo
  customer. Login / logout.
- Account area: order history, order detail (status, lines, totals, tracking),
  address book (shipping & billing — add / edit / delete), wishlist, affiliate.

### 2.5 Wishlist (BR-12)
- Heart toggle on cards & PDP; wishlist page; per-item and "move all" to cart.

### 2.6 Affiliate Program (BR-13, BR-14)
- **Self-serve:** a logged-in customer can become an affiliate, receive a unique
  code, generate trackable links (any storefront path), and share them
  (WhatsApp / Facebook / X / Telegram / copy). Dashboard shows clicks,
  conversions and earned/pending commission.
- **Tracking:** a link with the affiliate identifier sets a consent-gated
  first-party cookie; the click is recorded (hashed IP/UA — no raw PII).
- **Attribution:** at checkout the order is tagged with the affiliate code; on
  confirmation a commission is created (configurable rate; last-click; 30-day
  window) and held until the reversal window passes, then approved; payouts are
  batched. Anti-fraud: self-referral blocked, unknown/inactive codes ignored,
  clicks de-duplicated.

### 2.7 Editorial Content / CMS (BR-17, BR-18)
- Content blocks managed in Odoo (**Storefront ▸ Site Content**), each keyed by a
  stable code and bilingual: hero copy, editorial sections, lookbook, collection
  tiles, promo banner (on the listing page), footer copy, newsletter copy, and a
  dismissible **announcement bar** in the header.
- The home hero retains an animated 3D visual; CMS supplies its copy.
- Newsletter sign-up stores subscribers in Odoo (explicit consent).

### 2.8 Internationalization (BR-4, BR-18)
- Language switch (ID/EN) with `/id` and `/en` URLs; catalog & editorial content
  translate via Odoo; UI labels via a dictionary; shared links carry the locale.

## 3. Key Business Logic & Rules

- **Pricing:** displayed price = active pricelist price; discount badge & strike
  price computed from the difference vs. catalog price.
- **"New":** drop date (or creation date) within the configured window.
- **In-store availability:** on-hand quantity per published store location.
- **Affiliate commission:** goods value × rate; states pending → approved →
  paid, or reversed if the order is cancelled/returned.
- **Address ownership:** a selected shipping/billing address must belong to the
  customer (enforced server-side).
- **Guest isolation:** a guest email that already has an account is rejected
  ("please sign in") — a guest can never resolve to a registered customer.

## 4. Primary User Journeys

1. **Browse → buy (delivery):** PLP → PDP → add to cart → checkout → address →
   carrier → place order → (payment) → confirmation.
2. **Click-&-collect:** PDP (see in-store stock) → cart → "Pickup in store" →
   choose store → place order.
3. **Guest checkout:** add to cart → prompted → "continue as guest" (email +
   name + consent) → address → place order.
4. **Affiliate:** apply → generate link → share → visitor buys → commission
   attributed and visible in the dashboard.
5. **Content update:** brand edits hero/banner/announcement in Odoo → reflected
   on the storefront (bilingual).

## 5. Non-functional (functional view)

- **Languages:** Indonesian (default) and English.
- **Currency:** IDR.
- **Accessibility/UX:** responsive; editorial, calm visual language.
- **Privacy:** consent gating for cookies and marketing; data-subject rights
  supported via Odoo records.

## 6. Acceptance Tests (representative)

| Ref | Test | Expected |
|---|---|---|
| AT-1 | Filter PLP by tag + price | Only matching products shown |
| AT-2 | Switch ID/EN on PDP | Name, description, material translate |
| AT-3 | Promo product | Strike price + "−x%" badge |
| AT-4 | PDP in-store stock | Per-store quantities; sold-out marked |
| AT-5 | Guest delivery checkout | Order created with the entered address |
| AT-6 | Click-&-collect | Order created against the chosen store |
| AT-7 | Member saved address + billing | Order uses selected shipping & billing |
| AT-8 | Affiliate link → purchase | Click recorded; commission attributed |
| AT-9 | Edit announcement in Odoo | Banner updates on the site (ID/EN) |
| AT-10 | Register without consent | Rejected with a clear message |
