# Baileys WhatsApp Sidecar

Node.js sidecar that bridges Odoo's `custom_whatsapp` module to WhatsApp Web
via the [Baileys](https://github.com/WhiskeySockets/Baileys) library. Used
when a `whatsapp.account` record sets `provider = baileys` instead of
`meta_cloud`.

## Why a separate service

Baileys keeps a persistent WebSocket to WhatsApp and stores Signal-protocol
key material on disk. Odoo (Python, request-scoped) cannot host that loop,
so the sidecar runs alongside Odoo on the internal docker network.

Multiple Odoo accounts can share one sidecar instance — each
`whatsapp.account` gets its own `baileys_session_id` and auth state is
isolated per `${BAILEYS_AUTH_DIR}/<session_id>/`.

## Endpoints

All endpoints (except `/healthz`) require `Authorization: Bearer
${BAILEYS_SHARED_SECRET}`. Replies to Odoo include
`X-Baileys-Signature: sha256=<hmac>` computed with the same secret.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | Liveness — no auth |
| `POST` | `/sessions/:id/start` | Boot socket; returns `{status: "qr_pending" \| "connected"}` |
| `GET`  | `/sessions/:id/qr` | Pairing QR (`?format=base64` returns data URL, otherwise PNG) |
| `GET`  | `/sessions/:id/status` | `{status, phone}` |
| `POST` | `/sessions/:id/logout` | Tear down socket + wipe auth dir |
| `POST` | `/sessions/:id/messages` | Body `{to, type: "text", text}`; returns `{id}` |

Inbound events are POSTed back to Odoo at
`${ODOO_WEBHOOK_BASE}/custom_whatsapp/webhook/<account_id>` with
`X-Baileys-Event: connection | status | message`.

## Environment

| Variable | Default | Notes |
|----------|---------|-------|
| `PORT` | `8088` | Listen port inside the container |
| `BAILEYS_SHARED_SECRET` | _(required)_ | Bearer token + HMAC key |
| `BAILEYS_AUTH_DIR` | `/var/lib/baileys` | Persisted Signal auth state — back this up |
| `ODOO_WEBHOOK_BASE` | _(required)_ | e.g. `http://odoo:8069` |
| `LOG_LEVEL` | `info` | pino level |

## Pairing flow

1. In Odoo: open the `whatsapp.account`, set provider to **Baileys**, fill
   in `baileys_sidecar_url` + shared secret, save.
2. Click **Start Session** → Odoo `POST /sessions/<id>/start`.
3. Click **Refresh QR** → Odoo `GET /sessions/<id>/qr` and displays the PNG.
4. Scan from WhatsApp mobile (Linked Devices). The sidecar pushes a
   `connection` webhook; the account flips to `connected` and the QR clears.

## Operational notes

- **Ban risk**: Baileys speaks the WhatsApp Web protocol, which Meta does
  not officially support. Spam-like outbound patterns can get the number
  banned. The `custom_whatsapp` queue throttling still applies.
- **Auth state**: deleting `${BAILEYS_AUTH_DIR}/<session_id>/` forces a
  re-pair. Volume is mounted at `./data/baileys` by default — include it
  in your backup policy.
- **Restart safety**: on container restart, sessions auto-resume from the
  persisted auth state. No re-pair needed.
- **Reachability**: bind the published port to localhost only in prod
  (`docker-compose.prod.yml` uses `expose` rather than `ports`). The
  shared secret is the only authn — do not expose to the public internet.
