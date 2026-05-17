# AppArmor profile (opt-in, Linux host only)

This directory contains a starting-point AppArmor profile for the Odoo
container. AppArmor is a Linux-only MAC framework — Mac/Windows hosts
running Docker Desktop will ignore profile loads silently.

The profile is **defence-in-depth**: even if an attacker escapes seccomp
or the dropped-capabilities sandbox, AppArmor restricts what the process
can read, write, mount, or signal.

## When to use

- Production deployments on Linux hosts (Ubuntu / Debian / SUSE) with
  AppArmor enabled (the default on Ubuntu).
- CIS Docker Benchmark control 5.1 — "Verify AppArmor profile is enabled,
  if applicable".

## Files

| File | Purpose |
|------|---------|
| `odoo.profile` | Restricts the Odoo container's capabilities, filesystem reach, networking, and ability to exec child processes. |

## Install on the host

```bash
sudo cp security/apparmor/odoo.profile /etc/apparmor.d/custom-platform-odoo
sudo apparmor_parser -r /etc/apparmor.d/custom-platform-odoo
sudo aa-status | grep custom-platform-odoo
```

You should see the profile listed under "enforce mode".

## Wire it into Docker Compose

Add to the `odoo` service in `docker-compose.prod.yml`:

```yaml
services:
  odoo:
    security_opt:
      - apparmor=custom-platform-odoo
      - no-new-privileges:true
      - seccomp:./security/seccomp/odoo.json
```

Restart the stack: `docker compose up -d odoo`.

## Verify it's enforcing

```bash
docker inspect $(docker compose ps -q odoo) \
  | jq '.[0].AppArmorProfile'
# → "custom-platform-odoo"
```

## Loosening during debugging

To switch to "complain" mode (logs only, doesn't block):

```bash
sudo aa-complain /etc/apparmor.d/custom-platform-odoo
# debug…
sudo aa-enforce /etc/apparmor.d/custom-platform-odoo
```

## Tuning

Tail the kernel log for denials while exercising Odoo:

```bash
sudo journalctl -kf | grep apparmor=DENIED
```

Add allow rules to `odoo.profile` (or use `aa-logprof` for guided
addition). Re-load with `apparmor_parser -r`.

## Caveats

- This profile assumes the Odoo Docker image filesystem layout from
  `odoo/Dockerfile` (`/usr/local/bin/custom-*.sh`, default Odoo install
  paths). Adjust paths if you switch base images.
- If you mount filestore at a non-default path, update the rule under
  "Filesystem".
- Docker for Windows / Docker Desktop on Mac uses a Linux VM but does
  not load host AppArmor profiles into containers. The profile is a no-op
  there.
