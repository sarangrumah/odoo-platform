# syntax=docker/dockerfile:1.7
# ============================================================
# Hardened Odoo 19 image
# - Pinned to a specific digest (build 19.0-20260528) so the rolling
#   `odoo:19.0` tag cannot silently swap the base under a running DB,
#   which previously caused a stale-registry settings crash
#   ("res.config.settings"."email_primary_color" field is undefined).
#   To bump: `docker pull odoo:19.0`, verify, then update the digest below.
# - Adds xmlsec for XAdES sertel signing (Coretax)
# - Strips SUID, runs as non-root odoo user (already in base)
# ============================================================

FROM odoo:19.0@sha256:b81c76750665681327f0193afcc8a54ed0348e8cac3bdaef1b7f4abea5471eed

USER root

# System deps for: git (OCA fetch), curl (healthcheck), gettext-base (envsubst),
# xmlsec1 (Coretax XML signing), build deps for cryptography wheels.
#
# The second apt call patches the OS openssl family to the distro's fixed build
# (e.g. CVE-2026-45447, PKCS7_verify heap use-after-free). It's a targeted
# `--only-upgrade` of just the flagged packages rather than a blanket
# `apt-get upgrade`, so Odoo's pinned python3-* apt packages are left untouched.
# This is compatible with the base-digest pin above: that pin protects the Odoo
# application layer, not OS libraries. `--only-upgrade` skips any name that
# isn't already installed, so the list is safe across base rebuilds.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      curl \
      gettext-base \
      xmlsec1 \
      libxmlsec1-dev \
      libxmlsec1-openssl \
      ca-certificates \
 && apt-get install -y --no-install-recommends --only-upgrade \
      openssl \
      libssl3t64 \
      libssl-dev \
 && rm -rf /var/lib/apt/lists/* \
 && update-ca-certificates

# Python deps tambahan (HTTP client for AI gateway, encryption, XML validation)
COPY requirements.txt /tmp/requirements.txt
# --ignore-installed: base image ships some deps (cryptography, phonenumbers,
# python-dateutil) via the Debian python3-* apt packages which lack pip RECORD
# files. Without this flag, pip aborts when trying to uninstall them.
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed \
       -r /tmp/requirements.txt \
 && rm -f /tmp/requirements.txt

# The base image ships rtlcss (Odoo's RTL asset generator) with a nested
# postcss 8.5.15, vulnerable to GHSA-r28c-9q8g-f849 (path traversal via
# sourceMappingURL). rtlcss is already at its latest 4.3.0 — only the nested
# dep is stale, and its range (^8.4.21) accepts the fix. Drop the nested copy
# and pin the patched postcss as a sibling in the global node_modules, which
# rtlcss resolves upward to. Pinned, not @latest, so rebuilds are deterministic.
# Deleting the nested postcss orphans the deps npm had installed FOR it —
# nanoid and source-map-js stay behind in rtlcss/node_modules with nothing
# resolving to them, and the stale nanoid 3.3.12 keeps failing the image scan
# (CVE-2026-67213/67214). rtlcss itself depends on neither; the sibling postcss
# brings its own patched copies. So the orphans go with it.
RUN rm -rf /usr/local/lib/node_modules/rtlcss/node_modules/postcss \
           /usr/local/lib/node_modules/rtlcss/node_modules/nanoid \
           /usr/local/lib/node_modules/rtlcss/node_modules/source-map-js \
 && npm install -g --no-audit --no-fund postcss@8.5.25 \
 && npm cache clean --force

# Strip SUID binaries (CIS hardening)
RUN find / -xdev -perm -4000 -type f -exec chmod u-s {} + 2>/dev/null || true \
 && find / -xdev -perm -2000 -type f -exec chmod g-s {} + 2>/dev/null || true

# Templates & scripts
# Template lives in /usr/local/share so it survives a tmpfs mount of /etc/odoo
# under prod's read_only rootfs. The legacy /etc/odoo copy stays as a fallback
# for the dev compose where /etc/odoo isn't shadowed.
COPY odoo.conf.tmpl /usr/local/share/odoo.conf.tmpl
COPY odoo.conf.tmpl /etc/odoo/odoo.conf.tmpl
COPY entrypoint.sh /usr/local/bin/custom-entrypoint.sh
COPY healthcheck.sh /usr/local/bin/custom-healthcheck.sh
RUN chmod 0755 /usr/local/bin/custom-entrypoint.sh /usr/local/bin/custom-healthcheck.sh \
 && chmod 0644 /usr/local/share/odoo.conf.tmpl \
 && chown odoo:odoo /etc/odoo/odoo.conf.tmpl

USER odoo

# Healthcheck handled by compose, but keep image-level fallback
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=60s \
  CMD ["/usr/local/bin/custom-healthcheck.sh"]

ENTRYPOINT ["/usr/local/bin/custom-entrypoint.sh"]
CMD ["odoo"]
