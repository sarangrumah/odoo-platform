# Front-door hardening — eal-hub.erajaya.com

What protects the live domain, how to verify it, how to roll it back, and what is
still missing. Written 2026-08-06 alongside the change that put it in place.

## Why the front door needed its own controls

`eal-hub.erajaya.com` reaches Odoo through **Caddy only** — the internal nginx hop
is not on that path (`caddy/Caddyfile`, the `reverse_proxy odoo-front` comment).
Every protection written in `nginx/conf.d/odoo.conf` — the login rate limit, the
security headers, the CSP, the `/web/database/*` deny — therefore applied to
nothing that a real visitor touches. The `nginx/modsecurity/` stub was inert for a
second reason on top of that: the `nginx:1.27-alpine` image has no ModSecurity
connector.

Measured state before the change, against the live origin:

| probe | answer before | why it mattered |
|---|---|---|
| `GET /web/login` | `server: Werkzeug/3.0.1 Python/3.12.3` | exact version handed to any scanner |
| `GET /web/login` | no HSTS, no CSP, no `X-Frame-Options` | login page framable → credential harvesting overlay |
| `GET /files/xx.php` | **200** + the File Browser SPA | any junk path answered 200; hundreds of webshell probes a day, all encouraged |
| `GET /.env` | 404 (Odoo's) | reached the application |
| direct hit on the origin IP | served | Cloudflare's WAF bypassable — probes observed from `139.5.151.45`, not a CF range |

## What is in place now

Layer 1 — `caddy/Caddyfile` (commit "security headers, real client IP and scanner refusal"):

- **Security headers** on every front-door response: HSTS 1 year with
  `includeSubDomains`, `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, and a narrow CSP (`frame-ancestors 'self';
  object-src 'none'; base-uri 'self'`). `Server` and `X-Powered-By` are stripped.
  The CSP is deliberately not a `script-src` policy — Odoo's web client needs
  `unsafe-inline unsafe-eval`, so such a directive would grant everything it
  forbids while risking a white-screen backoffice.
- **Real client IP.** The Cloudflare ranges are declared as `trusted_proxies` and
  `CF-Connecting-IP` is honoured only from them, so `{client_ip}` is the visitor
  and a forged header from anywhere else is ignored (verified: a request carrying
  `CF-Connecting-IP: 1.2.3.4` from an untrusted peer logs `client_ip` as the socket
  address). Both proxies forward a single-valued `X-Forwarded-For` so werkzeug's
  `ProxyFix` cannot pick the wrong entry.
- **Scanner refusal** ahead of every application route: PHP paths, dotfiles, WP,
  phpMyAdmin, phpunit, actuator, and friends — case-insensitively and at any depth,
  because the probes were hitting `/files/vendor/phpunit/phpunit`, not the root.
- **`/xmlrpc` and `/jsonrpc` closed** with 403. They are Odoo's session-less,
  CSRF-free credential surface; the whole access log held one hit and it was a
  scanner. Machine clients that need RPC get a tenant hostname instead.
- **200 MB request body cap** (the same ceiling nginx allowed, so imports still work).
- **`/web/webclient/version_info` answered by Caddy** with an empty result. The
  route is `auth="none"` in Odoo, so before this any anonymous POST got
  `19.0-20260528` back — the same disclosure the `Server` header was stripped for,
  and it survived that stripping. It is answered rather than refused because the
  web client polls it to detect that a lost connection is back
  (`error_handlers.js`) and after a restart (`home` client action); both ignore the
  payload and only branch on success, so a 403 would pin "Connection lost. Trying
  to reconnect…" on screen. Authenticated clients still read the version from
  `session_info`. Verify: `curl -sX POST -d '{}' -H 'Content-Type: application/json'
  https://eal-hub.erajaya.com/web/webclient/version_info` → `"result":{}`.

Layer 2 — `caddy/Dockerfile` + `caddy/coraza/*` (commit "OWASP CRS WAF and per-IP rate limits"):

- **Coraza WAF with OWASP CRS 4.28.0** at paranoia 1, anomaly threshold 5. Blocks
  SQLi (incl. inside JSON bodies), XSS, RCE, traversal/LFI, protocol abuse, scanner
  fingerprints. Engine mode is `WAF_MODE` — see the rollout section below.
- **Rate limits per real client IP**: 12 POSTs/minute across every credential path
  (`/web/login`, `/web/session/authenticate`, `/web/reset_password`, `/signin`),
  3000/minute for everything else. The general limit is loose on purpose: whole
  stores share one NAT address.
- The image pins Caddy 2.11.3, both modules, and checksum-verifies the CRS tarball;
  the build fails if either module is absent.

## Rollout status and the flip to blocking

**Live is running `WAF_MODE=DetectionOnly` as of 2026-08-06 07:05 WIB.** Everything
in Layer 1 is enforcing; the WAF evaluates and logs but does not block.

That is deliberate. Within minutes of deploying in detection mode, real traffic
surfaced a false positive that would have broken the login flow itself: a
successful tenant-chooser login (`POST /signin`, 303 with a session cookie) scored
10 on CRS 922130 "Multipart header contains characters outside of valid range",
because of how React server actions encode multipart part names. It is excluded now
(`caddy/coraza/exclusions.conf`, rule 1000103), scoped to that one rule id on
`/signin` and `/vaspmo`.

Before flipping to blocking, run a monitoring window that includes the flows a
morning of testing does not: month-end reporting, a `base_import` run, a File
Browser upload, an e-Faktur/Coretax export, and the WMS handheld.

```bash
# 1. triage — the first section must be empty of real user traffic
scripts/security/waf_triage.sh

# 2. flip
echo 'WAF_MODE=On' >> /opt/odoo-platform/.env
cd /opt/odoo-platform && docker compose \
  -f docker-compose.yml -f docker-compose.multitenant.yml \
  up -d --force-recreate --no-deps caddy

# 3. prove both directions: attacks blocked, real ORM traffic not
scripts/security/verify_front_door.sh
```

Rollback is the same three steps with `WAF_MODE=DetectionOnly`. It takes about ten
seconds of ingress downtime, which is what a container recreate costs here.

## Verification

`scripts/security/verify_front_door.sh` is the regression test for all of this. It
asserts the hardening AND that nothing legitimate regressed, and it encodes two
traps that have produced false "all healthy" results on this host:

- `curl https://127.0.0.1/` sends the wrong `Host`, matches no site block, and gets
  an **empty 200** logged as `NOP`. Always `--resolve` the real hostname.
- a dead site still answers 200, so every check asserts on **body size** too.

It also runs the WAF matrix: SQLi in a query string, in an auth body and in a
`call_kw` body must be refused; a realistic nested ORM domain (100+ arguments once
flattened, containing the literal strings `select * from` and `DROP` as field
values) must NOT be. That last case is the one that catches over-eager tuning.

## Performance, stated plainly

WAF cost is roughly **0.8 ms per request argument plus 10 µs per byte** inside a
single large one, because every rule evaluates against every argument. Odoo's RPC
bodies are the worst possible shape for that.

| request shape | no WAF | full CRS | as configured |
|---|---|---|---|
| GET, no body | 21 ms | 24 ms | 24 ms |
| JSON POST, 3 args | 22 ms | 28 ms | 28 ms |
| JSON POST, 100 args | 23 ms | 110 ms | 47 ms |
| JSON POST, 260 KB base64 | 22 ms | 2723 ms | 25 ms |
| real Odoo RPC end to end | 94 ms | — | 109 ms |

Two scoped reductions get it there, both documented at the rule in
`caddy/coraza/exclusions.conf`: bodies over 64 KB are not inspected (they are
files, and no rule can say anything useful about compressed bytes), and on
`/web/dataset/*` only the SQLi family evaluates. The residual risk of the second —
stored XSS through an authenticated ORM write is not inspected — is stated there
too. Deleting rule 1000111 restores full inspection at ~85 ms per RPC.

## Still open — these need access this change did not have

1. **The origin is reachable directly, so Cloudflare can be bypassed.** Probes were
   observed arriving from non-Cloudflare addresses. Until the origin only accepts
   Cloudflare, every control that lives at the Cloudflare edge is optional from an
   attacker's point of view. Two ways, best done together:
   - Cloudflare **Authenticated Origin Pulls** (client-certificate on the CF→origin
     hop) plus `tls client_auth` in the `eal-hub.erajaya.com` site block.
   - Host firewall: allow 443/tcp only from the 22 Cloudflare ranges already listed
     in `caddy/Caddyfile`. Note this box's `DOCKER-USER` chain is **empty** and 15
     container ports are published to the LAN, so a firewall change here needs to
     be planned against that inventory rather than dropped in.
   The legacy bare-IP site block would have to go first, or be restricted to the
   office range — it is the intended bypass today.
2. **Cloudflare WAF is not configured** (dashboard access needed): enable Managed
   Rules (OWASP + Cloudflare rulesets), a Rate Limiting rule on `/web/login`, Bot
   Fight Mode, and turn on DNSSEC for `erajaya.com`. This is the cheap layer that
   stops volumetric traffic before it costs origin CPU.
3. **Phishing controls are DNS-side, not server-side** — nothing in this repo can
   set them: SPF, DKIM and a `p=reject` DMARC policy on the sending domain, so a
   forged "EAL Hub" mail cannot be delivered. The login page hardening here only
   stops the *framing* half of a phishing flow.
4. **MFA is not enforced in Odoo.** The rate limit makes credential stuffing slow;
   only TOTP (`auth_totp`) plus a password policy makes a leaked password
   insufficient. Worth pairing with a review of who holds Settings access, since
   `ir.ui.view` write is equivalent to code execution in every user's browser.
5. **File Browser (`/files`) is public.** It is login-gated, but it is the drop zone
   for client spreadsheets and it is what the webshell scanners are aiming at. It
   deserves either Cloudflare Access in front of it or an IP allowlist.
6. **`/web/database/*` on the bare-IP host** reaches `odoo-mgmt` per an earlier
   deliberate decision (see `caddy-recreate-overlay-drift` notes): the cross-tenant
   database manager, held back by the master password alone. Unchanged here because
   it was an explicit request, but it is the largest single item on this list.

## Maintenance

- **Cloudflare ranges** drift. `scripts/security/refresh_cloudflare_ranges.sh`
  diffs them and exits 1 when the Caddyfile is stale (`--write` to apply). A stale
  list never blocks traffic — those requests just fall back to the edge IP.
- **The Caddy binary is ours now, so its CVEs are ours.** The image is in CI's
  `container-scan` matrix (trivy, HIGH/CRITICAL, `--ignore-unfixed`), because the
  first build of it shipped 20 such findings: Caddy 2.11.3 itself (2, fixed in
  2.11.4), `x/crypto` (9), `x/net` (3), `x/text`, `grpc`, `go-jose` and the Go
  stdlib. That is why the build is a plain `go build` over `caddy/main.go` and an
  explicit `go.mod` rather than `xcaddy build`: xcaddy resolves whatever the pinned
  Caddy's `go.mod` asks for and gives no lever to raise a *transitive* module. The
  third `go get` group in the Dockerfile is that lever — remove an entry only after
  upstream has caught up, or the CVE comes back silently. `apk upgrade` in the
  runtime stage covers the same problem for the base image's Alpine packages.
- **CRS bumps**: change `CRS_VERSION` and `CRS_SHA256` in `caddy/Dockerfile`
  together, rebuild, run the verify script in DetectionOnly first. Our tuning lives
  in `crs-tuning.conf` and is included *after* the shipped `crs-setup.conf`, so a
  bump cannot silently drop it.
- **Editing the Caddyfile**: it is a single-file bind mount, so any edit that
  replaces the inode leaves the container reading the old file while
  `caddy reload` reports success. Either write in place (`cat new > path`) and
  reload, or recreate the container. Check with:
  ```bash
  stat -c %i /opt/odoo-platform/caddy/Caddyfile
  docker exec odoo19-platform-caddy stat -c %i /etc/caddy/Caddyfile   # must match
  ```
  `caddy/coraza/` is a *directory* mount, so rule edits there only need a reload.
- **Before recreating caddy**, compare the running container against the overlay
  (`docker inspect ... com.docker.compose.project.config_files`): a recreate uses
  today's definition, and this container has been bitten by mount/DOMAIN/8443 drift
  before.
