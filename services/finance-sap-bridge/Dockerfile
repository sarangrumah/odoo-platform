# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
# This image installs nothing from apt, but it still inherits the base's OS
# packages -- and their CVEs. `--only-upgrade` patches the util-linux family to
# the distro's fixed build (CVE-2026-53615, integer overflow in libblkid's DOS
# partition parser): python:3.12-slim ships trixie's 2.41-5 while the fix lives
# in trixie-security as 2.41.5-0+deb13u1, which only reaches us when upstream
# rebuilds the base. `--only-upgrade` skips any name that is not installed, so
# the list survives a base change. Same idiom as odoo/Dockerfile.
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade \
      util-linux \
      bsdutils \
      libblkid1 \
      libmount1 \
      libsmartcols1 \
      libuuid1 \
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
