# Nginx + ModSecurity (opt-in WAF)

This directory ships a **stub configuration** for ModSecurity v3 with the
OWASP Core Rule Set (CRS). The default `nginx` image used by the prod
override does **not** include the `modsecurity-nginx` connector, so the
files here are inert unless you:

1. Build a custom nginx image with the connector.
2. Uncomment the `modsecurity` directives in `nginx/conf.d/odoo.conf`.

Defense-in-depth: HMAC + rate limiting + CSP are already enforced by
the base config. ModSecurity is an extra layer for OWASP Top-10 / known
attack signatures.

## Files

| File | Purpose |
|------|---------|
| `main.conf` | Engine settings, body limits, audit log config. |
| `crs-setup.conf` | Paranoia level + anomaly thresholds for OWASP CRS. |

## Enabling locally

### Option A — Use the official ModSecurity nginx image

In `docker-compose.prod.yml`, replace the nginx image:

```yaml
nginx:
  image: owasp/modsecurity-crs:nginx-alpine
```

That image bundles CRS at `/etc/modsecurity.d/owasp-crs/`. Adjust the
include paths in `main.conf` accordingly.

### Option B — Build your own

```dockerfile
FROM nginx:1.27-alpine
RUN apk add --no-cache git build-base autoconf automake libtool pcre-dev \
    libxml2-dev curl-dev yajl-dev \
 && git clone --depth 1 -b v3.0.13 https://github.com/SpiderLabs/ModSecurity /tmp/ms \
 && cd /tmp/ms && git submodule update --init && ./build.sh && ./configure && make install \
 && git clone --depth 1 -b v1.0.3 https://github.com/SpiderLabs/ModSecurity-nginx /tmp/msn \
 # ... rebuild nginx with --add-dynamic-module=/tmp/msn ...
```

Then:

```dockerfile
RUN git clone --depth 1 -b v4.10.0 https://github.com/coreruleset/coreruleset \
    /etc/nginx/modsecurity/coreruleset
```

### Common to both

1. Set `NGINX_WAF_ENABLE=true` in `.env`.
2. Uncomment the `modsecurity` lines in `nginx/conf.d/odoo.conf` (search for
   `# modsecurity`).
3. Restart nginx: `docker compose restart nginx`.
4. Inspect audit log: `docker compose exec nginx tail -f /var/log/modsecurity/audit.log`.

## Tuning checklist

Start at paranoia level 1 with `SecRuleEngine DetectionOnly`. Watch
`audit.log` for one week, then:

1. Build a `SecRuleRemoveById` allow-list for false positives
   (typical Odoo offenders: 920350, 942100, 949110).
2. Flip `SecRuleEngine On`.
3. Optionally raise paranoia level to 2 and repeat.

## CIS reference

CIS Docker Benchmark 5.30 — "Network firewall rules should be in place".
ModSecurity satisfies the application-layer portion of that control.
