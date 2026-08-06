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

## Still open — measured and decided 6-Aug-2026

Each item below was re-measured on 6-Aug-2026 and put to the owner. Two turned out
to be largely done already; four are decisions, not work, and the decision is
recorded with each. Nothing on this list can be closed from inside this repo alone.

1. **The origin is reachable directly, so Cloudflare can be bypassed.**
   *Confirmed still true.* Caddy's own access log shows the socket source address
   is preserved end to end (`remote_ip` is a real Cloudflare edge, e.g.
   `172.69.89.166`, while `client_ip` is the visitor), so source-address filtering
   on this host would work — the upstream NAT does not rewrite it.

   **Decision: prepared, deliberately not enabled.** `scripts/security/origin_lockdown.sh`
   builds the rules and prints them; nothing happens without `--apply`:
   ```bash
   ./scripts/security/origin_lockdown.sh --allow 192.168.3.0/24            # plan only
   sudo ./scripts/security/origin_lockdown.sh --apply --allow 192.168.3.0/24 --trial 300
   sudo ./scripts/security/origin_lockdown.sh --commit                     # within 300s, or it self-reverts
   sudo ./scripts/security/origin_lockdown.sh --rollback
   ```
   It writes into `DOCKER-USER` (still empty on this box) because published ports
   are DNAT'd before `INPUT` and an `INPUT` rule would never match. The allow list
   is parsed out of the `trusted_proxies` block in `caddy/Caddyfile`, so the
   firewall and the proxy cannot disagree about who Cloudflare is. `--apply`
   accepts `RELATED,ESTABLISHED` first, arms an automatic rollback, and does not
   persist across reboot — a reboot is a rollback.

   **Order of operations matters, and getting it wrong is an outage.** Turn on
   Cloudflare Authenticated Origin Pulls at the dashboard *first*, then add the
   client-certificate check here:
   ```caddy
   # inside the eal-hub.erajaya.com site block, next to its tls directive
   tls /path/fullchain.pem /path/privkey.pem {
       client_auth {
           mode require_and_verify
           trust_pool file /etc/caddy/cloudflare-origin-pull-ca.pem
       }
   }
   ```
   (the CA is Cloudflare's public `origin-pull-ca.pem`). Enabling `client_auth`
   before AOP is on at the edge locks out every visitor immediately.

   Still true and still unaddressed: the bare-IP site block is the intended bypass,
   Caddy also publishes **8443**, and 15 other container ports are published to the
   LAN. The script prints that inventory rather than acting on it.
2. **Cloudflare WAF is not configured** — needs dashboard access nobody in this
   session had. Handover list, unchanged: Managed Rules (OWASP + Cloudflare
   rulesets), a Rate Limiting rule on `/web/login`, Bot Fight Mode, and DNSSEC.
   *Measured:* `dig DS erajaya.com` returns nothing, so **DNSSEC is confirmed off**.
3. **Phishing controls — mostly already in place, one gap left.** Measured 6-Aug:
   - SPF: present and ends in `-all` (hard fail) ✅
   - DKIM: present for both senders — `google._domainkey` and `s1._domainkey`
     (SendGrid) ✅
   - DMARC: present but **`p=none`** ❌ — it reports and enforces nothing, so a
     forged "EAL Hub" mail is still delivered. This is the whole remaining gap.

   The change is one DNS record on `_dmarc.erajaya.com`, staged so legitimate mail
   is not lost: run `p=quarantine` with `rua` reporting for two weeks, read the
   aggregate reports, then move to `p=reject`:
   ```
   v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc-alert@erajaya.com; ruf=mailto:dmarc-alert@erajaya.com; fo=1
   ```
4. **MFA is available but nobody uses it, and almost everyone is an admin.**
   Measured 6-Aug across the production databases:

   | database | TOTP enrolled | holds Settings (`base.group_system`) |
   |---|---|---|
   | `prd_levis_begbal` | 0 of 73 | **73 of 73** |
   | `prd_levis_AP` | 0 of 34 | 33 of 34 |
   | `prd_detail_levis` | 0 of 27 | 27 of 27 |
   | `prd_levis` | 0 of 65 | 28 of 65 |
   | `prd_arkaaim` | 0 of 28 | 14 of 28 |

   `auth_totp`, `auth_totp_mail` and `auth_totp_portal` are installed everywhere —
   the capability is there, unused. Note Odoo 19 CE has **no** `totp_policy` column
   on `res.company`, so enforcing 2FA is not a settings toggle; it needs a small
   module that refuses a privileged login without it.

   The admin figure is the sharper half: with `base.group_system` a user can write
   `ir.ui.view`, which is code execution in every other user's browser, so on three
   of these databases every account is effectively a superuser.

   **Decision: deferred by the owner, 6-Aug-2026.** Recorded here rather than acted
   on because both halves (enrolment rollout, revoking Settings per name) interrupt
   people mid-work.
5. **File Browser (`/files`) is public.** **Decision: left as is, 6-Aug-2026** —
   login gate plus the WAF, the scanner refusal and the rate limit are accepted as
   sufficient for now. The upgrade path if that changes is Cloudflare Access (edge
   SSO, no IP list to maintain) or an allowlist in the Caddyfile.
6. **`/web/database/*` on the bare-IP host** reaches `odoo-mgmt`: the cross-tenant
   database manager, held back by the master password alone. *Measured:* it is
   **actively used**, not a leftover — `odoo-mgmt` logged a `Database.backup` of
   `prd_wms` on 5-Aug-2026, plus regular selector renders.

   **Decision: left as is, 6-Aug-2026**, same as the original explicit request. It
   remains the largest single item on this list: one master password stands between
   any visitor to the bare IP and every tenant's data. If it is ever closed, the
   replacement is already running — `pg_dump` of every database nightly at 02:30
   with 14/8/6 rotation — and ad-hoc backups move to the CLI.

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
