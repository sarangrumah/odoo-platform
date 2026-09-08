# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
# Security patches from the base image, not just the packages we add. The
# python:3.12-slim tag is rebuilt on its own schedule, so between rebuilds its
# Debian packages fall behind the security archive — CVE-2026-14456 (openssl
# DoS) sat in libssl3t64 3.5.6 while 3.5.7 had been published. Upgrading here
# means our rebuild picks it up instead of waiting for upstream's.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app --gid 10101 \
 && useradd -r -u 10101 -g app -m -d /app -s /bin/bash app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
