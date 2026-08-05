# login-gateway

The front door's tenant chooser. It exists so that `https://<front-door>/` no
longer answers with Odoo's database selector — a public list of every client's
database — while users can still reach whichever database they need.

## Flow

```
browser ──> /signin            this app: pick Vertical + Environment
              │
              │  server action: (slug, code) --config/tenants.json--> db name
              │  server-side GET odoo-front/web/login?db=<db>
              │  Odoo's ensure_db() writes session.db and answers 302
              │  + Set-Cookie: session_id
              ▼
         cookie handed to the browser, 302 to /web/login
              │
              ▼
browser ──> /web/login         Odoo's own login form, already pinned to that DB
```

The database name never reaches the browser: not in the HTML, not in a form
value, not in the URL. The `db` is resolved server-side and used exactly once,
in a request the browser never makes.

## Why it works this way

- **Odoo's own login page is kept.** MFA, password reset and per-database
  branding are Odoo's, and reimplementing them here would be a downgrade. This
  app only decides *which* database that page belongs to.
- **No passwords pass through this app.** The obvious alternative — POST
  `{db, login, password}` to `/web/session/authenticate` — would put credentials
  in the gateway, and its controller returns `{'uid': None}` for MFA users,
  which is indistinguishable from a wrong password.
- **`X-Odoo-Database` is not usable here.** Odoo 19 marks any request carrying
  it stateless (`session.can_save = False`) and answers 403 if it disagrees with
  an existing `session.db`. It is a server-to-server mechanism; a browser
  session cannot be built on it. See `odoo/http.py::_get_session_and_dbname`.

## Adding or removing an environment

Edit `config/tenants.json`:

```json
{ "code": "training", "label": "Training", "db": "trn_arkaaim" }
```

`code` and `label` are what the browser sees; `db` never leaves the server. Keep
it that way: **never make a `slug` or a `code` equal to a database name**, or the
value in the rendered `<option>` gives it away. (`gentlewoman` is published under
the slug `gw` for exactly this reason.)

The
file is read per request, so a bind-mounted edit takes effect immediately — no
rebuild. A malformed file fails loudly rather than serving a partial list.

This is a hand-maintained allow-list on purpose: a database that nobody has
deliberately published must not become reachable just because it exists on the
server. **The list shipped here mirrors the databases present in August 2026 and
should be curated** — some entries (`prd_levis_AP`, `prd_detail_levis`,
`trn_arkaaim_begbal`) are working databases whose labels may not be what you
want end users to read.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ODOO_FRONT_URL` | `http://odoo-front:8069` | The multi-DB Odoo (`LIST_DB=False`, `DBFILTER=^.*$`) |
| `TENANTS_CONFIG_PATH` | `/app/config/tenants.json` | Allow-list location |
| `ODOO_TIMEOUT_MS` | `10000` | Bootstrap request timeout |
| `COOKIE_SECURE` | `true` | Set to `false` only for a plain-http dev run |

## Local run

```bash
npm install
TENANTS_CONFIG_PATH=$PWD/config/tenants.json \
ODOO_FRONT_URL=http://127.0.0.1:18079 \
COOKIE_SECURE=false \
npm run dev            # http://localhost:8080/signin
```
