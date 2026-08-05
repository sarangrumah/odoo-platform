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

## Public vs internal environments

A target with `"visibility": "internal"` is **absent** from the chooser — not
greyed out, not disabled: absent. A vertical whose targets are all internal
disappears entirely, so the page does not even name the project. `resolveDb()`
refuses internal pairs too, so a hand-crafted POST gets the same "not available"
as a nonexistent one.

Today that leaves clients seeing three entries: Levi's Production, ARKA-AIM
Production, ARKA-AIM Training. Everything else — working copies (`prd_levis_AP`,
`prd_detail_levis`, `prd_levis`), R&D, demo builds, the WMS and Gentle Woman
builds that have no live users yet — is internal.

To see them, open **`/signin?staff=<STAFF_KEY>`** once. The key is validated
server-side, exchanged for a 12-hour cookie, and stripped from the URL
immediately so it does not linger in history or a `Referer`. The header then
reads "mode staf" and internal entries are marked `· internal`.

`STAFF_KEY` unset = the unlock is off and internal entries are hidden from
everyone, us included. It fails closed.

This gate is a convenience on a *listing*, not an authorisation boundary — the
real one is Odoo asking for a password on the next page. Its job is to keep our
internal database inventory out of a client's view.

## Adding or removing an environment

Edit `config/tenants.json`:

```json
{ "code": "training", "label": "Training", "db": "trn_arkaaim" }
{ "code": "rnd", "label": "R&D", "db": "rnd_levis", "visibility": "internal" }
```

`visibility` defaults to `"public"` when omitted. A typo in it is a hard error
rather than a silent fallback — falling back to public would publish exactly
what the line was meant to hide.

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
| `VERSIONS_CONFIG_PATH` | `/app/config/versions.json` | Data behind `/signin/versi` (see below) |
| `ODOO_TIMEOUT_MS` | `10000` | Bootstrap request timeout |
| `STAFF_KEY` | *(unset)* | Unlocks internal entries at `/signin?staff=<key>`; unset = hidden from everyone |
| `COOKIE_SECURE` | `true` | Set to `false` only for a plain-http dev run |

## Branding

`public/brand/` holds the lockup used on the chooser and the version page.

| File | What it is |
|---|---|
| `eal-logo.png` | The official Erajaya Active Lifestyle artwork, white field knocked out, trimmed, downscaled to 900px |
| `eal-logo-dark.png` | Same artwork with the neutral inks lifted to near-white; the red/blue swoosh is untouched |
| `favicon.svg` | The swoosh alone on a dark plate, drawn to stay legible at 16px |

Two files rather than one because the official wordmark is **black** — it
disappears on anything dark, and CSS cannot recolour a raster. Which one is used
is decided per placement, not per theme: the brand panel is always dark so it
always takes the dark variant, while the compact lockup swaps with
`prefers-color-scheme` (in CSS, so there is no flash of the wrong logo).

The Odoo wordmark is `src/app/odoo-mark.tsx`, drawn as an inline SVG rather than
a file in `public/` so it can take its colour from `currentColor` and lighten in
dark mode. An `<img src="…svg">` cannot.

Source artwork:
<https://www.erajaya.com/files/uploads/newseventattachment/uri/2022/Jan/18/61e6765517991/erajaya-active-lifestyle-fa-logo-latar-putih.png>

Anything referenced out of `public/` must go through `asset()` in `src/lib/url.ts`.
Next prepends `basePath` to routes and static *imports* but not to a plain string
in `<img src>`, so a bare `/brand/eal-logo.png` 404s.

**Changing a brand file needs an image rebuild** — only `config/` is
bind-mounted; `public/` is baked in.

## Version page (`/signin/versi`)

Publicly linked from the chooser's footer. Shows the Odoo Community version
(with the base-image digest pin), PostgreSQL, Python, and every custom addon
with its manifest version and, for staff, the commits that touched it.

The data is a generated file, not a live query — the gateway sits in front of
the login and has no business opening a database connection:

```bash
python3 scripts/gen_module_versions.py        # writes login-gateway/config/versions.json
docker compose restart login-gateway          # optional: the file is re-read per request
```

`config/` is bind-mounted read-only, so refreshing the page's data never needs
an image rebuild — same mechanism as `tenants.json`. CI keeps the file honest:
`.github/workflows/check-module-versions.yml` runs the generator with `--check`
on any PR that touches a manifest, and fails if the committed file no longer
matches. The check deliberately ignores the git-derived fields, which move on
every commit and would make it unsatisfiable.

### What the public view withholds

Two things, and the second is the non-obvious one:

1. modules in the `_tenants` bucket, whose names identify a client, and
2. **every commit subject, on every module.**

(2) is not paranoia. Commit messages on entirely generic modules read
`feat(arkaaim): …`, `feat: Gentlewoman headless storefront`,
`fix(lint): restore the warehouse-jds ruff ignore` — publishing the changelog
would hand out exactly the client list that (1) and `tenants.json` go to some
trouble to withhold. Redacting names from free text would mean maintaining a
deny-list and being wrong the first time someone writes a new client's name, so
the public view drops the subjects and shows the shape of the history instead:
when the module last changed, and how many commits it has. The staff cookie
(`/signin?staff=<key>`) reveals both.

To publish the subjects anyway, return `m.changes` unconditionally in
`publicVersions()` (`src/lib/versions.ts`).

## Local run

```bash
npm install
TENANTS_CONFIG_PATH=$PWD/config/tenants.json \
VERSIONS_CONFIG_PATH=$PWD/config/versions.json \
ODOO_FRONT_URL=http://127.0.0.1:18079 \
COOKIE_SECURE=false \
npm run dev            # http://localhost:8080/signin
```

Note that `next dev` streams source frames for server-side file reads, so the
dev server's HTML contains the raw text of `tenants.json`, database names and
all. That is a dev-mode artefact — the production build does not. Do the leak
check against the built server:

```bash
npm run build
cp -r public .next/standalone/public && cp -r .next/static .next/standalone/.next/static
node .next/standalone/server.js
curl -sL http://127.0.0.1:8080/signin/ | grep -E 'prd_|rnd_|demo_|trn_'   # must be empty
```
