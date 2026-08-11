#!/usr/bin/env bash
# Login banner for backup trouble. Installed as /etc/update-motd.d/99-odoo-backup-alert.
#
# Why a banner: the verifier's only outbound channel is WhatsApp, and on 11-Aug-2026
# it answered 409 "session not connected" -- the session had been logged out since
# 4-Aug. The alert was written to $DEST/ALERT and nobody read it. SSH is where the
# people who run this host actually turn up, so the alert is put in their way.
#
# It also catches the failure no in-script alert can: if the cron itself stops
# firing, nothing runs to complain. Hence the staleness check, which depends on
# the age of the backups rather than on anything the backup job does.
#
# Prints nothing when all is well. Must never fail a login, so every step is
# guarded and the script always exits 0.
set -u

DEST=/opt/db-backups/auto
ALERT_FILE="$DEST/ALERT"
STALE_HOURS=30   # nightly job runs 02:30; 30h means one missed night, not a late run

if [ -r "$ALERT_FILE" ]; then
    printf '\n\033[1;31m%s\033[0m\n' "=== BACKUP ODOO BERMASALAH ==="
    cat "$ALERT_FILE" 2>/dev/null
    printf '%s\n\n' "(hilang sendiri begitu pg_backup_check.sh lolos)"
    exit 0
fi

newest=$(find "$DEST/daily" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -1)
if [ -z "$newest" ]; then
    printf '\n\033[1;31m%s\033[0m\n\n' "=== BACKUP ODOO: tidak ada set harian sama sekali di $DEST/daily ==="
    exit 0
fi

if [ -z "$(find "$newest" -maxdepth 0 -mmin -$((STALE_HOURS * 60)) 2>/dev/null)" ]; then
    printf '\n\033[1;31m%s\033[0m\n' "=== BACKUP ODOO BASI ==="
    printf 'Set terbaru: %s (lebih tua dari %d jam).\n' "$(basename "$newest")" "$STALE_HOURS"
    printf 'Cron 02:30 mungkin mati: systemctl status cron; tail /var/log/odoo-pg-backup.log\n\n'
fi

exit 0
