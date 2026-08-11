#!/usr/bin/env bash
# Open an SSH tunnel to Odoo's database manager and print how to use it.
#
# Run this FROM YOUR WORKSTATION, not on the platform host.
#
# Why this exists: https://<domain>/web/database/manager answers 403, and that is
# the design, not a fault. The front door deliberately refuses the database
# manager -- see caddy/Caddyfile, the `handle /web/database/*` block -- because
# before that block existed the root of the public host served Odoo's database
# selector, i.e. the name of every tenant database plus create/drop/restore, to
# any anonymous visitor.
#
# The real manager runs in the `odoo-mgmt` container (LIST_DB=True, dbfilter
# ^.*$), bound to 127.0.0.1:18079 on the host and published nowhere else. Only
# 80 and 443 are NATed to that box anyway, so a tunnel is the only way in and
# the only way that keeps it off the internet.
#
# Full procedure and the traps around backup/restore:
#   docs/runbooks/database-manager-access.md
#
# TWO host details that are not the defaults, and cost a round trip when this
# script was first written against them:
#
#   * sshd listens on 2221, not 22. `ssh odoo-erp@192.168.3.140` with no -p
#     answers "Connection refused", which reads like the host being down.
#   * sshd used to carry a GLOBAL `DisableForwarding yes`, which overrides every
#     other forwarding option and refuses `-L` for everyone. It is now scoped to
#     the `sftpusers` group (the SFTP share accounts it was meant for), so
#     ordinary accounts can forward. If a forward is ever refused with
#     "administratively prohibited", that scoping has been reverted -- check
#     `sshd -T -C user=<you>,host=localhost,addr=127.0.0.1 | grep -i forwarding`
#     on the host.
#
# Usage:
#   scripts/ops/db-manager-tunnel.sh
#   ODOO_HOST=odoo-erp@192.168.3.140 ODOO_SSH_PORT=2221 ODOO_MGMT_PORT=18079 \
#     scripts/ops/db-manager-tunnel.sh
#
# Ctrl-C closes the tunnel.

set -euo pipefail

HOST="${ODOO_HOST:-odoo-erp@192.168.3.140}"
SSH_PORT="${ODOO_SSH_PORT:-2221}"
PORT="${ODOO_MGMT_PORT:-18079}"
URL="http://localhost:${PORT}/web/database/manager"

port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}"
  elif command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "${PORT}" >/dev/null 2>&1
  else
    return 1
  fi
}

banner() {
  cat <<EOF

  Database manager : ${URL}
  Master password  : ssh -p ${SSH_PORT} ${HOST} 'grep ^ODOO_ADMIN_PASSWD= /opt/odoo-platform/.env'

  Before you drop, restore or duplicate anything on a production database, take
  a dump first -- docs/runbooks/backup-restore.md.

EOF
}

if port_in_use; then
  echo "Local port ${PORT} is already listening -- an earlier tunnel is probably still up."
  echo "Not opening a second one."
  banner
  exit 0
fi

# EXIT only, and no `exec` below: an exec'd ssh replaces this shell, and the trap
# would never fire.
trap 'echo; echo "Tunnel closed."' EXIT

echo "Opening tunnel to ${HOST}:${SSH_PORT} (local ${PORT} -> 127.0.0.1:${PORT}) ..."
banner
echo "  Ctrl-C to close."
echo

# -N: no remote command, this is a forward and nothing else.
# ExitOnForwardFailure: fail loudly if the forward cannot be set up, rather than
# sitting there looking connected while the browser gets connection refused.
ssh -N \
  -p "${SSH_PORT}" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L "127.0.0.1:${PORT}:127.0.0.1:${PORT}" \
  "${HOST}"
