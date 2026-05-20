# landing-public

Next.js 15 (App Router, TypeScript strict) public landing for the Odoo
multi-tenant platform onboarding flow.

Pages:
- `/` — marketing hero + CTA.
- `/intake` — multi-step wizard (company, vertical, modules, narrative, BRD + Turnstile).
- `/status/[token]` — read-only progress timeline.

## Setup

```bash
cd apps/landing-public
cp .env.example .env.local
# fill ORCHESTRATOR_BASE_URL + ORCHESTRATOR_SHARED_SECRET + TURNSTILE_SITE_KEY
npm install
npm run dev          # http://localhost:3000
npm run build && npm start
```

## Environment

| Var | Scope | Purpose |
|---|---|---|
| `ORCHESTRATOR_BASE_URL` | server | FastAPI orchestrator base, e.g. `http://orchestrator:8000` |
| `ORCHESTRATOR_SHARED_SECRET` | server | HMAC secret — MUST match `orchestrator_shared_secret` in tenant-orchestrator settings. **Never exposed to browser.** |
| `TURNSTILE_SITE_KEY` | server (re-exposed as `NEXT_PUBLIC_TURNSTILE_SITE_KEY`) | Cloudflare Turnstile site key. If unset, the widget falls back to a dev token so local dev keeps working. |

## Architecture

```
Browser ─POST /api/intake──▶ Next.js Route Handler ─HMAC─▶ FastAPI orchestrator /v1/intake/submit ─JSON-RPC─▶ Odoo (odoo-mgmt)
Browser ─GET  /status/...──▶ Next.js Server Component ─HMAC─▶ /v1/intake/{token}/status ─────────────────────▶ Odoo (odoo-mgmt)
```

The HMAC signing helper is `lib/api.ts` — it mirrors the scheme implemented in
`tenant-orchestrator/app/security.py` (`HMACMiddleware`) and the Odoo client
`addons/verticals/custom_super_admin/models/orchestrator_client.py`:

```
X-Custom-Signature: t=<unix_ts>,v1=<hex(hmac_sha256(secret, f"{ts}.{body}"))>
X-Custom-Actor:     landing-public
```

The shared secret is read from `process.env.ORCHESTRATOR_SHARED_SECRET` and is
only ever accessed from server contexts (route handlers, server components).

## Deployment

`next.config.js` sets `output: 'standalone'` so the produced `.next/standalone`
directory can be packaged into a slim Docker image. Mount the secret via your
orchestrator process env (e.g. Docker Compose `env_file: .env`).

## Notes for orchestrator integration

The orchestrator counterpart is `tenant-orchestrator/app/routers/intake.py`.
When merging Track G, the parent agent MUST:

1. Register the new router in `tenant-orchestrator/app/main.py`:
   ```python
   from .routers import intake
   app.include_router(intake.router)
   ```
2. Add CORS middleware allowing the landing origin:
   ```python
   from fastapi.middleware.cors import CORSMiddleware
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[os.getenv("LANDING_PUBLIC_ORIGIN", "http://localhost:3000")],
       allow_methods=["GET", "POST"],
       allow_headers=["*"],
   )
   ```
3. Set orchestrator env: `ODOO_MGMT_URL`, `ODOO_MGMT_DB`, `ODOO_MGMT_USER`,
   `ODOO_MGMT_PASSWORD` (or `ODOO_MGMT_API_KEY`), and optionally
   `TURNSTILE_SECRET` for server-side captcha verification.
