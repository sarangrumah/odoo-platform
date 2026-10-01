#!/usr/bin/env bash
# Verify that the retail import pipeline actually moved data last night, and shout
# on WhatsApp if it did not.
#
# Why a separate checker: every surface the pipeline owns can look healthy while it
# is dead. On 10-Aug-2026 one POS session left open in the UI made every X24 sales
# import raise; the log rows stayed 'running' (the state is committed BEFORE the
# handler runs), the next hourly poll saw a duplicate hash and archived the file,
# and the feed reported last_status=ok. Files kept arriving, the archive kept
# filling, cron stayed green -- and prd_levis_begbal did not book a single sale for
# eight days. Nobody noticed until somebody asked.
#
# So this asserts the properties that matter from OUTSIDE Odoo, in the order they
# bite:
#   1. no import stuck in 'running' (a dead run that also blocks re-import)
#   2. no import that ended 'failed' in the last day
#   3. no active feed reporting last_status=error
#   4. the daily feeds (X24/X70D/X31) actually imported something in the last 26h
#   5. POS sales are not stale: a database that sold in the last 30 days must have
#      sold in the last 48h
#   6. every trading day's tender detail (X70D) covers that day's sales (X24)
#   7. every trading day's GL settlement (RIREC) equals that day's sales -- in BOTH
#      directions, so an over-posted receivable is caught too
#   8. no store is sending a trans_date this importer cannot parse
#
# Check 5 is the one that would have caught August on day one: it measures the
# OUTCOME (rows in pos_order), not the machinery's opinion of itself. Its blind
# spot is deliberate -- a database with no sales at all for 30 days is treated as
# dormant rather than broken, otherwise every frozen demo tenant alerts forever.
#
# Checks 6-8 exist because on 01-Oct-2026 all five checks above were green while
# Rp 2,59 M of September tender detail was simply absent: X-center's nightly X70D
# kept arriving on time and kept shrinking, carrying 207 of the day's 307 sales.
# Nothing in the pipeline compares the two sides, so nothing noticed for ten days.
# The same blindness hid an over-posted receivable (29-Sep, Rp 3.849.700: X70D
# omitted a void that X70T reported as a negative, and the settlement's `> 0` clamp
# discarded it) and 4.936 staged rows whose date never parsed.
#
# Do NOT try to read health off retail_import_log.state for X24DN/X70D. Cron 46
# ("Levi's nightly full-auto") rewrites every 'imported' log of those two profiles
# to 'partial' every hour -- a workaround for an older self-blocking guard that no
# longer exists. So 'partial' is the normal resting state there and says nothing
# about whether the data arrived. Checks 6 and 7 measure the data instead.
#
# Read-only apart from its own ALERT marker and the per-store date-dialect baseline
# in $STATE_DIR: it opens no transaction that writes.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
PG_CONTAINER="${PG_CONTAINER:-odoo19-platform-postgres}"
BAILEYS_URL="${BAILEYS_URL:-http://127.0.0.1:18088}"
ALERT_FILE="${ALERT_FILE:-/opt/db-backups/auto/ALERT-retail-import}"
STUCK_HOURS="${STUCK_HOURS:-6}"
FEED_SILENT_HOURS="${FEED_SILENT_HOURS:-26}"
SALES_STALE_HOURS="${SALES_STALE_HOURS:-48}"
# Feeds expected to deliver EVERY night. Matched against retail_import_feed.file_glob;
# the occasional feeds (X101 master, CoA, X20) must not alert when they stay quiet.
DAILY_GLOBS="${DAILY_GLOBS:-X24%,X70D%,X31%}"
# Reconciliation window for checks 6-8, in days ago. The newest day is deliberately
# excluded: X70T tops a day up hours after X70D, and a manual backfill lands later
# still, so judging D-1 would flap every morning on money that is about to arrive.
RECON_FROM_DAYS="${RECON_FROM_DAYS:-8}"
RECON_TO_DAYS="${RECON_TO_DAYS:-2}"
# Rupiah tolerance per trading day. Big enough to ignore rounding, small enough that
# a single voided card transaction (the 29-Sep case was Rp 3,8 jt) still alerts.
RECON_TOL="${RECON_TOL:-100000}"
STATE_DIR="${STATE_DIR:-/opt/db-backups/auto}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
PGUSER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
PGUSER="${PGUSER:-odoo}"

problems=()

psql_q() { # db, sql -> tab-separated rows on stdout
  docker exec -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
    psql -U "$PGUSER" -d "$1" -Atq -c "$2" 2>/dev/null
}

# Same thing, but a query that FAILS becomes a problem instead of an empty result.
# psql_q discards stderr, and `psql -c` exits 0 on a SQL error, so a typo in a check
# reads exactly like "nothing wrong" -- which is how the date-dialect check below
# shipped broken the first time (GROUP BY 1 over an aggregate). A monitor that goes
# quiet when it breaks is worse than no monitor.
psql_chk() { # db, label, sql -> rows on stdout; appends to $problems on error
  local out err
  err="$(mktemp)"
  out="$(docker exec -e PGPASSWORD="$PGPASSWORD" "$PG_CONTAINER" \
          psql -U "$PGUSER" -d "$1" -Atq -v ON_ERROR_STOP=1 -c "$3" 2>"$err")"
  if [ -s "$err" ]; then
    problems+=("[$1] CEK GAGAL ($2): $(head -c 200 "$err" | tr '\n' ' ')")
  fi
  rm -f "$err"
  # Trailing newline matters: the callers feed this to `while read`, which drops a
  # final line that has none -- one finding per database, silently.
  printf '%s\n' "$out"
}

if [ -z "$PGPASSWORD" ]; then
  problems+=("tidak bisa membaca POSTGRES_PASSWORD dari $ENV_FILE")
else
  dbs="$(psql_q postgres "SELECT datname FROM pg_database WHERE NOT datistemplate AND datallowconn ORDER BY 1")"
  for db in $dbs; do
    has="$(psql_q "$db" "SELECT to_regclass('public.retail_import_feed') IS NOT NULL")"
    [ "$has" = "t" ] || continue

    # Only databases that actually RUN the pipeline, not the many clones that merely
    # carry its configuration. Every restored copy of a tenant keeps the feeds, the
    # profiles and x24_post_enabled, so those are useless as a discriminator -- an
    # alert that lists rnd_/tst_/demo_ every morning is an alert nobody reads.
    #
    # Two signals, either one qualifies:
    #   - an ACTIVE mailbox: the nightly mail ingest runs here (prd_levis_begbal)
    #   - a feed that imported something in the last 7 days: covers SFTP-only tenants
    #     and lets a new tenant enrol itself simply by working
    # The 7-day clause means a database broken for longer drops out of monitoring --
    # acceptable, because it can only get there after alerting every day for a week.
    monitored="$(psql_q "$db" "
      SELECT (SELECT count(*) FROM retail_import_mailbox WHERE active) > 0
          OR (SELECT count(*) FROM retail_import_log
               WHERE imported_at > now() - interval '7 days') > 0")"
    [ "$monitored" = "t" ] || continue

    globs="$(printf "'%s'," ${DAILY_GLOBS//,/ })"; globs="${globs%,}"

    while IFS= read -r line; do
      [ -n "$line" ] && problems+=("[$db] $line")
    done < <(psql_q "$db" "
      SELECT 'impor MACET: log ' || id || ' ' || coalesce(filename, '?')
             || ' masih running sejak ' || to_char(coalesce(started_at, imported_at), 'DD-Mon HH24:MI')
        FROM retail_import_log
       WHERE state = 'running'
         AND coalesce(started_at, imported_at) < now() - interval '${STUCK_HOURS} hours'
      UNION ALL
      SELECT 'impor GAGAL: log ' || id || ' ' || coalesce(filename, '?')
             || ' — ' || left(coalesce(error_message, ''), 100)
        FROM retail_import_log
       WHERE state = 'failed'
         AND coalesce(finished_at, imported_at) > now() - interval '24 hours'
      UNION ALL
      SELECT 'feed ERROR: ' || name || ' — ' || left(coalesce(last_message, ''), 100)
        FROM retail_import_feed
       WHERE active AND last_status = 'error'
      UNION ALL
      SELECT 'feed DIAM: ' || f.name || ' — impor terakhir '
             || coalesce(to_char(max(l.imported_at), 'DD-Mon HH24:MI'), 'tidak pernah')
        FROM retail_import_feed f
        LEFT JOIN retail_import_log l ON l.profile_id = f.profile_id
       WHERE f.active AND f.file_glob LIKE ANY (ARRAY[${globs}])
       GROUP BY f.id, f.name
      HAVING coalesce(max(l.imported_at), timestamp '1970-01-01')
             < now() - interval '${FEED_SILENT_HOURS} hours'
    ")

    # Outcome check: sales themselves, not the importer's opinion of them.
    if [ "$(psql_q "$db" "SELECT to_regclass('public.pos_order') IS NOT NULL")" = "t" ]; then
      stale="$(psql_q "$db" "
        SELECT 'PENJUALAN BASI: pos_order terakhir ' || to_char(max(date_order), 'DD-Mon-YYYY')
               || ' (' || count(*) || ' order dalam 30 hari)'
          FROM pos_order
         WHERE date_order > now() - interval '30 days'
        HAVING max(date_order) < now() - interval '${SALES_STALE_HOURS} hours'
      ")"
      [ -n "$stale" ] && problems+=("[$db] $stale")
    fi

    # Checks 6-8 ask whether the books reconcile, which is only a question where the
    # pipeline is still being fed. The gate above (checks 1-5) deliberately admits a
    # database that merely imported something in the last 7 days, so a clone keeps
    # being watched for a week after it was restored -- right for "did the importer
    # die", wrong here: a frozen copy's gap is history, not an incident, and
    # demo_levis_wms alone contributed six lines that would bury the real tenant.
    # An active mailbox or an active feed is what separates the two.
    fed="$(psql_q "$db" "
      SELECT (SELECT count(*) FROM retail_import_mailbox WHERE active) > 0
          OR (SELECT count(*) FROM retail_import_feed WHERE active) > 0")"
    [ "$fed" = "t" ] || continue

    # ---- checks 6-7: does the money reconcile, day by day? ------------------
    # Only where the X70D settlement is actually in play. A tenant that merely
    # carries the profiles has no RIREC journal and must not alert.
    if [ "$(psql_q "$db" "
          SELECT to_regclass('public.account_move_line') IS NOT NULL
             AND EXISTS (SELECT 1 FROM retail_import_profile WHERE file_type = 'x70d')")" = "t" ]; then
      while IFS= read -r line; do
        [ -n "$line" ] && problems+=("[$db] $line")
      done < <(psql_chk "$db" "rekonsiliasi harian" "
        -- X24 is the baseline for what was sold, deduplicated per transaction by
        -- newest log exactly like retail_import_recon does. The same nightly file
        -- does get imported twice (25-Jul and 29-Jul 2026 each sit in two logs) and
        -- summing both would report every day as half-settled, every day.
        WITH x24 AS MATERIALIZED (
          SELECT d, sum(amt) AS a24 FROM (
            SELECT (r.trans_date)::date AS d, (r.total_amount)::numeric AS amt,
                   dense_rank() OVER (PARTITION BY r.store_code, r.trans_date,
                                                   coalesce(nullif(r.register,''),'1'), r.transnum
                                      ORDER BY g.id DESC) AS rk
              FROM retail_import_line l
              JOIN retail_import_log g ON g.id = l.log_id
              CROSS JOIN LATERAL json_to_record(l.raw_data_json::json)
                   r(store_code text, register text, transnum text, trans_date text, total_amount text)
             WHERE g.file_type = 'x24'
               AND g.imported_at > now() - interval '60 days'
               AND l.raw_data_json ~ '^\{'
               AND r.trans_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
               AND r.total_amount ~ '^-?[0-9]+([.][0-9]+)?\$'
               AND (r.trans_date)::date BETWEEN current_date - ${RECON_FROM_DAYS}
                                            AND current_date - ${RECON_TO_DAYS}
          ) z WHERE rk = 1 GROUP BY d
        ),
        -- The tender detail the per-transaction reconciliation and the MDR acquirer
        -- lookup read: every log of a x70d profile, including manual backfills.
        x70 AS MATERIALIZED (
          SELECT d, sum(amt) AS a70 FROM (
            SELECT (r.trans_date)::date AS d, (r.tender_amount)::numeric AS amt,
                   dense_rank() OVER (PARTITION BY r.store_code, r.trans_date,
                                                   coalesce(nullif(r.register,''),'1'), r.transnum
                                      ORDER BY g.id DESC) AS rk
              FROM retail_import_line l
              JOIN retail_import_log g ON g.id = l.log_id
              CROSS JOIN LATERAL json_to_record(l.raw_data_json::json)
                   r(store_code text, register text, transnum text, trans_date text,
                     tender_type text, tender_amount text)
             WHERE g.file_type = 'x70d'
               AND g.imported_at > now() - interval '60 days'
               AND l.raw_data_json ~ '^\{'
               AND coalesce(r.tender_type,'') <> ''
               AND r.trans_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
               AND r.tender_amount ~ '^-?[0-9]+([.][0-9]+)?\$'
               AND (r.trans_date)::date BETWEEN current_date - ${RECON_FROM_DAYS}
                                            AND current_date - ${RECON_TO_DAYS}
          ) z WHERE rk = 1 GROUP BY d
        ),
        gl AS (
          SELECT aml.date AS d, sum(aml.debit) - sum(aml.credit) AS net
            FROM account_move_line aml
            JOIN account_move m ON m.id = aml.move_id
            JOIN account_journal j ON j.id = aml.journal_id
            JOIN account_account aa ON aa.id = aml.account_id
           WHERE j.code = 'RIREC' AND m.state = 'posted'
             AND aa.name->>'en_US' LIKE 'POS Receivable - %'
             AND aml.date BETWEEN current_date - ${RECON_FROM_DAYS}
                              AND current_date - ${RECON_TO_DAYS}
           GROUP BY 1
        )
        SELECT 'DETAIL TENDER KURANG ' || to_char(x.d, 'DD-Mon') || ': terjual Rp '
               || replace(to_char(round(x.a24), 'FM999,999,999,999'), ',', '.')
               || ' tapi tender hanya Rp '
               || replace(to_char(round(coalesce(v.a70,0)), 'FM999,999,999,999'), ',', '.')
               || ' — selisih Rp '
               || replace(to_char(round(x.a24 - coalesce(v.a70,0)), 'FM999,999,999,999'), ',', '.')
          FROM x24 x LEFT JOIN x70 v ON v.d = x.d
         WHERE x.a24 - coalesce(v.a70,0) > ${RECON_TOL}
        UNION ALL
        SELECT 'SETTLEMENT GL '
               || CASE WHEN coalesce(g.net,0) > x.a24 THEN 'KELEBIHAN ' ELSE 'KURANG ' END
               || to_char(x.d, 'DD-Mon') || ': terjual Rp '
               || replace(to_char(round(x.a24), 'FM999,999,999,999'), ',', '.')
               || ' tapi RIREC Rp '
               || replace(to_char(round(coalesce(g.net,0)), 'FM999,999,999,999'), ',', '.')
               || ' — selisih Rp '
               || replace(to_char(round(abs(coalesce(g.net,0) - x.a24)), 'FM999,999,999,999'), ',', '.')
          FROM x24 x LEFT JOIN gl g ON g.d = x.d
         WHERE abs(coalesce(g.net,0) - x.a24) > ${RECON_TOL}
      ")
    fi

    # ---- check 8: a trans_date this importer cannot parse -------------------
    # No layer blocks one. require_fields only asks that the cell be non-blank, and
    # _parse_date returns False rather than raising -- so '04.09.2026', an Excel
    # serial like 46277, a '-' or a cashier id all stage happily with error_count 0
    # and the row silently never matches anything. Worse, a cell Excel already typed
    # as a date is taken verbatim, so a workbook authored month-first lands in the
    # wrong month without a trace (80680's 12/09 became 2026-12-09).
    #
    # Alert on a NEW source only, against a baseline of the ones already known. The
    # store exports are cumulative from the 1st, so a broken template re-sends its bad
    # rows every night and its row count climbs as the month fills -- keying the
    # baseline on counts would fire every single day and train everyone to skip the
    # whole message. The actionable unit is the source, not the volume: either a
    # store's template needs fixing or it does not. Counts ride along for context.
    # Keyed on store_code, tab-separated: some of these workbooks have their columns
    # shifted, so store_code itself comes back holding a date or a store name --
    # values with spaces in them, which a space-delimited key would split in half.
    dialect="$(psql_chk "$db" "tanggal tidak terbaca" "
      SELECT store_code || E'\t' || n FROM (
        SELECT coalesce(nullif(r.store_code,''),'?') AS store_code, count(*) AS n
          FROM retail_import_line l
          JOIN retail_import_log g ON g.id = l.log_id
          CROSS JOIN LATERAL json_to_record(l.raw_data_json::json)
               r(store_code text, trans_date text)
         WHERE g.imported_at > now() - interval '48 hours'
           AND l.raw_data_json ~ '^\{'
           AND coalesce(r.trans_date,'') <> ''
           AND r.trans_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         GROUP BY 1) z ORDER BY n DESC, store_code")"
    state_file="$STATE_DIR/retail-import-datedialect-$db.state"
    if [ -n "$dialect" ]; then
      # Name the worst few and total the rest: a broken template can affect a dozen
      # keys at once and a message nobody can read is a message nobody acts on.
      grown="$(printf '%s\n' "$dialect" | awk -F'\t' -v sf="$state_file" '
        BEGIN { FS = "\t"; while ((getline l < sf) > 0) { split(l, a, "\t"); was[a[1]] = 1 } }
        $1 != "" && !($1 in was) {
          n++; rows += $2
          if (n <= 5) names = names (names ? ", " : "") $1 " (" $2 " baris)"
        }
        END { if (n) printf "%d sumber baru, %d baris — %s%s", n, rows, names,
                            (n > 5 ? ", dan " (n - 5) " lainnya" : "") }')"
      [ -n "$grown" ] && problems+=("[$db] TANGGAL TIDAK TERBACA: $grown. Ekspor toko memakai format lain (dd.mm.yyyy / serial Excel / kolom bergeser) — baris itu tidak akan pernah cocok saat rekonsiliasi, dan impornya tetap dilaporkan sukses")
    fi
    # The baseline accumulates rather than being replaced. Several stores send weekly,
    # so their file drops out of the 48h window for days at a time; replacing the
    # baseline would forget them and re-alert on every delivery. The cost is that a
    # store fixed and later broken again goes unannounced here -- acceptable, because
    # checks 6 and 7 measure the money and would catch whatever it costs. This check
    # only exists to point at the cause sooner.
    if [ -d "$STATE_DIR" ] && [ -n "$dialect" ]; then
      { [ -f "$state_file" ] && cat "$state_file"; printf '%s\n' "$dialect" | cut -f1; } \
        | sort -u > "$state_file.tmp" 2>/dev/null \
        && mv -f "$state_file.tmp" "$state_file" 2>/dev/null || true
    fi
  done
fi

# ---- alerting ---------------------------------------------------------------
# Same plumbing as pg_backup_check.sh: WhatsApp is best-effort (that session has
# gone logged-out before and the alert reached nobody), the RECORD is not -- every
# verdict goes to syslog, and a failing one leaves $ALERT_FILE behind.

send_wa() {
  local text="$1" secret to session code
  # Temporary kill switch: with ALERT_WHATSAPP_DISABLED=1 in .env the alert is
  # still written to this script's log, only the WhatsApp send is skipped. Set
  # it while the baileys session is unpaired so a dead channel does not fill the
  # log with http=409, and REMOVE it once the session is paired again.
  if grep -qE '^ALERT_WHATSAPP_DISABLED=1' "$ENV_FILE" 2>/dev/null; then
    log "WA: dimatikan sementara (ALERT_WHATSAPP_DISABLED=1) — isi peringatan ada di log ini"
    return 1
  fi
  secret="$(grep -E '^BAILEYS_SHARED_SECRET=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  to="$(grep -E '^ALERT_WHATSAPP_TO=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="$(grep -E '^ALERT_WHATSAPP_SESSION=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="${session:-acct-2}"
  if [ -z "$secret" ] || [ -z "$to" ]; then
    log "WA: dilewati — BAILEYS_SHARED_SECRET atau ALERT_WHATSAPP_TO kosong"
    return 1
  fi
  code="$(curl -s -m 20 -o /tmp/retail_import_check_wa.$$ -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $secret" -H 'Content-Type: application/json' \
    --data-raw "$(printf '{"to":"%s","type":"text","text":%s}' "$to" \
                  "$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
    "$BAILEYS_URL/sessions/$session/messages")"
  if [ "$code" = "200" ]; then
    log "WA: terkirim ke $to"
    rm -f /tmp/retail_import_check_wa.$$
    return 0
  fi
  log "WA: GAGAL http=$code body=$(head -c 200 /tmp/retail_import_check_wa.$$ 2>/dev/null)"
  rm -f /tmp/retail_import_check_wa.$$
  return 1
}

host="$(hostname -s)"
if [ "${#problems[@]}" -eq 0 ]; then
  log "OK — tidak ada impor macet/gagal, feed harian jalan, penjualan segar"
  rm -f "$ALERT_FILE"
  logger -t odoo-retail-import -p daemon.info -- "OK retail import sehat" 2>/dev/null || true
  exit 0
fi

msg="⚠️ IMPOR RETAIL BERMASALAH ($host)
$(date '+%d-%b-%Y %H:%M')

$(printf '• %s\n' "${problems[@]}")

Cek: /var/log/odoo-retail-import-check.log
Session POS yang terbuka memblokir impor X24 — cek dulu:
  SELECT id, state FROM pos_session WHERE state <> 'closed';"

log "MASALAH:"
printf '  - %s\n' "${problems[@]}"
printf '%s\n' "$msg" > "$ALERT_FILE"
logger -t odoo-retail-import -p daemon.err -- "$(printf '%s' "$msg" | tr '\n' ' ')" 2>/dev/null || true
send_wa "$msg"
exit 1
