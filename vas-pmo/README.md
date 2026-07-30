# vas-pmo — headless UI + notification BFF

Next.js 15 (App Router) front end for the **Product Owner — Value-Added Services** team,
sitting on top of Odoo 19 CE. Same architecture as `storefront/`: baked standalone image,
read-only filesystem, BFF → Odoo over the internal TLS terminator with the CA pinned.

Container port **8080**, published on **18110** (`VAS_PMO_PORT`).

## What lives here

| Path | Purpose |
|---|---|
| `src/app/(app)/portfolio` | Project health per brand vertical — the "what is slipping" screen |
| `src/app/(app)/board` | Kanban across the seven stages, including Hold and Waiting User Verification |
| `src/app/(app)/tasks/[id]` | Task detail: two honest numbers, hold, verification, transaction log |
| `src/app/(app)/weekly` | Weekly progress reports (the factual half is written by Odoo) |
| `src/app/(app)/cr` | Change requests with impact, approval tiers and response SLA |
| `src/app/api/notify` | **HMAC endpoint Odoo's outbox POSTs to.** Renders and sends WA + e-mail |
| `src/app/api/health` | Container health; reports the Odoo hop separately |
| `src/lib/services/*` | WaHub client, WhatsApp transport, e-mail, templates, orchestrator |

## The notification path

The event is **not** raised here. Four different writers can change a task (this UI, the
Odoo backend, the Jira webhook, the ticket bridge), so Odoo owns the outbox and this app
is the renderer and sender it hands off to:

```
project.task.write()  ->  custom.project.notify.outbox  ->  cron (1 min)
      -> POST /api/notify  (X-Signature = HMAC-SHA256(secret, ts + body), 5-min window)
      -> notification-service.deliver()
           -> whatsapp-service  (WaHub primary  ->  baileys fallback)
           -> email-service     (SMTP)
      <- per-channel results  ->  custom.project.notify.log
```

E-mail and WhatsApp run independently: one failing never stops the other, and nothing in
this path throws. That contract is lifted from e-Telekomunikasi's
`notification-service.ts`, as is the WhatsApp message shape and the `NOTIFICATION_TEST_MODE`
safety valve that redirects every message to a single tester.

## Environment

| Variable | Meaning |
|---|---|
| `ODOO_BASE_URL` | `https://nginx` in the cluster; `http://odoo:8069` for a plain dev run |
| `ODOO_INTERNAL_CA` | Path to the pinned internal cert (mounted read-only) |
| `ODOO_TENANT_DB` | `rnd_vas_pmo` → `prd_vas_pmo` |
| `VAS_PMO_HMAC_SECRET` | Must equal `ir.config_parameter custom_core.secure_endpoint.vaspmo.secret` |
| `WA_PROVIDER` | `wahub` (default) or `baileys` — the other one becomes the fallback |
| `WAHUB_API_URL` / `WAHUB_APP_ID` / `WAHUB_APP_SECRET` | WaHub client credentials |
| `BAILEYS_URL` / `BAILEYS_API_KEY` | Platform WhatsApp gateway (compose service `baileys`) |
| `SMTP_*`, `MAIL_FROM` | E-mail channel |
| `NOTIFICATION_TEST_MODE`, `NOTIFICATION_TEST_PHONE`, `NOTIFICATION_TEST_EMAIL` | Redirect everything to one tester |

## Run it

```bash
# Odoo side (once)
make init-db DB=rnd_vas_pmo
docker compose exec odoo odoo -d rnd_vas_pmo -i custom_project_api --stop-after-init --no-http

# point Odoo's outbox at this app and share the secret
#   custom_project_notify.bff_url          = http://vas-pmo:8080
#   custom_core.secure_endpoint.vaspmo.secret = $VAS_PMO_HMAC_SECRET
#   auth.jwt.validator "vaspmo".secret_key  = $VAS_PMO_JWT_SECRET

docker compose build vas-pmo && docker compose up -d vas-pmo
open http://localhost:18110
```

Log in with an Odoo account that holds a `VAS PMO / *` group. Tokens are kept in httpOnly
cookies — never `localStorage`, because an XSS on the board must not be able to walk away
with a token that can write to Odoo.

## Styling

Plain CSS in `src/app/globals.css`, using the design tokens from the approved mockup, so
the shipped app looks like what was signed off. No Tailwind here — the storefront uses it,
but this app's UI came straight from a hand-designed mockup and re-expressing that in
utility classes would have lost the details for no gain.
