# Docker CIS Baseline — Odoo 19 Platform

This document records how the platform meets the CIS Docker Benchmark v1.7 critical and high-impact recommendations. Findings are documented per CIS section. Sections not applicable (e.g., Docker Swarm) are noted but not configured.

## 2 — Docker daemon configuration

- 2.1 Restrict network traffic between containers: each compose project has its own user-defined bridge (`odoo19-platform-net`). No `--icc=true` default-bridge usage.
- 2.5 Do not use insecure registries: all images pulled from official sources (Docker Hub / GHCR).
- 2.8 Enable user namespace support: recommended for prod (out-of-scope for compose; deploy host doc).
- 2.11 Limit memory / CPU / pids per service: configured via `deploy.resources.limits` in `docker-compose.yml` and `docker-compose.prod.yml`.

## 4 — Container images & build

- 4.1 Use trusted base images: `odoo:19.0`, `postgres:16-alpine`, `redis:7-alpine`, `python:3.12-slim`, `nginx:1.27-alpine`, official Grafana / Prometheus / Loki.
- 4.5 Add HEALTHCHECK: present on all custom images (`odoo/Dockerfile`, `ai-gateway/Dockerfile`, `custom-predictor/Dockerfile`) and via compose `healthcheck:` for upstream images.
- 4.6 Use specific tag pinning: all images use explicit version tags, not `latest` (in compose).
- 4.7 Use COPY instead of ADD: confirmed in all Dockerfiles.
- 4.9 Strip SUID/SGID in image: `odoo/Dockerfile` runs `find / -perm -4000 -exec chmod u-s` on build.
- 4.10 No secrets in image layer: only configs and templates baked in; secrets come from env at runtime.

## 5 — Container runtime

- 5.1 AppArmor (Linux): host-dependent; profile available in `security/apparmor/` as starting point.
- 5.2 SELinux: host-dependent.
- 5.3 Restrict Linux kernel capabilities: every service in compose has `cap_drop: [ALL]` with explicit `cap_add` only where required.
- 5.4 No privileged containers: confirmed (`privileged: false` is implicit; no service uses `privileged: true`).
- 5.5 Limit sensitive host paths: only `/var/run/docker.sock`, `/proc`, `/sys` mounted into observability services (read-only). No host config mounts into Odoo.
- 5.7 Do not map privileged ports inside containers: containers listen on ≥1024 internally (8069/8080/3000/etc.). Nginx in prod uses cap `NET_BIND_SERVICE` to bind 80/443.
- 5.10 No-new-privileges: `security_opt: [no-new-privileges:true]` set on every service.
- 5.12 Mount root FS as read-only: enabled on `ai-gateway`, `custom-predictor`, `odoo-exporter`, and `odoo` in prod override. Tmpfs used for `/tmp`.
- 5.14 PID cgroup limit: `pids_limit: 256` set on each service in prod (review per workload).
- 5.15 Restart policy: `unless-stopped` for all (avoids restart-loop DoS).
- 5.25 Restrict container from acquiring new privileges: see 5.10.
- 5.28 Use PIDs cgroup limit: see 5.14.

## 6 — Docker security operations

- 6.1 Audit Docker daemon: deploy host responsibility (recommend auditd).
- 6.5 Audit `/var/lib/docker`, `/etc/docker`: deploy host responsibility.

## Hard requirements (must-fix before prod)

1. Replace every `changeme` in `.env`.
2. Generate `GATEWAY_SHARED_SECRET` with `openssl rand -hex 32`.
3. Generate `CORETAX_SERTEL_MASTER_KEY` with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
4. Replace dev `nginx/certs/*` self-signed with CA-issued certs.
5. Enable AppArmor / SELinux on host.
6. Configure `userns-remap` in `/etc/docker/daemon.json` (host doc).
7. Rotate `POSTGRES_PASSWORD` quarterly (see `secret-rotation.md`).
