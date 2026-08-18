# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
RUN groupadd -r app --gid 10101 \
 && useradd -r -u 10101 -g app -m -d /app -s /bin/bash app
WORKDIR /app
# The `--only-upgrade` call patches the util-linux family to the distro's fixed
# build (CVE-2026-53615, integer overflow in libblkid's DOS partition parser).
# python:3.12-slim ships trixie's 2.41-5 and the fix lives in trixie-security as
# 2.41.5-0+deb13u1, so it only arrives when upstream rebuilds the base image --
# patching here keeps the scan green without waiting on that. `--only-upgrade`
# skips any name that is not installed, so the list survives a base change.
# Same idiom as odoo/Dockerfile.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get install -y --no-install-recommends --only-upgrade \
      util-linux \
      bsdutils \
      libblkid1 \
      libmount1 \
      libsmartcols1 \
      libuuid1 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir prometheus-client==0.21.0 httpx==0.27.2 structlog==24.4.0
COPY exporter.py /app/exporter.py
USER app
EXPOSE 9200
CMD ["python", "/app/exporter.py"]
