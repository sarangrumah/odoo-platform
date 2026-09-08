# Levi's Sales Cockpit

An interactive sales dashboard over `prd_levis_begbal`, built for a director-level
demo. Next.js 15 App Router, React server components, Recharts, and plain SQL
against a read-only Postgres role.

Current state: **fast path** — Ringkasan, Toko, Produk, Associate, Kualitas Data,
packaged as a compose service behind Caddy at `/cockpit`.
Not yet built: Diskon & Promo, Membership, Transaction Explorer, and login —
see [Before this is exposed](#before-this-is-exposed).

## What the data actually supports

There are no `sale_order` and no customer invoices in this database. Every sale
lives in `pos_order` / `pos_order_line`, loaded by the retail-import feed.
As of 2026-08-14, unfiltered:

| | |
|---|---|
| Window | 12 Jun 2026 – 9 Aug 2026 |
| Orders / lines | 19.268 / 52.581 |
| Gross | Rp 27.923.625.458 |
| Units | 57.434 |
| Stores | 23 configured, 22 selling |
| Associates | 72 named (2 lines carry no name, bucketed as "tanpa nama") |
| Member transactions | 16.602 (86,2%) |
| Discounted transactions | 8.582 (44,5%) |

Three questions this dashboard deliberately refuses to answer, each surfaced on
the **Kualitas Data** page rather than hidden:

1. **Gross margin.** `total_cost` is 0 on all 52.581 lines and no `levis.cogs.run`
   has been posted, so there is no cost side. Nothing here estimates it.
2. **Payment tender split.** Every payment sits on a single method named
   SUSPENSE. Cash-versus-card belongs to bank reconciliation, not to POS.
3. **Discount amounts.** `SUM(price_unit * qty)` equals gross to the rupiah, so
   imported prices are already net of discount. Only the discount *type* flag
   survives, so the dashboard reports the share of discounted transactions.

What it does support is a claim worth making to a director: POS revenue
excluding tax reconciles to posted GL income at **Rp 0 for every month** in the
window. That check runs live on the Kualitas Data page.

## Database access

The app logs in as `cockpit_ro`, created by `sql/001_cockpit_ro_role.sql`:

- `LOGIN`, no superuser, no createdb, no createrole
- `default_transaction_read_only = on` — `UPDATE` and `CREATE TABLE` are refused
  by the server, not by application code
- `SELECT` on seventeen named tables; `res_users` is **not** among them
- `statement_timeout = 30s`

Applying it (idempotent, run both halves):

```bash
docker cp sql/001_cockpit_ro_role.sql odoo19-platform-postgres:/tmp/
docker exec -e PGPASSWORD="$PGPASS" odoo19-platform-postgres \
  psql -U odoo -d postgres -v cockpit_password="$COCKPIT_PASS" -f /tmp/001_cockpit_ro_role.sql
docker exec -e PGPASSWORD="$PGPASS" odoo19-platform-postgres \
  psql -U odoo -d prd_levis_begbal -f /tmp/001_cockpit_ro_role.sql
```

### One manual step: pg_hba

`pg_hba.conf` on this platform is a per-user allowlist ending in an explicit
`reject`, so a new role cannot connect until it is named there. Add to
`/opt/odoo-platform/postgres/pg_hba.conf` (and keep the `/home` copy in sync),
**above** the two `reject` lines:

```
host    prd_levis_begbal  cockpit_ro    172.16.0.0/12           scram-sha-256
host    prd_levis_begbal  cockpit_ro    192.168.0.0/16          scram-sha-256
host    prd_levis_begbal  cockpit_ro    10.0.0.0/8              scram-sha-256
```

Scoping the database column to `prd_levis_begbal` is the isolation boundary: the
role can log in over the socket to other databases (Postgres grants `CONNECT` to
`PUBLIC` by default) but has `SELECT` on nothing there, and over TCP it cannot
reach them at all.

Then reload — a reload, not a restart, so no session is dropped:

```bash
docker exec odoo19-platform-postgres psql -U postgres -c "SELECT pg_reload_conf();"
```

Edit the file in place rather than replacing it: it is bind-mounted as a single
file, and a new inode silently detaches the mount.

## Running it

Postgres does not publish a host port, so the dev server has to sit on the
docker network:

```bash
docker run --rm -it \
  --name cockpit-dev \
  --network odoo19-platform-net \
  -p 18130:8080 \
  -v "$PWD":/app -w /app \
  -e COCKPIT_DB_PASSWORD='…' \
  -e HOSTNAME=0.0.0.0 \
  node:20-alpine npm run dev
```

Then open <http://localhost:18130/cockpit/overview>.

Health check, which round-trips to the database rather than just answering 200:
<http://localhost:18130/cockpit/api/health>.

## Deploying

The compose service is `sales-cockpit` in `docker-compose.yml`, built from this
directory: non-root, `read_only: true` with tmpfs for `/tmp` and the Next cache,
all capabilities dropped, 512m, published on **`127.0.0.1:18130` only** — with no
authentication yet, a `0.0.0.0` binding would hand every store's revenue to
anything on the LAN. Reach it over an SSH tunnel, the way `odoo-mgmt` is reached.
Caddy routes it with

```
handle /cockpit* {
    reverse_proxy sales-cockpit:8080
}
```

`handle`, not `handle_path`: `basePath=/cockpit` means the app expects to see the
prefix. One matcher per `handle` block — two makes the ingress crash-loop.

```bash
docker compose build sales-cockpit
docker compose up -d sales-cockpit
curl -s localhost:18130/cockpit/api/health
```

The credential lives in `.env` as `COCKPIT_DB_PASSWORD` (gitignored). The runtime
compose project reads `/opt/odoo-platform/.env`, so the variable has to exist
there too, and the Caddyfile edit has to reach `/opt/odoo-platform/caddy/` — this
repo's copies under `/home` are the source, not what the running containers
mount.

The container starts whether or not the pg_hba entries exist; without them
`/cockpit/api/health` answers 503 with the connection error, which is the
intended failure mode rather than a blank dashboard.

### The public route is loaded at runtime, not from disk (14-Aug-2026)

`/cockpit` is live at `https://eal-hub.erajaya.com/cockpit/overview`. It was
applied with

```bash
docker cp caddy/Caddyfile odoo19-platform-caddy:/tmp/Caddyfile.new
docker exec odoo19-platform-caddy caddy reload --adapter caddyfile --config /tmp/Caddyfile.new
```

because `/opt/odoo-platform/caddy/Caddyfile` could not be written from this
session, and the container's mount of it is `ro` so it cannot be written from
inside either.

**This does not survive a Caddy restart.** On start Caddy reads
`/etc/caddy/Caddyfile`, i.e. the unmodified `/opt` copy, and `/cockpit` goes back
to 404 while every other route is unaffected. To make it permanent, copy the file
in and reload — `cat`, not `mv` or `install`, so the single-file bind mount keeps
its inode:

```bash
cd /home/odoo-erp/odoo-platform/caddy
cat Caddyfile > /opt/odoo-platform/caddy/Caddyfile
docker exec odoo19-platform-caddy caddy reload --config /etc/caddy/Caddyfile
```

Verified before applying: `diff /opt/.../Caddyfile /home/.../Caddyfile` showed the
`/cockpit` block and nothing else, so the reload carried no unrelated drift into
production ingress.

## Authentication

Login is Odoo's own. `src/lib/auth.ts` posts the credentials to
`/web/session/authenticate` on **`odoo-front`** — the public `odoo` runs
dbfilter `^%d$` and answers "Database not found" for this tenant, the same
reason the login gateway targets odoo-front. The app never sees a password hash
and keeps no user table.

On success it reads `res.users.share` with the freshly minted Odoo session and
rejects portal/public accounts, then mints its own HMAC-SHA256 signed cookie
(`cockpit_session`, httpOnly, SameSite=Lax, Secure in production, 12h) and
throws Odoo's session away — the dashboard reads Postgres directly and has no
further use for it.

- `COCKPIT_SESSION_SECRET` must be ≥32 chars or session handling throws. There is
  no default on purpose: one would let anyone who read this file forge a cookie.
- `src/middleware.ts` checks only that the cookie is *present* — the edge runtime
  has no `node:crypto`. The real gate is `getSession()` in `src/app/(app)/layout.tsx`,
  which verifies the signature and expiry before any page renders.
- Five failed attempts per login triggers a 5-minute lockout, held in memory.
- Wrong password and unknown user return the same message, so the form does not
  confirm which logins exist.
- `/cockpit/api/health` is the only public route; it answers `SELECT 1` and
  reports no business figures, because the container healthcheck calls it
  unauthenticated.

Verified 14-Aug-2026: anonymous → 307 to `/login?next=…`; a valid signed cookie
renders the pages; a cookie with one character changed → 307 to login; an expired
cookie → 307 to login. A successful round trip with real Odoo credentials has
**not** been exercised — no test account was created on production for it.

## How it is put together

```
src/lib/db.ts              pg pool; logs any query over 300ms
src/lib/filters.ts         URL search params -> a SQL scope; the alias contract
src/lib/queries/sales.ts   every number the UI shows, one function per question
src/lib/format.ts          Indonesian number and rupiah formatting
src/components/            filter bar, nav, charts, KPI tile, theme toggle
src/app/(app)/             the five pages

src/lib/agent/skills.ts    the assistant's skill catalogue — the ONLY door to data
src/lib/agent/intent.ts    weighted keyword matcher; refuses rather than guesses
src/lib/agent/slots.ts     dates/stores/categories out of a sentence, no model
src/lib/agent/answer.ts    orchestrator: refuse -> match -> run -> escalate
src/components/agent/       floating Lottie mascot and its panel
src/app/api/agent/          the widget's endpoint, and the sidecar's callback
```

Filter state lives in the URL, never in React state, so every view is a
shareable link — during a demo "send me that screen" is the most common request.
Aggregates are built on the line grain and count transactions with
`COUNT(DISTINCT o.id)`; summing `price_subtotal_incl` over that join reproduces
`SUM(pos_order.amount_total)` exactly, so nothing is lost.

Charts follow the `dataviz` skill: a validated categorical palette (slots
assigned by entity, never by rank), no dual axes anywhere, a shared y-domain
across small multiples, and a table beside every chart — three light-mode slots
fall below 3:1 contrast, which obliges that relief.

## The assistant

A Lottie mascot floats on every page (`src/components/agent/agent-widget.tsx`,
mounted once in `src/app/(app)/layout.tsx`). Ask it a question in Indonesian and
it answers with the figure, a small table, and a link back into the dashboard
carrying the same filters.

Questions are answered in three steps, and the first two involve no model at all:

1. **Refuse what the data cannot carry.** `detectUnanswerable()` catches margin,
   tender split, stock, payroll, and target questions by name and says exactly
   why prd_levis_begbal cannot answer them. This runs *first* — "berapa margin
   bulan lalu" also contains "bulan lalu" and "berapa", and would otherwise
   score as a KPI question and return an omzet figure to somebody who asked
   about profit.
2. **Match the catalogue.** `intent.ts` scores the sentence against eleven
   skills, each wrapping a function that already existed in `queries/`. Slots
   (period, store, category, membership, limit) come out of `slots.ts` and are
   folded onto whatever the filter bar already has, so "produk terlaris"
   respects the range on screen. The threshold is strict on purpose: an
   ambiguous sentence scores itself out rather than answer confidently.
3. **Escalate, if configured.** Anything left goes to `cockpit-agent`, whose
   only tools are those same eleven skills.

Everything up to step 3 runs with no API key, no per-question cost, and the same
answer every time. Set nothing and the widget is still fully useful.

Date phrases anchor to the **last day with data**, never to the wall clock: the
retail-import feed runs behind, so "hari ini" asked on 20 August against data
ending 19 August means 19 August. A period entirely outside the data ("penjualan
januari") is told so rather than silently answered from the filter bar.

```bash
npm run test          # 32 unit tests: date phrases, matching, refusals
npm run test:smoke    # runs all 11 skills against prd_levis_begbal (needs the DB)
npm run mascot        # regenerate public/mascot/mascot.json
```

The mascot ships as a generated placeholder (`scripts/gen_mascot.py`, four
segments on one 240-frame timeline: idle / listening / thinking / talking).
Swapping in a designer's Lottie means replacing `public/mascot/mascot.json` and
nothing else, as long as it keeps those frame ranges.

`console.info` logs one JSON line per question with the chosen skill and source.
A question that keeps landing on `source: "unmatched"` is the next skill worth
writing deterministically — that log is the backlog.

## Verification

Numbers were checked against SQL run directly as `cockpit_ro`. Re-run after any
change to `queries/sales.ts`:

```bash
docker exec -e PGPASSWORD='…' odoo19-platform-postgres \
  psql -U cockpit_ro -d prd_levis_begbal -tAF'|' -c "
SELECT COUNT(DISTINCT o.id), round(SUM(l.price_subtotal_incl)), round(SUM(l.qty))
FROM pos_order_line l JOIN pos_order o ON o.id=l.order_id;"
# expect: 19268|27923625458|57434
```

## Demo run, five minutes

1. **Kualitas Data first.** Open with the Rp 0 reconciliation on screen and say
   what the dashboard will not claim. Credibility is cheaper to establish before
   the numbers than after.
2. **Ringkasan, full window.** Rp 27,9 M, 19.268 transaksi, ATV Rp 1,45 jt.
   Switch the preset to 30 hari and let the deltas move.
3. **Toko.** Grand Indonesia leads at Rp 4,19 M. Point out Pacific Place with
   zero transactions — the row a `GROUP BY` would have dropped.
4. **Click Grand Indonesia.** The filter chip appears; navigate to Produk and
   Associate with it still applied. Copy the URL and note that it is shareable.
5. **Produk.** Click MENS BOTTOMS to drill into sub-categories, then scroll to
   the 50-product table and the "sold in how many stores" column.
6. Close back on the margin gap: the one number a director will ask for that
   this data cannot yet give, and what would need to be posted to change that.
