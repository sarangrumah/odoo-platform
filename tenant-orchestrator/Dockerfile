# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Enable pipefail so a failed step in `curl ... | tar ...` (line 21 below)
# aborts the build instead of silently producing a half-extracted docker CLI.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# postgresql-client: pg_dump / pg_restore / psql for backup/restore ops.
# docker-cli (static): the orchestrator invokes ``docker exec odoo-mgmt odoo -d <db> --init=...``
#   to bootstrap freshly-provisioned tenant databases. The /web/database/create
#   HTTP path is unreliable in Odoo 19 (returns 200 even when ``-i base`` fails).
#   /var/run/docker.sock is mounted read-only by docker-compose.multitenant.yml.
#   Keep this version current: the static CLI is a single Go binary, so every
#   Go stdlib CVE is compiled into it and trivy reports it as a `gobinary`
#   target. 27.3.1 was built with go1.22.7 and carried 15 HIGH/CRITICAL
#   findings; 29.7.1 is built with go1.26.5 and carries none.
# The `--only-upgrade` call patches the util-linux family to the distro's fixed
# build (CVE-2026-53615, integer overflow in libblkid's DOS partition parser).
# python:3.12-slim ships trixie's 2.41-5 and the fix lives in trixie-security as
# 2.41.5-0+deb13u1, so it only arrives when upstream rebuilds the base image --
# patching here keeps the scan green without waiting on that. `--only-upgrade`
# skips any name that is not installed, so the list survives a base change.
# Same idiom as odoo/Dockerfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    ca-certificates \
    curl \
    tini \
 && apt-get install -y --no-install-recommends --only-upgrade \
      util-linux \
      bsdutils \
      libblkid1 \
      libmount1 \
      libsmartcols1 \
      libuuid1 \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-29.7.1.tgz \
      | tar -xz -C /tmp \
 && mv /tmp/docker/docker /usr/local/bin/docker \
 && rm -rf /tmp/docker \
 && apt-get purge -y --auto-remove curl \
 && useradd -u 10102 -m -s /usr/sbin/nologin orchestrator

WORKDIR /app

# Install from pyproject.toml rather than repeating the dependency list here.
# The two lists had already drifted: paramiko was declared in pyproject but
# never reached the image, so every VPS-provisioning call raised
# ``RuntimeError: paramiko not installed`` at runtime (app/provisioner_ssh.py),
# while passlib was installed here but absent from pyproject, so any
# pyproject-based install broke app/dbops.py. One source of truth prevents both.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Drop SUID/SGID bits as a defence-in-depth step
RUN find / -xdev -perm -4000 -exec chmod u-s {} + 2>/dev/null || true \
 && find / -xdev -perm -2000 -exec chmod g-s {} + 2>/dev/null || true

# NOTE: We do NOT drop privileges via USER directive when /var/run/docker.sock
# is mounted. The mounted socket is root-owned, and the orchestrator needs
# ``docker exec`` access to invoke ``odoo --init`` on the odoo-mgmt container.
# Docker socket access already grants root-equivalent capability on the host,
# so dropping privileges inside the container is not a meaningful additional
# defence here. The orchestrator container itself stays on the internal
# odoo-net bridge — never publicly reachable — and authenticates every API
# call with HMAC. The unused ``orchestrator`` user above is kept so a future
# refactor (e.g., HMAC-authenticated sidecar in odoo-mgmt replacing docker.sock)
# can switch back to a non-root runtime.
# USER orchestrator

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=15s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"]

# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint - runs as root by design (needs docker.sock); container is internal-only + HMAC-authed, see rationale above
ENTRYPOINT ["/usr/bin/tini","--"]
# nosemgrep: dockerfile.security.missing-user.missing-user - runs as root by design (needs docker.sock); container is internal-only + HMAC-authed, see rationale above
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
