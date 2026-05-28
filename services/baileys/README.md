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
- **Volume ownership** (first-time setup): the container runs as
  `uid=10104(baileys)`, but a bind-mounted host directory inherits
  whatever ownership it had on the host (typically `root:root`). If
  Start Session returns `EACCES: permission denied, mkdir ...`, fix
  ownership once on the host:
  ```bash
  sudo chown -R 10104:10104 ./data/baileys
  ```
  The setting persists across restarts and recreations.
- **Restart safety**: on container restart, sessions auto-resume from the
  persisted auth state. No re-pair needed.
- **Reachability**: bind the published port to localhost only in prod
  (`docker-compose.prod.yml` uses `expose` rather than `ports`). The
  shared secret is the only authn — do not expose to the public internet.

## Pre-fill defaults on `whatsapp.account`

`baileys_sidecar_url` and `baileys_shared_secret` auto-prefill from the
Odoo container's environment when a `whatsapp.account` record is
created:

| Field | Env var | Fallback |
|-------|---------|----------|
| `baileys_sidecar_url` | `BAILEYS_INTERNAL_URL` | `http://baileys:8088` |
| `baileys_shared_secret` | `BAILEYS_SHARED_SECRET` | empty |

`baileys_session_id` stays blank by default and is resolved to
`acct-{record_id}` the first time **Start Session** is clicked.

To create the account record from the host (e.g. during tenant
provisioning) instead of clicking through the UI, use:

```bash
BAILEYS_SHARED_SECRET=$(openssl rand -hex 32) \
  bash scripts/tenants/setup_baileys_account.sh <db_name>
```

The script is idempotent — re-running it skips databases that already
have a `whatsapp.account` with the same name. Pass no arg to provision
every tenant DB at once.

## AI Auto-Draft (Hybrid mode)

The `whatsapp.account` form has an **AI Prompt** tab with three fields:

- `ai_system_prompt` — persona/tone instructions for the AI gateway
  (single string per account, in any language the model handles).
- `ai_auto_draft` — when on, every inbound message is run through the AI
  gateway and the response is stored as a draft on the message.
- `ai_max_history` — number of recent messages with the same contact to
  include as conversational context (default 10).

The draft is **never sent automatically**. On an inbound message the
agent sees:

- `AI Draft Ready` badge in the list view.
- A new **AI Draft** notebook page with the editable suggestion.
- Header buttons: **Send AI Draft** (creates an outbound message and
  fires `action_send`), **Regenerate** (re-call AI), **Dismiss Draft**.

Manual generation is also available via **Generate AI Draft** on any
inbound row even when `ai_auto_draft` is off.

Example prompt (Bahasa Indonesia, sales/CS use case):

```
Kamu adalah customer service Sarang Rumah yang ramah dan to-the-point.
Jawab dalam Bahasa Indonesia, maksimal 3 kalimat.
- Kalau pelanggan tanya stok atau harga produk, arahkan ke katalog: katalog.sarangrumah.id
- Kalau pelanggan butuh bantuan teknis, minta nomor order dan eskalasi ke tim support.
- Jangan janjikan diskon, garansi, atau jadwal pengiriman tanpa konfirmasi.
- Akhiri dengan menanyakan apakah ada yang masih bisa dibantu.
```

The AI call goes through `custom.ai._chat()` (defined in
`addons/core/custom_ai_bridge`) so the same gateway, signing, and
tenant-routing used by the rest of the platform applies.
