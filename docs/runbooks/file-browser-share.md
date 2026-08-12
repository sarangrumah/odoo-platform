# File Browser — the document hand-off share

**What it is:** a web UI over `/srv/sftp-share/files`, served at
`https://eal-hub.erajaya.com/files/`. Clients download deliverables here (the
feature catalogue is published to it by
`docs/platform-feature-catalog/publish.sh`); the same directory is the SFTP drop
zone on port 2221.

Defined in `docker-compose.multitenant.yml` as the `filebrowser` service. It was
not, until 12-Aug-2026 — it existed only as a hand-typed `docker run` on the
host. A rebuild would have lost it silently.

## Why it spent two weeks `unhealthy`

Two faults, one hiding the other. Both are fixed in the compose definition; this
is here so the next `unhealthy` is diagnosed rather than ignored.

**1. `/config` was not writable by the runtime uid.** The image's entrypoint
seeds `settings.json` there on boot. The volume was owned by
`template-ubuntuesx60` — a leftover uid from the VM template — while the
container runs as `1002` (sftpshare), so the copy was refused on every start and
the file never appeared.

**2. The healthcheck read the file that never appeared.** `/healthcheck.sh` is:

```sh
PORT=${FB_PORT:-$(cat /config/settings.json | ... )}
ADDRESS=${FB_ADDRESS:-$(cat /config/settings.json | ... )}
wget -q --spider http://$ADDRESS:$PORT/health || exit 1
```

With no settings.json, `PORT` came out empty and the probe failed with
`wget: bad port ''` — for two weeks, while the service answered HTTP 200
throughout. The container was healthy; the probe was not.

The fix is both halves: own the config directory, and set `FB_PORT` /
`FB_ADDRESS` so the probe never depends on that file again.

## Creating it on a fresh host

The config directory must exist and be owned by the runtime uid **before** the
container starts:

    mkdir -p /opt/odoo-platform/data/filebrowser-config
    chown 1002:1002 /opt/odoo-platform/data/filebrowser-config
    docker compose -f docker-compose.yml -f docker-compose.multitenant.yml up -d filebrowser

`data/filebrowser/filebrowser.db` holds the user accounts and survives a
recreate — it is a bind mount, not a volume. Back it up before touching the
container:

    cp /opt/odoo-platform/data/filebrowser/filebrowser.db /opt/db-backups/manual/filebrowser-db-$(date +%Y%m%d).bak

## Accounts

There is **one** account: `admin`, scope `/`, full rights — it can read, modify
and delete every file on the share, which is 59 entries spanning several
clients' documents.

So it is not an account to hand to a client. To give someone access to one
folder, create a scoped, read-only user instead:

    docker exec odoo19-platform-filebrowser /bin/filebrowser -d /db/filebrowser.db \
        users add <name> <password> --perm.admin=false --perm.create=false \
        --perm.delete=false --perm.modify=false --perm.rename=false --scope=/<folder>

Listing users needs the database free — the running container holds a lock, so
`users ls` against it returns `Error: timeout`. Copy the file and read the copy,
and delete the copy afterwards: it contains password hashes.

## Checks

    docker inspect odoo19-platform-filebrowser --format '{{.State.Health.Status}}'
    curl -sk -o /dev/null -w '%{http_code}\n' https://eal-hub.erajaya.com/files/

Note the UI is a single-page app: `/files/<anything>` answers 200, including
paths that do not exist. A 200 proves the service is up, never that a file is
there. Check the filesystem for that.
