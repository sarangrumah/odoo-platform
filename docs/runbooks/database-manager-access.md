# Reaching Odoo's database manager

**Symptom:** `https://103.130.240.24/web/database/manager` (or the same path on
`eal-hub.erajaya.com`) answers **403 "Not available"**, and `https://<domain>/`
redirects to `/signin/` instead of showing Odoo's database selector.

**That is the design, not a fault.** Do not "fix" it by loosening Caddy or
`dbfilter`. The manager moved to a private instance; this page is how you get there.

## Why the public host refuses it

Two independent controls, both deliberate, both added on 5-Aug-2026 with the
front-door login gateway:

- `caddy/Caddyfile` has a `handle /web/database/*` block that answers 403 outright.
- The instance serving the public host (`odoo-front`) runs `LIST_DB=False`, so Odoo
  itself rejects those endpoints. The Caddy block is the belt to that pair of braces.

Before they existed, the root of the public host served Odoo's database selector —
the name of every tenant database, plus create/drop/backup/restore — to any
anonymous visitor. See `docs/runbooks/front-door-hardening.md`.

Three Odoo instances run on this host, and only one of them is a database manager:

| instance | `list_db` | `dbfilter` | role |
|---|---|---|---|
| `odoo` | False | `^%d$` | per-tenant hostname routing |
| `odoo-front` | False | `^.*$` | the front door on the domain / public IP |
| `odoo-mgmt` | **True** | `^.*$` | **the database manager**, private on `127.0.0.1:18079` |

`odoo-mgmt` is bound to loopback on the host and published nowhere else. Only ports
80 and 443 are NATed to this box, so even publishing it on another port would not
make it reachable from outside — an SSH tunnel is the only route, and it is the one
that keeps the manager off the internet.

## Procedure

From your workstation:

```bash
scripts/ops/db-manager-tunnel.sh
```

or, without the helper:

```bash
ssh -N -L 127.0.0.1:18079:127.0.0.1:18079 odoo-erp@192.168.3.140
```

Then open **<http://localhost:18079/web/database/manager>**.

Master password:

```bash
ssh odoo-erp@192.168.3.140 'grep ^ODOO_ADMIN_PASSWD= /opt/odoo-platform/.env'
```

Check the tunnel is really up (expect `200`, and a list of every database):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:18079/web/database/manager
curl -s http://localhost:18079/web/database/list \
  -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}'
```

## Traps

- **This is not the nightly backup.** The manager's Backup/Restore uses Odoo's own
  zip format (SQL dump *plus* filestore). The nightly job
  (`scripts/ops/pg_backup_all.sh`) writes pg_dump custom-format files with no
  filestore. They are not interchangeable — during a recovery, know which one you
  are holding. See `docs/runbooks/backup-restore.md`.
- **Take a dump before you drop, restore or duplicate a production database.** The
  manager gives no confirmation worth the name and no undo.
- **`odoo-mgmt` runs `WORKERS=0`** (threaded, single process). Fine for admin work;
  a large restore will be slow and will block other requests *on that instance*.
  Tenant traffic goes through `odoo` / `odoo-front` and is unaffected.
- **Never loosen the public instance's `dbfilter`, and never delete the
  `handle /web/database/*` block** to make this easier. Either one puts the full
  tenant database list — `prd_levis_begbal`, `prd_arkaaim`, and the rest — back in
  front of the internet.
- Editing `caddy/Caddyfile` on the host needs a container **recreate**, not a
  restart: the file is a single-file bind mount and a restart keeps reading the old
  inode. See `docs/runbooks/front-door-hardening.md`.
