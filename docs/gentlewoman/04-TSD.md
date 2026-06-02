# Technical Specification Document (TSD)
## Gentle Woman — Headless Commerce Storefront

**Audience:** Engineering, DevOps, Security
**Version:** 1.0
**Companion:** FSD (functional behaviour), BRD (requirements)

---

## 1. Architecture

A **headless** design: a Next.js storefront (UI + Backend-for-Frontend) over
**Odoo 19 CE** as the system of record, on the shared multi-tenant Odoo Platform.

```
Browser ─HTTPS(Caddy/TLS)─► Next.js Storefront (App Router)
                              ├─ UI (React, Tailwind, framer-motion, three.js)
                              └─ BFF API routes (/api/store, /api/img, /api/affiliate)
                                      │  server-side, TLS-pinned
                                      ▼
                              storefront-tls (TLS sidecar) ─► Odoo :8069
                                      │
        Odoo modules: custom_storefront_api, custom_affiliate, custom_core,
        custom_ecommerce, custom_payment_id, custom_pdp_*  ─►  PostgreSQL
```

- **Tenant resolution:** the BFF sends an `X-Odoo-Database` header selecting the
  `gentlewoman` database; the browser never talks to Odoo directly.
- **Single source of truth:** Odoo owns catalog, stock, price, orders, customers,
  promotions, fulfilment, affiliate and editorial content.

## 2. Components

### 2.1 Storefront (Next.js, container `storefront`)
- App Router pages (home, PLP, PDP, cart, checkout, stores, account/*).
- BFF route handlers proxy to Odoo, inject auth/tenant headers server-side, and
  never expose secrets to the browser.
- Server-rendered SEO/Open-Graph metadata per product (localized).
- State: lightweight client stores for cart, wishlist, auth (profile only),
  locale, UI.

### 2.2 Odoo modules
| Module | Responsibility |
|---|---|
| `custom_storefront_api` | Public catalog/content/stores API, JWT customer API (cart, wishlist, addresses, orders, checkout), HMAC admin API, editorial content model, store-locator fields, PII-at-rest, guest checkout |
| `custom_affiliate` | Affiliate master/links/clicks/conversions/payouts, order attribution, public click-tracking, daily lifecycle cron |
| `custom_core` | Shared platform: HMAC secure-endpoint, Fernet field encryption helpers |
| `custom_ecommerce`, `custom_payment_id` | Shipping rate quotes; payment adapters (Eraspace stub) |
| `custom_pdp_*` | Data-protection support |

### 2.3 Data model highlights (Odoo)
- Catalog on native `product.template`/`product.product` + `product.tag`,
  `product.public.category`, pricelists; storefront adds `custom_drop_date`,
  `custom_material_composition`.
- Stores = published `stock.warehouse` (+ geo/hours fields); in-store stock from
  `stock.quant`.
- `custom.storefront.content` (editorial blocks), `custom.storefront.subscriber`
  (newsletter), `custom.wishlist`, `custom.affiliate*`.
- `sale.order` extended with affiliate code/id, pickup flag.

## 3. API Surface (selected)

- **Public:** `GET /storefront/api/{categories,products,products/<id>,
  products/<id>/availability,tags,stores,content}`, `POST .../shipping/quote`,
  `POST .../newsletter`. Catalog endpoints accept `lang`, `tag`, `price_min/max`.
- **Customer (JWT):** auth `register/login/guest/refresh/logout`; `customer/me`,
  addresses; cart (items, address, pickup, shipping); checkout & pay; orders;
  wishlist (+ move-to-cart); affiliate (me/apply/links).
- **Admin (HMAC, server-to-server):** health, product sync, order status.

## 4. Security

Layered, defense-in-depth (all implemented):

- **Transport:** browser↔storefront over HTTPS/TLS (Caddy). **BFF↔Odoo over a
  dedicated TLS sidecar** (`storefront-tls`) with certificate pinning — the one
  internal hop that previously carried tokens/PII in cleartext is now encrypted.
- **Sessions:** customer auth tokens live in **HttpOnly cookies** (never in
  browser JS), additionally **sealed with AES-256-GCM** so the token/claims are
  unreadable at rest; the BFF injects the bearer server-side and transparently
  refreshes; refresh tokens are stored hashed.
- **PII at rest:** customer `phone/street/zip` are **Fernet-encrypted** in the
  database (email kept plaintext as it is the identity key); transparent
  decrypt on read.
- **Application:** strict Content-Security-Policy and security headers; HTML
  sanitization; image proxy locked to `/web/image` (anti-SSRF); rate-limiting and
  body-size caps on sensitive endpoints; address ownership checks (anti-IDOR);
  no raw SQL (ORM only); UU PDP consent capture.
- **Secrets:** JWT signing key, HMAC secret, cookie-seal key and the Fernet master
  key are externalized via environment/secret config; rotation procedures
  documented.

## 5. Internationalization

URL-prefixed locales (`/id`, `/en`) via middleware; Odoo translatable fields drive
catalog/editorial content (`?lang=`); UI strings via dictionary; localized OG tags.

## 6. Deployment & Operations

- Containerized via Docker Compose on the platform (`storefront`,
  `storefront-tls`, `odoo`, `postgres`, `redis`, `caddy`, `nginx`).
- Storefront is a baked production build (read-only filesystem); deploy = rebuild
  image + recreate; Odoo module changes applied per-tenant (`-u … -d gentlewoman`).
- Tenant isolation: all storefront changes are scoped to `gentlewoman`; other
  tenants are unaffected (verified).
- Health checks on storefront and Odoo; logging/observability via the platform.

## 7. Performance & Scaling

- Stateless storefront container → horizontally scalable behind the proxy.
- Catalog reads are cache-friendly; image delivery via a same-origin proxy.
- Rate-limiter is currently in-memory (single instance) — move to Redis for
  multi-instance horizontal scale.

## 8. Dependencies & Constraints

- **Payment (Eraspace):** BLOCKED on vendor API documentation; checkout is built
  to order creation behind a `PaymentProvider` interface + feature flag.
- **AI (Phase 3):** requires external AI services (vector search, model API) and
  an operating budget; not on the launch critical path.
- Encryption requires the platform master/seal keys to be present and rotated per
  policy.

## 9. Known Trade-offs

- PII fields encrypted at rest are no longer searchable/groupable in the Odoo
  back-office (accepted).
- Content-Security-Policy uses inline-allow for scripts (compatible with Next
  static prerendering) while blocking all external/injected scripts.
- Pre-encryption database backups contain plaintext PII and must be secured or
  deleted after a stability window.

## 10. Acceptance (technical)

- All Phase-1 journeys pass end-to-end over the encrypted stack.
- Security checklist satisfied (transport, session, at-rest, app-layer).
- Tenant isolation confirmed; other tenants unaffected.
- Documentation (this set) maintained alongside module knowledge files.
