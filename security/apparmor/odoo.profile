## ==========================================================
## AppArmor profile — Custom Platform Odoo container (stub)
## ==========================================================
## Status: STUB / opt-in. Linux host with AppArmor enabled only.
## Macs / Windows hosts (Docker Desktop) silently ignore this.
##
## Load:
##   sudo apparmor_parser -r security/apparmor/odoo.profile
##
## Use in docker-compose.yml under the odoo service:
##   security_opt:
##     - apparmor=custom-platform-odoo
##
## See security/apparmor/README.md for details.
## ==========================================================

#include <tunables/global>

profile custom-platform-odoo flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/python>
  #include <abstractions/openssl>
  #include <abstractions/nameservice>

  # ----- Capabilities (Odoo binds 8069/8072 as non-root inside container) -----
  capability chown,
  capability dac_override,
  capability setgid,
  capability setuid,

  # Deny anything not whitelisted below
  deny capability sys_admin,
  deny capability sys_module,
  deny capability sys_rawio,
  deny capability sys_ptrace,
  deny capability mac_admin,
  deny capability mac_override,
  deny capability net_admin,
  deny capability net_raw,        # block raw sockets — no ICMP fingerprinting
  deny capability dac_read_search,
  deny capability fowner,
  deny capability setpcap,
  deny capability fsetid,
  deny capability ipc_owner,
  deny capability ipc_lock,
  deny capability lease,
  deny capability audit_write,
  deny capability audit_read,

  # ----- Filesystem -----
  # Read-only Odoo install
  /usr/lib/python3*/dist-packages/odoo/** r,
  /etc/odoo/** r,

  # Writable filestore + tmp (filestore mounted from host)
  /var/lib/odoo/** rwk,
  /tmp/** rwk,

  # Forbid touching /etc/passwd, /etc/shadow, /root, host /proc/sys
  deny /etc/shadow* rwklx,
  deny /etc/sudoers rwklx,
  deny /root/** rwklx,
  deny /proc/sys/kernel/** wklx,
  deny /sys/kernel/security/** rwklx,

  # ----- Networking -----
  network inet stream,
  network inet6 stream,
  network unix stream,
  network unix dgram,
  deny network raw,
  deny network packet,

  # ----- Mounts -----
  deny mount,
  deny umount,
  deny remount,
  deny pivot_root,

  # ----- ptrace / signals -----
  ptrace peer=custom-platform-odoo,
  signal (send,receive) peer=custom-platform-odoo,
  deny ptrace,

  # ----- Exec children (wkhtmltopdf, python subprocesses) -----
  /usr/bin/python3* ix,
  /usr/local/bin/python3* ix,
  /usr/bin/wkhtmltopdf ix,
  /usr/local/bin/custom-entrypoint.sh ix,
  /usr/local/bin/custom-healthcheck.sh ix,

  # Catch-all denies anything not explicitly allowed (AppArmor default for
  # implicit paths is deny when "complain" not set).
}
