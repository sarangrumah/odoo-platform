# TLS Renewal — Caddy ACME Runbook

This runbook covers the Caddy-fronted TLS terminator introduced by the
`docker-compose.tls-acme.yml` overlay. Caddy auto-issues and auto-renews
certificates via ACME (Let's Encrypt by default). No cron, no certbot.

## Topology

```
Internet ──► Caddy (host :80, :443)  ──► nginx:80 (rate-limit + WAF)
              │     ACME + TLS                 │
              └─► /data (cert store)            └─► odoo:8069 / odoo:8072
```

* Caddy: terminates TLS, requests/renews certificates, redirects 80 -> 443.
* nginx: still does rate-limiting, login throttling, longpolling, and
  blocks `/web/database/manager`.
* Operators may keep nginx host-ports `${NGINX_HTTP_PORT:-18000}` and
  `${NGINX_HTTPS_PORT:-18443}` exposed for direct/internal access; Caddy
  uses the internal docker network and does not need them.

## Bootstrap

1. Point your A/AAAA record for `${DOMAIN}` at the host's public IP.
2. Open inbound TCP 80 and 443 (ACME HTTP-01 challenge needs port 80).
3. Set in `.env`:
   ```
   DOMAIN=erp.example.com
   ACME_EMAIL=ops@example.com
   ```
4. Start: `make up-tls`
5. Watch issuance: `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls-acme.yml logs -f caddy`

Expected log lines: `certificate obtained successfully`, `served key authentication`.

## ACME staging vs prod

Let's Encrypt **production** rate-limits aggressively (50 certs / domain /
week). When trialing DNS, firewall, or container config, switch Caddy to
**staging**:

* Easiest: bind-mount the staging variant. In an inline override, replace
  the Caddyfile mount with:
  ```yaml
  - ./caddy/Caddyfile.staging:/etc/caddy/Caddyfile:ro
  ```
* Or set `ACME_CA_DIR=https://acme-staging-v02.api.letsencrypt.org/directory`
  and uncomment the `acme_ca {$ACME_CA_DIR}` line in `caddy/Caddyfile`.

Staging certs are NOT publicly trusted; browsers will warn. That is the
intended trade-off — proves the full pipeline without burning your quota.

When ready for prod, switch the file back, **delete `./data/caddy/data`**
(or just the staging account dir under `data/caddy/data/caddy/acme/`) so
Caddy registers a fresh account against LE production, then restart.

## Auto-renewal — how to verify

Caddy renews ~30 days before expiry. To inspect:

```bash
# Show live cert metadata Caddy is serving
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls-acme.yml \
  exec caddy caddy list-certificates

# Tail renewal events
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls-acme.yml \
  logs -f caddy | grep -E 'renew|certificate|acme'

# Force-trigger a renewal (rarely needed; Caddy schedules automatically)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls-acme.yml \
  exec caddy caddy reload --config /etc/caddy/Caddyfile
```

External check from a workstation:
```bash
openssl s_client -connect ${DOMAIN}:443 -servername ${DOMAIN} </dev/null \
  | openssl x509 -noout -issuer -subject -dates
```

## Where certs live

* Mounted volume: `./data/caddy/data` -> container `/data`
* Cert + key:     `./data/caddy/data/caddy/certificates/<acme-server>/<domain>/`
* ACME account:   `./data/caddy/data/caddy/acme/<server>/users/<email>/`
* Config cache:   `./data/caddy/config` -> container `/config`

**Back this directory up** in your normal volume snapshot routine. Losing it
means Caddy re-issues on next start (fine if you are under the rate limit,
painful if not).

## Local CA mode (no public domain)

If you cannot expose port 80 or do not have a public DNS name, leave
`ACME_EMAIL` blank and edit `caddy/Caddyfile` to use `tls internal`. Caddy
then mints certs from its own local CA. Trust the root by exporting it:

```bash
docker compose -f docker-compose.tls-acme.yml exec caddy \
  cat /data/caddy/pki/authorities/local/root.crt > caddy-local-root.crt
```

Install `caddy-local-root.crt` in the OS trust store of clients that need
trusted access.

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `no such host` for ACME challenge | DNS not pointing to host | Update DNS, wait TTL |
| `connection refused on :80` from LE | firewall / NAT | Open inbound 80 (ACME HTTP-01) |
| LE `too many certificates` | hit prod rate limit | Switch to staging Caddyfile, fix, switch back |
| Browser shows "not trusted" | using `tls internal` or staging | Install local root (above) or move to prod |
| Renewal not happening | system clock skew | `timedatectl status`; ensure NTP healthy |
