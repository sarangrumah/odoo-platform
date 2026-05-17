# SOP — Tenant Onboarding

Ops-driven multi-tenant provisioning. End-to-end, a new tenant goes from
"green light" to "logged in" in **≤2 hours** when the orchestrator + Odoo
+ MinIO + Caddy are healthy.

## Pre-conditions

- Multi-tenant stack running: `make up-multitenant`
- All services healthy: `docker compose ps` shows `(healthy)` for
  `postgres`, `odoo`, `tenant-orchestrator`, `minio`, `caddy`.
- Master-admin DB bootstrapped (one-off): `make init-master-admin`
- Presenter / ops machine has trusted Caddy local CA (one-off): see
  *Caddy CA trust* below.

## Procedure

### 1. Collect tenant intake info

| Field | Example | Notes |
|-------|---------|-------|
| `slug` | `acme` | Lowercase letters/digits/underscore. Also becomes DB name + subdomain. |
| `display_name` | `Acme Corporation` | Human-readable label. |
| `plan_tier` | `trial` / `standard` / `enterprise` | Drives feature flags + billing. |
| `contact_email` | `ops@acme.id` | Initial admin recovery email. |
| `contact_phone` | `+62 812 ...` | Optional. |
| `features` | `pajakku=true`, `marketplace=false` | Feature flags. |

### 2. Add hosts entry (presenter / ops box)

Edit `C:\Windows\System32\drivers\etc\hosts` (run as admin) and add:

```
127.0.0.1   <slug>.platform.localhost
```

### 3. Provision via UI (recommended)

1. Open `https://admin.platform.localhost`.
2. Log in with the master admin account.
3. **Super Admin → Provision New** (top menu).
4. Fill the wizard with the intake info from step 1.
5. Click **Provision**.
6. **CRITICAL** — the result form shows the generated `admin_password` and
   `fernet_key_dek` **once**. Copy both to your secrets vault (1Password,
   Bitwarden, Vault, etc.) immediately.

### 3.alt. Provision via CLI

```bash
make tenant-provision SLUG=acme NAME="Acme Corporation" PLAN=standard EMAIL=ops@acme.id
```

Capture the `admin_password` + `fernet_key_dek` from the JSON output.

### 4. Smoke test

- Open `https://acme.platform.localhost` — Caddy serves the tenant.
- Log in with `admin` + the captured password.
- Confirm modules installed: Apps → search "custom_" → all expected
  modules show as Installed.
- Run a baseline audit-chain check (per tenant):
  `make verify-audit-chain DB=acme` → must return 0 broken rows.

### 5. First backup verification

```bash
make tenant-backup SLUG=acme KIND=manual
make tenant-list-backups SLUG=acme
```

Verify `outcome=success` and `size_bytes > 0` on the latest entry.

### 6. Notify CSM

- Add tenant to CSM dashboard (Grafana → Capacity dashboard → variable
  `db=acme`).
- Send onboarding email with: tenant URL, initial admin credentials
  (via secure channel only), CSM contact, support escalation path.

## Caddy CA trust (one-off per presenter / ops machine)

After first `make up-multitenant`, Caddy mints a local CA root cert at:

```
data/caddy/data/caddy/pki/authorities/local/root.crt
```

Trust it:

- **Windows**: double-click the `.crt` → Install Certificate → Local
  Machine → Trusted Root Certification Authorities.
- **macOS**: `security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain root.crt`
- **Linux**: `sudo cp root.crt /usr/local/share/ca-certificates/platform-local.crt && sudo update-ca-certificates`

After trust, all `*.platform.localhost` URLs become green-padlock in the
browser.

## Rollback

If provisioning fails midway (state `failed`), archive + retry:

```bash
make tenant-archive SLUG=acme
# wait for action to complete, then
make tenant-provision SLUG=acme2 NAME="Acme Corp" PLAN=standard
```

The first `acme` row stays in registry (state=archived) for audit; the
DB is renamed (`_archived_<ts>_acme`) and purged after 30 days.

## Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Wizard returns "HMAC mismatch" | Odoo's `GATEWAY_SHARED_SECRET` ≠ orchestrator's `ORCHESTRATOR_SHARED_SECRET` (these are different env vars by design) | Confirm `.env` has both, restart Odoo + orchestrator |
| State stays in `provisioning` > 5 min | Odoo create-DB hung | `docker compose logs odoo --tail=200` — look for OOM or template0 issue. Archive + retry. |
| `https://acme.platform.localhost` shows certificate error | Caddy CA not trusted | Follow "Caddy CA trust" section above |
| `https://acme.platform.localhost` → "Database not found" | dbfilter mismatch | Confirm `DBFILTER=^%d$` in docker-compose.multitenant.yml override + DB name = slug |
| Pajakku adapter not visible in tenant Settings | Feature flag off | Toggle in `tenant.registry` form or re-run wizard with `feature_pajakku=true` |

## Audit trail

Every step in this SOP writes to two append-only logs:

- `tenant_registry.action_log` (master DB) — orchestrator-level ops.
- `pdp.audit_log` (per-tenant DB) — Odoo-level operations after provisioning.

Both can be verified for tamper-evidence:

```bash
make tenant-verify-chain      # master action_log
make verify-audit-chain DB=acme   # per-tenant pdp
```
