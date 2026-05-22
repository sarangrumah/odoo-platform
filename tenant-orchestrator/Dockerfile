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
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    ca-certificates \
    curl \
    tini \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz \
      | tar -xz -C /tmp \
 && mv /tmp/docker/docker /usr/local/bin/docker \
 && rm -rf /tmp/docker \
 && apt-get purge -y --auto-remove curl \
 && useradd -u 10102 -m -s /usr/sbin/nologin orchestrator

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      fastapi==0.115.4 \
      uvicorn[standard]==0.32.0 \
      "pydantic[email]==2.9.2" \
      pydantic-settings==2.6.0 \
      httpx[http2]==0.27.2 \
      psycopg[binary,pool]==3.2.3 \
      cryptography==43.0.3 \
      bcrypt==4.2.0 \
      passlib==1.7.4 \
      boto3==1.35.54 \
      structlog==24.4.0 \
      prometheus-client==0.21.0 \
      croniter==3.0.4 \
      apscheduler==3.10.4

COPY app ./app

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
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
