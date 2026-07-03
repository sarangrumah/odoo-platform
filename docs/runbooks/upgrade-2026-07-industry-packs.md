# VPS Upgrade Runbook — Finance Portal + Tax Reports + SSO + PO Return

Release branch: **`feat/industry-packs`** (commits `10273a0..237cd9f`, 2026-07-03).
Target: an already-running VPS stack (`make up-tls` / `up-prod`). This is an
in-place **module upgrade**, not a first-time host bootstrap — for a fresh host
see [`../vps-demo-deploy.md`](../vps-demo-deploy.md) /
[`../prod-deploy-checklist.md`](../prod-deploy-checklist.md).

---

## 0. What's in this release

**New modules** (install with `-i` on the DBs that need them):

| Module | Purpose | Install on |
|--------|---------|-----------|
| `custom_finance_portal` | Engagement layer over SAP (Cash Advance / Reimbursement / Vendor Invoice / Travel), 2-stage Tax→Finance approval, no native GL | Finance Portal tenant |
| `custom_finance_budget` | Per-division budget consumption check | Finance Portal tenant |
| `custom_finance_portal_sap` | SAP/HRIS bridge adapter, async push, master sync (needs `queue_job`, `custom_adapter_framework`) | Finance Portal tenant |
| `custom_finance_portal_sso` | Keycloak OIDC login + role→group map | Finance Portal tenant |
| `authenticate_keycloak` | Keycloak login button on Odoo | where SSO wanted |
| `custom_hr_sso_keycloak` | Keycloak SSO + non-blocking hr.employee sync | where HR SSO wanted |
| `custom_po_return` | Quantity-driven vendor returns (FIFO) + credit notes | tenants doing RTV |
| `custom_levis_asset_accounts` | Wires IAS 16 revaluation accounts onto asset groups (Erajaya chart) | Levi's / Erajaya tenant |

**Modified modules** (update with `-u` on DBs where already installed):

| Module | Change |
|--------|--------|
| `custom_accounting_asset` | Fixed-asset IAS 16 revaluation (new models/wizards) |
| `custom_accounting_reports` | Indonesian tax reports: Bupot, Faktur Pajak/Pengganti, SPT PPN, DPP Nilai Lain, NSFP, NPWP quality, PPh withholding/equalisation, Coretax submission, Pajakku usage |
| `custom_accounting_full` | Vendor-bill reference guard (faktur uniqueness for equalisation) |
| `custom_levis_localization` | Payment vouchers, journal billing, terbilang, payment-register views |

**Not auto-deployed:** `services/finance-sap-bridge/` (Kafka bridge micro-service)
is **not** wired into any compose file yet. The portal degrades to a local stub
without it, so this upgrade does **not** require it. Deploy the bridge separately
only when connecting SAP for real.

All dependencies (`queue_job` in `addons/_vendor`, `custom_adapter_framework`,
`custom_approval_engine`, `custom_pdp_core/_audit`) are already in the repo — no
extra `fetch_oca.sh` step needed.

---

## 1. Pre-flight

```bash
ssh <vps>
cd /opt/odoo-platform

# 1a. Know your DBs
docker exec odoo19-platform-postgres psql -U odoo -d postgres \
  -c "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY 1;"

# 1b. BACK UP every DB you're about to touch (migrations are hard to undo)
make backup-now        # S3 sidecar (prod), or:
make backup            # local pg_dumpall -> data/backups/
```

Do not proceed until you have a backup file you can see (`ls -lh data/backups/`).

---

## 2. Pull the new code

Addons are **bind-mounted read-only** into the Odoo container
(`./addons:/mnt/extra-addons:ro`), so a `git pull` is all that's needed to put
the new code where the container can see it — **no image rebuild**, because
`odoo/Dockerfile` and `odoo/requirements.txt` did not change in this release.

```bash
git fetch origin
git checkout feat/industry-packs
git pull --ff-only origin feat/industry-packs
git log --oneline -3          # expect 237cd9f at HEAD
```

> If a future release touches `odoo/requirements.txt` or `odoo/Dockerfile`, then
> also run `docker compose -f docker-compose.yml -f docker-compose.prod.yml build odoo`
> before the next step.

---

## 3. Apply module changes per DB

Run Odoo **out of band** (`--stop-after-init --no-http`) so it never goes through
nginx/Caddy — this avoids the `ERR_EMPTY_RESPONSE` proxy-timeout on long upgrades.
Set `DB` once per tenant and run the block for that tenant.

### 3a. Finance Portal tenant

```bash
DB=<finance_portal_db>

# Check current state first
docker exec odoo19-platform-postgres psql -U odoo -d "$DB" -c \
  "SELECT name,state FROM ir_module_module WHERE name LIKE 'custom_finance%' ORDER BY 1;"

# Install the suite (Odoo resolves deps automatically, in order)
docker exec odoo19-platform-odoo odoo -d "$DB" --stop-after-init --no-http \
  -i custom_finance_portal,custom_finance_budget,custom_finance_portal_sap,custom_finance_portal_sso

# Optional SSO for login/HR on this DB
docker exec odoo19-platform-odoo odoo -d "$DB" --stop-after-init --no-http \
  -i authenticate_keycloak,custom_hr_sso_keycloak
```

### 3b. Levi's / Erajaya tenant

```bash
DB=<levis_db>

# Update the modified localisation + accounting modules, install the new ones
docker exec odoo19-platform-odoo odoo -d "$DB" --stop-after-init --no-http \
  -u custom_levis_localization,custom_accounting_asset,custom_accounting_reports,custom_accounting_full \
  -i custom_levis_asset_accounts
```

### 3c. Any other tenant already running the accounting modules

```bash
DB=<other_db>
docker exec odoo19-platform-odoo odoo -d "$DB" --stop-after-init --no-http \
  -u custom_accounting_asset,custom_accounting_reports,custom_accounting_full
# add: -i custom_po_return   (if that tenant does vendor returns)
```

Watch the tail of each run for `Modules loaded.` and no `CRITICAL`/`ERROR`:
```bash
docker logs --tail 80 odoo19-platform-odoo
```

> **Caution (tax data on `-u`):** `custom_accounting_reports` touches tax config.
> After its `-u`, spot-check that no duplicate tax / report definitions were
> created (Accounting → Configuration). If the module ships CSV-seeded tax rows,
> re-running `-u` is not guaranteed idempotent — verify counts against a backup.

---

## 4. Restart the serving Odoo process

The `--stop-after-init` runs above applied schema/data using the fresh code, but
the **long-running** Odoo server still holds the old Python in memory. Restart it
so the new methods are actually served:

```bash
docker restart odoo19-platform-odoo
docker exec odoo19-platform-odoo true && echo "up"
```

---

## 5. Smoke test

- [ ] `https://<DOMAIN>/web/login` loads; admin login works
- [ ] Apps list shows the new modules **Installed** at version `19.0.x`
- [ ] Finance Portal: create a draft Cash Advance → submit → lands in Tax Review
- [ ] Tax reports menu renders (Bupot / Faktur Pajak / SPT PPN wizards open)
- [ ] Levi's: post a payment → payment voucher PDF prints with terbilang
- [ ] `docker logs --tail 100 odoo19-platform-odoo` is clean of `ERROR`

---

## 6. Rollback

Module upgrades that changed the schema are **not** cleanly reversible by code
alone — restore from the §1 backup if a migration went wrong.

```bash
# Code rollback (safe for view/logic-only issues):
git checkout 29a2624           # pre-release HEAD
docker restart odoo19-platform-odoo

# Data rollback (if a -u corrupted data): restore the affected DB from backup
make restore FILE=data/backups/<dumpall-...>.sql.gz
```

---

## 7. After go-live (optional)

- Enable Keycloak: set the realm endpoints + client id on the seeded (disabled)
  `auth.oauth.provider`, then enable it per tenant.
- Deploy `services/finance-sap-bridge/` and enable the `custom.adapter.config`
  rows to switch the Finance Portal from local stub to real SAP push.
- Merge `feat/industry-packs` → `main` once the demo/UAT signs off.
