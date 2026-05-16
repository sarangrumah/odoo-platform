# syntax=docker/dockerfile:1.7
# ============================================================
# Hardened Odoo 19 image
# - Pinned to verified latest tag from Docker Hub (May 2026)
# - Adds xmlsec for XAdES sertel signing (Coretax)
# - Strips SUID, runs as non-root odoo user (already in base)
# ============================================================

FROM odoo:19.0

USER root

# System deps for: git (OCA fetch), curl (healthcheck), gettext-base (envsubst),
# xmlsec1 (Coretax XML signing), build deps for cryptography wheels
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      curl \
      gettext-base \
      xmlsec1 \
      libxmlsec1-dev \
      libxmlsec1-openssl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && update-ca-certificates

# Python deps tambahan (HTTP client for AI gateway, encryption, XML validation)
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
 && rm -f /tmp/requirements.txt

# Strip SUID binaries (CIS hardening)
RUN find / -xdev -perm -4000 -type f -exec chmod u-s {} + 2>/dev/null || true \
 && find / -xdev -perm -2000 -type f -exec chmod g-s {} + 2>/dev/null || true

# Templates & scripts
COPY odoo.conf.tmpl /etc/odoo/odoo.conf.tmpl
COPY entrypoint.sh /usr/local/bin/custom-entrypoint.sh
COPY healthcheck.sh /usr/local/bin/custom-healthcheck.sh
RUN chmod 0755 /usr/local/bin/custom-entrypoint.sh /usr/local/bin/custom-healthcheck.sh \
 && chown odoo:odoo /etc/odoo/odoo.conf.tmpl

USER odoo

# Healthcheck handled by compose, but keep image-level fallback
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=60s \
  CMD ["/usr/local/bin/custom-healthcheck.sh"]

ENTRYPOINT ["/usr/local/bin/custom-entrypoint.sh"]
CMD ["odoo"]
