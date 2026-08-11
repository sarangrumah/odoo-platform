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
ssh -N -p 2221 -L 127.0.0.1:18079:127.0.0.1:18079 odoo-erp@192.168.3.140
```

Then open **<http://localhost:18079/web/database/manager>**.

Master password:

```bash
ssh -p 2221 odoo-erp@192.168.3.140 'grep ^ODOO_ADMIN_PASSWD= /opt/odoo-platform/.env'
```

**`-p 2221` is not optional.** sshd on this host listens on 2221, not 22
(`/etc/ssh/sshd_config`, `Port 2221`). Without it you get `ssh: connect to host
192.168.3.140 port 22: Connection refused`, which reads like the host being down.

192.168.3.140 is a LAN address and only 80/443 are NATed to this box, so the tunnel
works from the office network or the VPN, not from the open internet.

Check the tunnel is really up (expect `200`, and a list of every database):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:18079/web/database/manager
curl -s http://localhost:18079/web/database/list \
  -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}'
```

## The host has to permit forwarding at all

`sshd_config` carried a **global `DisableForwarding yes`** until 11-Aug-2026. That
directive overrides every other forwarding option — `AllowTcpForwarding yes`
included — so `-L` was refused for every account, and this whole procedure could
not work. The symptom is a session that connects normally and then:

```
channel 1: open failed: administratively prohibited: open failed
```

It was there for the SFTP share accounts (`sftpshare` and anything else in group
`sftpusers`, chrooted and forced to `internal-sftp`). The ban is now **scoped to
that group** instead of applying to everyone: `DisableForwarding yes` moved into
the `Match Group sftpusers` block, where it sits alongside the `AllowTcpForwarding
no` / `PermitTunnel no` lines that were already there.

Check either side without guessing — `sshd -T` resolves the Match blocks:

```bash
sshd -T -C user=odoo-erp,host=localhost,addr=127.0.0.1  | grep -i forwarding  # disableforwarding no
sshd -T -C user=sftpshare,host=localhost,addr=127.0.0.1 | grep -i forwarding  # disableforwarding yes
```

If a forward is ever refused again, that scoping has been reverted — check there
before debugging the client. Do **not** answer it by removing the restriction from
the `sftpusers` block: those accounts are external file hand-off, and giving them
TCP forwarding turns each one into a jump host into the platform network.

## Dropping a database: the filestore does not travel with pg_dump

Attachments do not live in Postgres. They sit in
`/opt/odoo-platform/data/odoo-filestore/filestore/<db>/`, and **`pg_dump` never
touches them** — which means the nightly job in `/opt/db-backups/auto/daily`
restores the data and loses every attachment: stored PDFs, product images,
e-Faktur evidence. Dropping through the database manager deletes the filestore
along with the database, and `dropdb` plus an orphan sweep ends up in the same
place.

So archive the filestore **at the moment you drop**, alongside the dump:

```bash
db=prd_something
dest=/opt/odoo-platform/backups/dropped-$(date +%Y%m%d)
mkdir -p "$dest"

export PGPASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' /opt/odoo-platform/.env | cut -d= -f2-)
docker exec -e PGPASSWORD="$PGPASSWORD" odoo19-platform-postgres \
  pg_dump -U odoo -Fc -d "$db" -f "/tmp/$db.dump"
docker cp "odoo19-platform-postgres:/tmp/$db.dump" "$dest/"

tar czf "$dest/$db-filestore.tgz" \
  -C /opt/odoo-platform/data/odoo-filestore/filestore "$db"
```

The database manager's own Backup (zip = SQL + filestore) does both in one step
and is the better choice when the tunnel is already up.

**Verify the dump, and verify it in the right place.** `pg_restore` is not
installed on the host, so `pg_restore -l` there fails with `command not found` —
which reads exactly like a corrupt dump. Check inside the container:

```bash
docker cp "$dest/$db.dump" odoo19-platform-postgres:/tmp/v.dump
docker exec odoo19-platform-postgres pg_restore -l /tmp/v.dump | grep -c '^[0-9]'
```

**"Later" is not an option: the window is seven days.** Since 11-Aug-2026
`/etc/cron.d/odoo-platform-disk-cleanup` sweeps orphan filestores nightly at
03:30 — any directory with no matching database. It skips anything younger than
seven days, so a filestore left behind by a drop survives a week and then goes.
It also refuses to run at all if the database list cannot be read or comes back
with fewer than five entries, because an unreachable postgres looks exactly like
"every database is gone". Details in `scripts/ops/nightly_disk_cleanup.sh`.

Worked example, 11-Aug-2026: seven databases were dropped deliberately. Dumps and
one combined filestore archive went to
`/opt/odoo-platform/backups/dropped-20260811/` first, so all seven can come back
whole — attachments included, for the five that had any:

| Database | Files in filestore |
|---|---:|
| `prd_levis_AP` | 621 |
| `trn_arkaaim_begbal` | 554 |
| `prd_detail_levis` | 525 |
| `demo` | 467 |
| `tst_agedpay` | 1 |
| `tst_recur_gapA` | none |
| `tst_appr_clean` | none |

Counts are actual files, not directory entries — Odoo's filestore nests one
directory per hash prefix, so a `tar tzf | wc -l` roughly doubles them. If you
verify a restore by counting attachments, count files.

## Traps

- **This is not the nightly backup.** The manager's Backup/Restore uses Odoo's own
  zip format (SQL dump *plus* filestore). The nightly job
  (`scripts/ops/pg_backup_all.sh`) writes pg_dump custom-format files with no
  filestore. They are not interchangeable — during a recovery, know which one you
  are holding. See `docs/runbooks/backup-restore.md`.
- **Take a dump before you drop, restore or duplicate a production database.** The
  manager gives no confirmation worth the name and no undo. A dump alone is not a
  full restore point — see the filestore section above.
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
