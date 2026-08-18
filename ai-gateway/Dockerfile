# syntax=docker/dockerfile:1.7
# ============================================================
# AI Gateway — FastAPI multi-provider abstraction
# Lightweight, non-root, read-only rootfs in compose
# ============================================================

FROM python:3.12-slim AS base

# Non-root user (UID matches docker-compose)
RUN groupadd -r app --gid 10101 \
 && useradd -r -u 10101 -g app -m -d /app -s /bin/bash app

WORKDIR /app

# System deps minimal (curl for healthcheck dev convenience, build-essential for some wheels)
# The `--only-upgrade` call patches the util-linux family to the distro's fixed
# build (CVE-2026-53615, integer overflow in libblkid's DOS partition parser).
# python:3.12-slim ships trixie's 2.41-5 and the fix lives in trixie-security as
# 2.41.5-0+deb13u1, so it only arrives when upstream rebuilds the base image --
# patching here keeps the scan green without waiting on that. `--only-upgrade`
# skips any name that is not installed, so the list survives a base change.
# Same idiom as odoo/Dockerfile.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && apt-get install -y --no-install-recommends --only-upgrade \
      util-linux \
      bsdutils \
      libblkid1 \
      libmount1 \
      libsmartcols1 \
      libuuid1 \
 && rm -rf /var/lib/apt/lists/* \
 && update-ca-certificates

# ----- Builder stage -----
FROM base AS builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --target=/app/site-packages \
      "fastapi==0.136.1" \
      "uvicorn[standard]==0.32.0" \
      "pydantic==2.9.2" \
      "pydantic-settings==2.6.0" \
      "httpx[http2]==0.27.2" \
      "anthropic==0.39.0" \
      "openai==1.54.0" \
      "redis==5.1.1" \
      "structlog==24.4.0" \
      "prometheus-client==0.21.0"

# ----- Final stage -----
FROM base AS final

COPY --from=builder /app/site-packages /app/site-packages
COPY app /app/app

ENV PYTHONPATH=/app:/app/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

USER app

EXPOSE 8080

# Healthcheck handled by compose; image-level fallback
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
  CMD ["/bin/sh", "-c", "curl -fsS http://localhost:8080/health || exit 1"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
