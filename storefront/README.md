# Gentle Woman — Headless Storefront

A Next.js 14 (App Router) storefront for the **Gentle Woman** retail tenant.
Odoo is the commerce + FICO backend (via `custom_storefront_api`); payment is
**Eraspace** (stubbed until credentials arrive).

## Stack
- Next.js 14 (standalone output) + TypeScript + Tailwind
- **framer-motion** — page/scroll motion, cart drawer, editorial reveals
- **@react-three/fiber + drei** — 3D hero accent + draggable PDP product viewer
  (lazy, client-only via `next/dynamic({ ssr:false })`)
- **zustand** — cart + auth stores

## Architecture — the BFF is the security boundary
The browser never talks to Odoo directly. All calls go through Next.js route
handlers:
- `src/app/api/store/[...path]` → proxy to Odoo `/storefront/api/*` (public +
  JWT; forwards the customer's `Authorization: Bearer`).
- `src/app/api/store-admin/[...path]` → **HMAC-signs** to
  `/storefront/api/admin/*` (the `STOREFRONT_HMAC_SECRET` stays server-side;
  signing in `src/lib/hmac.ts` mirrors Odoo's `secure_endpoint` scheme).
- `src/app/api/health` → Docker healthcheck.

Tenant resolution: `src/lib/odoo.ts` sets the `Host` header to
`ODOO_TENANT_HOST` so Odoo's `dbfilter=^%d$` selects the tenant DB.

## Local dev
```bash
cp .env.example .env.local   # set STOREFRONT_HMAC_SECRET to match Odoo
npm install
npm run dev                  # http://localhost:8080
```

## Build / container
```bash
docker compose build storefront
docker compose up -d storefront
```
Served behind Caddy at `https://shop.gentle-woman.platform.localhost`.

## Images / licensing
`public/placeholder/` holds neutral placeholders. **Do not** copy imagery from
gentlewomanonline.com or any third party — model the layout/motion language
only. Real catalog imagery is served from Odoo (`/web/image/product.template/
<id>/image_*`); configure `NEXT_PUBLIC_ODOO_PUBLIC_URL`.
