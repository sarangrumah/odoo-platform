# MVP Implementation Plan — AI Personal Shopper (Gentle Woman)

> Status: **PROPOSED — awaiting approval** (Phase-3 feature, budget-gated per BRD §7).
> Scope: text-based personal shopper grounded on the live Odoo catalog.
> **No** Qdrant/vector search, **no** virtual try-on, **no** purchase-history personalization (all deferred).
> This is the spec §3 "Fase A" slice from `docs/spec-headless-fashion-commerce-ai.md` (§7 roadmap).

## 1. Architecture

The existing `ai-gateway` already has a generic, HMAC-protected `/v1/chat` with Anthropic
tool-calling + prompt caching, but **no Odoo access**. The Odoo catalog API is public HTTP.
So the agent loop (decides + executes tool calls) must run where it can reach *both* the
gateway and the Odoo catalog.

- **Option A (recommended): agent loop in the ai-gateway** as a new `/v1/shopper` router.
  It calls `/v1/chat` internally (reuse provider + caching) and calls the Odoo storefront
  catalog API for tools (`http://odoo:8069/storefront/api/*`, reachable on the Docker network).
- Option B: agent loop in the Next.js BFF — rejected (re-implements the tool loop + provider
  logic in TypeScript).

**Recommended flow:**

```
Browser (ShopperWidget)
  → POST /api/shopper            (Next.js BFF route, rate-limited, session cookie)
    → POST /v1/shopper           (ai-gateway, HMAC-signed via lib/hmac.ts)
        loop (server-side, max ~4 tool rounds):
          → /v1/chat (internal, Anthropic + tools + cached system)
          → tool calls → GET /storefront/api/products | /products/<id> | /products/<id>/availability
        → returns { reply, product_ids[], escalate? }
    ← BFF returns reply + real product cards to the browser
```

Session state (first-turn greeting flag, short history) — MVP keeps history client-side and
sends the last N turns (no Redis writes). Redis-backed memory is a later phase.

## 2. Agent tools (function-calling)

Three tools, all backed by **existing** endpoints in `custom_storefront_api/controllers/public_api.py`
— **no new Odoo endpoint required for MVP**:

| Tool | Existing endpoint | Notes |
|---|---|---|
| `search_products(q?, category?, tag?, price_min?, price_max?, sort?, limit?)` | `GET /storefront/api/products` | Supports `q` (name ilike), `category` (child_of), `tag` (id list), price bounds, sort, pagination. Domain `sale_ok=True`. Returns cards: `id, name, price, compare_at, discount_pct, currency, tags[], categories[], in_stock, image, ref`. |
| `get_product(product_id)` | `GET /storefront/api/products/<id>` | `detail=True`: adds `description, material, variants[]` (per-variant in_stock + attributes like Size). |
| `check_availability(product_id)` | `GET /storefront/api/products/<id>/availability` | Per-store on-hand. The card `in_stock` flag already covers "is it buyable". |

**Tag taxonomy bridge:** `search_products` filters tags by integer id, but the model reasons in
words. Prefetch the tag list once (`GET /storefront/api/tags` → `{id,name}`) and inject it into
the cached system prompt so the model maps concepts → tag ids, or relies on `q` + price + category.
(Semantic search = deferred Qdrant phase.)

## 3. File-by-file work list

### (a) ai-gateway
- `ai-gateway/app/routers/shopper.py` (new) — `POST /v1/shopper`; runs the capped tool loop.
- `ai-gateway/app/shopper/odoo_catalog.py` (new) — async httpx client for the catalog endpoints.
- `ai-gateway/app/shopper/tools.py` (new) — tool JSON schemas + dispatcher + grounding guard.
- `ai-gateway/app/prompts/shopper_system.md` (new) — persona ("Kak", greet first turn only),
  guardrails, few-shot examples; loaded like `nlq.py` loads its prompt, passed as cached block.
- Edit `ai-gateway/app/main.py` — include the shopper router.
- Edit `ai-gateway/app/config.py` — add `odoo_storefront_url` + `ai_model_shopper`.
- Edit `ai-gateway/app/providers/anthropic.py` — expose `tool_use` blocks on `ChatResponse`
  (the loop must read tool calls; currently only text parts are returned). Small but required.

### (b) Odoo catalog API (custom_storefront_api)
- **No new endpoint required for MVP.** Existing `/products`, `/products/<id>`,
  `/products/<id>/availability`, `/tags` cover all three tools.

### (c) storefront (Next.js)
- `storefront/src/app/api/shopper/route.ts` (new) — BFF POST: rate-limit (`lib/ratelimit.ts`),
  body cap, HMAC-sign (`lib/hmac.ts`), forward to `${AI_GATEWAY_URL}/v1/shopper`. Add `AI_GATEWAY_URL`
  to env; keep gateway URL + secret server-side.
- `storefront/src/components/shopper/ShopperWidget.tsx` (new) — floating launcher + chat panel,
  client component, lazy via `next/dynamic({ ssr:false })`; renders assistant text + **real
  product cards** (reuse `src/components/product/` card).
- `storefront/src/components/shopper/index.ts` + mount in `MainShell.tsx` / `app/layout.tsx`
  next to `CookieConsent` so it shows on every page.
- `storefront/src/lib/types.ts` — add `ShopperMessage`, `ShopperResponse`.
- Animated maskot (Lottie/Rive) deferred; MVP ships a styled button + framer-motion panel.

## 4. Grounding / guardrail rule

Two layers:
1. **Prompt:** "Only recommend products returned by `search_products`/`get_product`. Never invent
   SKU, price, or stock. Every recommendation must carry a `product_id`. For price/stock you must
   use a tool. If nothing fits, say so honestly and offer the closest alternative."
2. **Code (hard guard):** the gateway tracks the set of `product_id`s actually returned by tool
   calls; the response `products[]` is built only from that set (live `price`/`in_stock` from the
   tool payload). Products the model names but that weren't tool-returned are dropped. Only
   `in_stock=true` products surface. Prices are always live Odoo values.

Escalation (spec §3.6): return `escalate=true` on CS/complaint/return intent or after 3 empty-result
turns; widget surfaces a "Chat with a human / WhatsApp" CTA.

## 5. Model choice & cost

- **Default: Claude Haiku** for the conversational + tool-selection loop (cheap, fast, capable).
- **Escalate to Sonnet** only for multi-item outfit composition ("complete the look", budget-bound).
  MVP can ship Haiku-only and add Sonnet later.
- **Not Opus** here (gateway's quality tier; too expensive/slow for chat).
- **Prompt caching is the cost lever** (already implemented): system prompt + tag taxonomy + tool
  schemas in cached blocks → cache-reads after turn 1.
- **Rough per-conversation cost:** system+tools ~1.5–3k tokens (cached after turn 1); each tool
  round adds a few hundred tokens of product JSON. A 3–4 turn Haiku session with caching lands at a
  small fraction of a cent to ~1 cent. Cap reply `max_tokens` (~700) and tool rounds at 4.

## 6. Effort estimate (dev-days)

| Component | Est. |
|---|---|
| ai-gateway: `/v1/shopper` router + tool loop + tools/catalog client | 2.0 |
| Provider tool-block passthrough fix + config/env | 0.5 |
| System prompt authoring + few-shot + grounding tests | 1.5 |
| BFF `/api/shopper` route (HMAC, rate-limit) | 0.5 |
| ShopperWidget UI + product-card reuse + mount | 1.5 |
| Wiring/env/Docker + end-to-end QA + guardrail eval | 1.0 |
| **Total MVP** | **~7 dev-days** |

**Explicitly deferred:** Qdrant vector/semantic search + embeddings + re-index webhook (§3.2);
visitor profile + purchase-history personalization + consent/PDP storage (§3.4/§3.5); Trend KB +
web-search trends (§3.3); Sonnet outfit-composition + 2D "complete the look"; animated maskot;
Redis cross-session memory; virtual try-on / 3D (§5 Fase B/C, fully out of scope).
