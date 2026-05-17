# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# postgresql-client provides pg_dump / pg_restore / psql used by backup/restore ops
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    ca-certificates \
    tini \
 && rm -rf /var/lib/apt/lists/* \
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
      boto3==1.35.54 \
      structlog==24.4.0 \
      prometheus-client==0.21.0 \
      croniter==3.0.4 \
      apscheduler==3.10.4

COPY app ./app

# Drop SUID/SGID bits as a defence-in-depth step
RUN find / -xdev -perm -4000 -exec chmod u-s {} + 2>/dev/null || true \
 && find / -xdev -perm -2000 -exec chmod g-s {} + 2>/dev/null || true

USER orchestrator

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
