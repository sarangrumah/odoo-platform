# Image Hardening Runbook — 2026-08-04

Container images across the whole stack went from **100 HIGH/CRITICAL trivy
findings to 0**, `container-scan` grew from 3 images to 9, and eight production
containers in `/opt` were swapped. One of those swaps broke Odoo completely and
was rolled back — the recovery and the guard added afterwards are the most
reusable part of this document.

Merged to `main`: **#84**, **#81**, **#89**, **#90**, **#92** (plus #72, #74,
#75, #77, #78, #79, #80 earlier the same day). Final `main`: `314d65e`.

> **If you are here because an image bump broke production**, skip to
> [§5 Incident](#5-incident-cryptography-50-killed-every-odoo-route) and
> [§6 Rollback](#6-rollback).

---

## 1. What changed

| Area | Change | PR |
|---|---|---|
| `container-scan` matrix | 3 Dockerfiles → **all 9** | #81 |
| hub-portal, storefront, baileys | drop bundled npm + corepack from runtime stage; targeted `apk upgrade libssl3 libcrypto3` | #84 |
| tenant-orchestrator | starlette → 1.3.1, fastapi → 0.141.1, static docker CLI 27.3.1 → 29.7.1, install from `pyproject.toml` | #84 |
| ai-gateway | rebuild refreshes Debian layer (curl CVE-2026-5773) | #77 + rebuild |
| odoo | `pyOpenSSL==26.4.0` pinned alongside `cryptography==50.0.0` | #89 |
| CI | boot-check the odoo image, not just scan it | #90 |
| CI | `linux-libc-dev` suppressed via Rego ignore-policy | #92 |

### Findings cleared

| Image | Before | After |
|---|---|---|
| hub-portal | 20 (1 CRITICAL) | 0 |
| storefront | 20 (1 CRITICAL) | 0 |
| baileys | 20 (1 CRITICAL) | 0 |
| tenant-orchestrator | 18 (1 CRITICAL) | 0 |
| ai-gateway | 4 | 0 |
| odoo | 5 non-OS + 118 OS | 0 (OS suppressed, see §7) |

**Not one Node.js finding came from application code.** All three node images
carried the *same* 18, entirely from `/usr/local/lib/node_modules/npm/**` and
`corepack` that `node:20-alpine` bundles — while every one of those runtimes
starts its server with `node` and never invokes npm.

```dockerfile
# in the runtime stage, after any step that still needs npm, before USER
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
 && apk upgrade --no-cache libssl3 libcrypto3
```

Placement gotcha: **hub-portal's runtime stage really does run
`npm install --omit=dev`** — chain the `rm` into that same `RUN`. storefront and
baileys can drop it standalone.

---

## 2. Deploy procedure (staged)

Work in `/opt/odoo-platform`. Three rules, each learned the hard way:

**Never copy a whole directory from `main`.** `/opt` sits on
`feat/industry-packs`, which carries commits `main` does not — `2212615`
(provisioner installs `custom_currency_nbsp` on every new tenant) and `adea94b`
(baileys sends `X-Odoo-Database`). Copying `tenant-orchestrator/` or
`services/baileys/` wholesale silently reverts them. Check first:

```bash
git log --oneline origin/main..HEAD -- <dir>/     # what would be lost
git checkout origin/main -- <specific files>      # then take only those
```

**Always pass both compose files.** `/opt/.env` sets no `COMPOSE_FILE`, so a
bare `docker compose up` drops every override in `docker-compose.multitenant.yml`
— see §4.

**Tag a rollback image before retagging `:latest`.**

```bash
docker tag odoo19-platform-<svc>:latest odoo19-platform-<svc>:rollback-$(date +%Y%m%d)
docker compose build <svc>
# verify the image BEFORE swapping — see §3
docker compose -f docker-compose.yml -f docker-compose.multitenant.yml \
  up -d --no-deps <svc>
```

For the odoo image, build to `:candidate` instead of `:latest` so nothing can
pick it up accidentally, verify, then retag.

### Order matters

`odoo-mgmt` serves no tenants but uses the same image and the same database.
**Swap it first.** That is what turned §5 from an outage into a non-event.

```
odoo-mgmt  →  odoo  →  odoo-vaspmo
```

---

## 3. Verification that actually proves something

A green healthcheck is not evidence. Each of these caught, or would have caught,
a real defect today.

```bash
# node images — npm gone, node still works
docker run --rm --entrypoint sh   <img> -c 'command -v npm || echo REMOVED'
docker run --rm --entrypoint node <img> -e 'console.log(process.version)'

# tenant-orchestrator — the dependency drift that broke VPS provisioning
docker run --rm --entrypoint python3 <img> -c "import paramiko, passlib.hash"
docker run --rm --entrypoint docker  <img> --version

# odoo — the check that scanning cannot do (see §5)
docker run --rm --entrypoint python3 <img> -c "import odoo.addons.web.controllers.database"
```

Against the running stack:

```bash
# existing wrapped tenant DEKs must still unwrap after a cryptography bump
docker run --rm --network container:odoo19-platform-tenant-orchestrator \
  --env-file <(docker inspect odoo19-platform-tenant-orchestrator \
      --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^[A-Za-z_]+=') \
  --entrypoint python3 <img> -c "
from app.db import master_connection
from app.crypto import unwrap_dek
with master_connection() as c, c.cursor() as cur:
    cur.execute('SELECT slug, fernet_key_wrapped FROM tenant_registry.tenants '
                'WHERE fernet_key_wrapped IS NOT NULL')
    print(sum(bool(unwrap_dek(bytes(w))) for _, w in cur.fetchall()), 'unwrapped')"

# HMAC middleware — header is X-Custom-Signature, NOT X-Signature
# valid sig -> 200, missing -> 401, bad sig -> 401

# odoo — load a real production registry, not just the login page
docker exec odoo19-platform-odoo python3 -c "
from odoo.modules.registry import Registry
import odoo
r = Registry('prd_arkaaim')
with r.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    print(len(r._init_modules), 'modules |', env['ir.mail_server'].search_count([]))"
```

`tenant_registry` is a **schema in the master DB**, not a database — connect via
the app's own `master_connection()`.

---

## 4. Trap: the multitenant overlay is not optional

`/opt/.env` has only `COMPOSE_PROJECT_NAME`. A bare
`docker compose up -d tenant-orchestrator` therefore uses `docker-compose.yml`
alone and **silently drops**:

```yaml
    read_only: false                                   # base sets read_only: true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      ODOO_HOST: odoo-mgmt
      ODOO_MGMT_CONTAINER: ${COMPOSE_PROJECT_NAME:-odoo19-platform}-odoo-mgmt
```

The container comes back **healthy** while `docker ps` inside it fails with
`dial unix /var/run/docker.sock: connect: no such file or directory` — the entire
tenant-bootstrap path dead, with a green light.

```bash
# after ANY recreate, confirm the mounts survived
docker inspect <c> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

`docker-compose.observability.yml` also mounts docker.sock. Before recreating
anything: `grep -ln docker.sock docker-compose*.yml`.

---

## 5. Incident: cryptography 50 killed every Odoo route

**Symptom.** `odoo-mgmt` starts, logs
`odoo.service.server: HTTP service (werkzeug) running on …:8069`, healthcheck
fails, and **every** route — `/web/login`, `/web/database/selector` — returns
**404**. A port check looks fine.

**Cause.** The base image ships Ubuntu's `python3-openssl` = **pyOpenSSL 23.2.0**.
`OpenSSL/crypto.py` reads `_lib.GEN_EMAIL`, removed from the cryptography **50.x**
bindings:

```
File "/usr/lib/python3/dist-packages/OpenSSL/crypto.py", line 846, in X509Extension
    _lib.GEN_EMAIL: "email",
AttributeError: module 'lib' has no attribute 'GEN_EMAIL'
```

Odoo core imports it from `base/models/ir_mail_server.py`, which
`web/controllers/database.py` imports in turn — so the whole `web` module fails
to load.

**Fix.** `pyOpenSSL==26.4.0`, the first release accepting `cryptography>=49,<51`.

> ⚠️ Do **not** resolve a conflict here with a 25.x. Their caps are `<45` / `<46`
> / `<47`, so pip silently **downgrades** cryptography — 25.3.0 pulled it back to
> 46.0.7 — undoing the CVE fixes the bump existed for.

**Why CI was green throughout.** `container-scan` builds an image and scans it;
it never boots Odoo. `sca-python` audits the pin list, which was internally
consistent. `odoo --version` also passes — it exits before module loading.
`main` had been shipping a dead odoo image since #74.

**Guard added (#90).** The `container-scan` matrix now takes an optional `smoke`
field, run right after the build:

```yaml
- {name: odoo, dir: odoo, smoke: "import odoo.addons.web.controllers.database"}
```

Verified in both directions — it passes on the fixed image and **fails** on a
reproduction of the broken pair. A guard that cannot go red is not a guard.

---

## 6. Rollback

Every image swapped on 2026-08-04 has a `:rollback-20260804` tag.

```bash
docker tag odoo19-platform-<svc>:rollback-20260804 odoo19-platform-<svc>:latest
docker compose -f docker-compose.yml -f docker-compose.multitenant.yml \
  up -d --no-deps <svc>
```

For odoo that is `odoo`, `odoo-mgmt` and `odoo-vaspmo` — all three share the tag.
Recovery on 2026-08-04 took about a minute, and **no tenant-facing container was
ever exposed to the broken image**, because `odoo-mgmt` went first.

Addons are **bind-mounted**, not baked in, so an image rollback never touches
module code: no `-u`, no migration, no schema risk.

---

## 7. `linux-libc-dev` suppression (#92)

The odoo image reports ~118 HIGH/CRITICAL from `linux-libc-dev` alone. It is C
kernel headers under `/usr/include/linux` — nothing executes, and a container
uses the **host** kernel. `apt-get --only-upgrade linux-libc-dev` would install
headers mismatched to the running host kernel, which is worse than leaving it.
The real fix is upstream republishing `odoo:19`.

It could **not** go in `.trivyignore`, which matches vulnerability IDs only —
118 pasted IDs go stale on the next kernel advisory. `.trivyignore.yaml`'s
`purl:` field does not match deb packages either; measured on trivy 0.70.0 and
0.73.0:

| attempt | effect |
|---|---|
| `pkg:deb/ubuntu/linux-libc-dev` | none |
| wildcard `…*` / `…@*` | none |
| exact PURL incl. `?arch=amd64&distro=ubuntu-24.04` | none |
| `id: CVE-…` in the same file | **filtered** ← control: the file *was* loaded |

The working mechanism is `.trivy/ignore-policy.rego`, wired through the
trivy-action `ignore-policy:` input:

```rego
package trivy
default ignore = false
ignore { input.PkgName == "linux-libc-dev" }
```

**REVIEW:** drop this rule and re-scan whenever the odoo base image is bumped.
Do not widen it to other OS packages — those are fixable in our own Dockerfile.

---

## 8. Notes for whoever works in `/opt` next

- **`trivy-action@v0.36.0` installs trivy v0.70.0.** Test ignore rules against
  that, not just a local `:latest` (0.73.0), whose DB is also fresher and will
  surface findings CI has not seen yet.
- **Prove a suppression twice**: the targeted findings vanish *and* unrelated
  findings in the same image still report. A policy that silences everything
  looks identical on a one-way test.
- **`git checkout origin/main -- <path>` stages the file.** A later
  `git checkout -- <path>` restores from the index, so it does *not* revert, and
  the next `git commit` sweeps it in — along with anything another session left
  staged in the shared index. Commit with an explicit pathspec:
  `git commit -- <paths>`.
- **A no-cache rebuild before believing app-dep findings** on images without a
  lockfile. A stale `deps` layer held axios 1.16.1 while 1.18.0 existed,
  producing three phantom findings that vanished on `docker build --no-cache`.
- **`$?` after a pipe is the last command's**, not the interesting one. Use
  `if cmd; then` when checking whether something failed.
- **Read `git push` output per remote.** `origin` pushes to GitHub *and*
  Bitbucket; Bitbucket is frozen and diverged, so it always rejects. The exit
  code is not the verdict.

---

## Related

- [`../../.trivy/ignore-policy.rego`](../../.trivy/ignore-policy.rego)
- [`prod-deploy-checklist.md`](../prod-deploy-checklist.md)
- [`upgrade-2026-07-industry-packs.md`](upgrade-2026-07-industry-packs.md)
- [`incident-odoo-oom.md`](incident-odoo-oom.md)
