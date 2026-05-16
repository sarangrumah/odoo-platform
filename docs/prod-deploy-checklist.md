# Production Deploy Checklist

Run through this list **in order** before declaring a host production-ready.
Tick each item; do not skip. Anything that fails -> stop and fix before moving on.

---

## 1. Replace every `changeme*` in `.env`

```bash
grep -nE 'changeme' .env && echo "STILL HAS PLACEHOLDERS — FIX BEFORE BOOT" || echo "OK"
```

The Odoo entrypoint fail-fasts on the literal substring `changeme`, so this is
also enforced at runtime. Required vars: `POSTGRES_PASSWORD`,
`ODOO_ADMIN_PASSWD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`,
`PGADMIN_PASSWORD`, `GATEWAY_SHARED_SECRET`, `CORETAX_SERTEL_MASTER_KEY`.

## 2. Generate gateway secret + Coretax sertel key

```bash
# AI gateway shared secret (Odoo <-> ai-gateway HMAC)
openssl rand -hex 32
# -> set GATEWAY_SHARED_SECRET in .env

# Coretax sertel master key (Fernet, 44-char base64-urlsafe)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# -> set CORETAX_SERTEL_MASTER_KEY in .env
```

**Coretax key is once-only**: rotating it requires a decrypt-all / re-encrypt
migration (see `security/policies/secret-rotation.md`).

## 3. Bootstrap certs OR set `DOMAIN` + `ACME_EMAIL`

Choose one path:

* **Static cert path** (legacy nginx-only): run `make dev-bootstrap` for a
  self-signed cert, OR drop your real cert+key at `nginx/certs/server.{crt,key}`.
* **ACME path** (recommended for internet-exposed hosts): set
  `DOMAIN=erp.example.com` and `ACME_EMAIL=ops@example.com` in `.env`. The
  Caddy overlay (`docker-compose.tls-acme.yml`) will then issue & renew
  automatically. See `docs/runbooks/tls-renewal.md`.

## 4. Configure S3 backup

In `.env` set all of: `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
`S3_BUCKET`, `S3_REGION`, `S3_PREFIX`. Leave `S3_ENDPOINT` empty for AWS,
or set it for R2 / MinIO / Wasabi. Verify the local backup target exists:

```bash
mkdir -p data/backups
```

After first `make up-prod`, trigger an immediate backup to validate creds:

```bash
make backup-now
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" \
  --endpoint-url "${S3_ENDPOINT:-https://s3.${S3_REGION}.amazonaws.com}"
```

## 5. Bring the stack up

* Without ACME (static-cert nginx):
  ```bash
  make up-prod
  ```
* With ACME (Caddy in front of nginx):
  ```bash
  make up-tls
  ```

Watch logs until all healthchecks are green:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

## 6. Install custom modules in the production DB

```bash
# Initialise the DB (one-time)
make init-db DB=prod

# Install each vertical / custom module needed
make install MODULE=custom_core    DB=prod
make install MODULE=custom_coretax DB=prod
# ...repeat for every required module
```

Verify in Odoo UI: Apps -> Search the installed module list; confirm presence
and version.

## 7. Verify Grafana dashboards

```bash
make up-obs   # ensure observability stack running
```

Open `http://<host>:${GRAFANA_PORT:-13000}` and confirm:

* "Odoo Overview" — workers, request rate, p95 latency render data
* "Postgres" — connection count, cache hit ratio, replication lag (if HA)
* "AI Gateway" — token counts, error rate
* "Capacity Predictor" — last run < `PREDICTOR_INTERVAL_HOURS` ago
* Alertmanager: `http://<host>:${ALERTMANAGER_PORT:-19093}` shows zero firing
  critical alerts.

## 8. Verify pre-commit + scans are green

```bash
make pre-commit
make scan          # trivy fs + image + gitleaks
make sast          # semgrep
```

All must exit 0. CI will block merges otherwise.

## 9. Age-key recipients added to `.sops.yaml`

Every operator with decrypt rights must contribute their **age public key**
under `creation_rules[].age`. Verify:

```bash
grep -nE 'age1' .sops.yaml
# Expect one line per operator; no `age1example...` placeholders left.
```

After updating recipients, **re-encrypt** the secrets file so the new
recipient can decrypt:

```bash
make decrypt-env       # produce .secrets.dec.yaml locally
# edit as needed
make encrypt-env       # re-encrypts for ALL current age: recipients
git add .secrets.enc.yaml && git commit -m "rotate sops recipients"
```

## 10. DBA reviewed init-load script outputs

Hand off to the DBA:

* `postgres/init/*.sql` (everything in `/docker-entrypoint-initdb.d`)
* The audit-chain bootstrap output: `make verify-audit-chain DB=prod`
* Confirm row counts and schema match staging.

The DBA must sign off in writing (ticket / email) that:

* Custom roles & GRANTs are intentional.
* `pg_hba.conf` allows only intended hosts.
* Backup retention aligns with regulatory requirement
  (`BACKUP_KEEP_DAYS`, S3 bucket lifecycle).
* `LIST_DB=false` in prod (DB manager UI is off).

---

## Post-deploy smoke (do this immediately after the checklist clears)

1. Login as admin in Odoo via the public URL. Confirm TLS issuer in the
   browser cert info matches your CA (Let's Encrypt / your internal CA).
2. Trigger a `make backup-now`; verify the new object lands in S3.
3. Browse Grafana for 5 minutes; confirm no panel shows "No data".
4. Run a representative business workflow end-to-end (invoice, login,
   AI gateway request) and watch nginx access log + Loki for errors.
