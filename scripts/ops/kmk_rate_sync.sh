#!/usr/bin/env bash
# Pull the latest Kurs Pajak KMK from fiskal.kemenkeu.go.id and load it into the
# tenant databases that book in foreign currency.
#
# WHY THIS EXISTS
# ---------------
# Odoo converts a foreign-currency document with the newest res.currency.rate row
# whose date is <= the document date, and falls back to 1.0 when it finds none.
# There is no warning: a CN¥ 20,000 bill simply reads as Rp 20,000. On
# prd_arkaaim the whole rate table held ONE row until 19-Aug-2026, which is how
# two CN¥ bills got posted before anyone noticed the payment popup was proposing
# rupiah at 1:1.
#
# A rate table is therefore not a one-off load. It goes stale the week after you
# fill it, silently, and the symptom shows up as a wrong number in the ledger
# rather than as an error. This script keeps it current.
#
# WHAT IT DOES
# ------------
#   1. Reads the KMK listing page and takes the newest $BACKFILL_WEEKS PDFs.
#      More than one on purpose: if the box was down, or a run failed, the next
#      run heals the gap instead of leaving a hole that converts at a stale rate.
#   2. Extracts every currency from each decree (pdftotext -layout), keyed by the
#      period's FIRST day -- that is the date Odoo needs, since it carries a rate
#      forward until the next one.
#   3. Writes rows for the currencies each database actually has active, as
#      SHARED rows (company_id NULL). Idempotent: an existing row for the same
#      (currency, date) is left alone, never duplicated and never overwritten --
#      a rate that has already been used to post is history, not a typo.
#   4. Alerts if the newest decree is older than $MAX_AGE_DAYS (publication moved,
#      the page changed, or our fetch broke), or if a database run failed.
#
# NEVER writes a company-scoped row. Core orders its rate lookup by
# 'company_id.id, name DESC' (res_currency.py:126-129), so ANY company-scoped row
# outranks EVERY shared row regardless of date -- one stray row dated in July
# pinned prd_arkaaim's company 2 to that week's rate for all of August. The
# script reports such rows so they can be removed by hand.
#
# USAGE
#   scripts/ops/kmk_rate_sync.sh            # fetch + load
#   DRY_RUN=1 scripts/ops/kmk_rate_sync.sh  # fetch + show what it would write
#   DBS="prd_arkaaim trn_arkaaim" scripts/ops/kmk_rate_sync.sh
#
# Installed as /etc/cron.d/odoo-kmk-rate — see kmk_rate_sync.cron.

set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/odoo-platform/.env}"
MGMT_CONTAINER="${MGMT_CONTAINER:-odoo19-platform-odoo-mgmt}"
BAILEYS_URL="${BAILEYS_URL:-http://127.0.0.1:18088}"
ALERT_FILE="${ALERT_FILE:-/opt/db-backups/auto/ALERT-kmk-rate}"
LIST_URL="${LIST_URL:-https://fiskal.kemenkeu.go.id/peraturan/kmk-kurs-pajak}"
BASE_URL="${BASE_URL:-https://fiskal.kemenkeu.go.id}"
DBS="${DBS:-prd_arkaaim}"
# The listing page shows about five decrees, so raising this past 5 buys nothing --
# it pages, and this script does not. To load an older stretch (a fresh tenant, a
# backdated opening balance), use scripts/tenants/arkaaim/load_currency_rates.py,
# which takes an explicit list of dates.
BACKFILL_WEEKS="${BACKFILL_WEEKS:-4}"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-8}"
DRY_RUN="${DRY_RUN:-0}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

problems=()
WORK="$(mktemp -d /tmp/kmk-rate.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

command -v pdftotext >/dev/null 2>&1 || { log "FATAL: pdftotext tidak ada (apt install poppler-utils)"; exit 2; }

# ---- 1. daftar PDF terbaru --------------------------------------------------
list_code="$(curl -sS -m 40 -o "$WORK/list.html" -w '%{http_code}' "$LIST_URL")"
if [ "$list_code" != "200" ]; then
  problems+=("halaman daftar KMK menjawab http=$list_code ($LIST_URL)")
fi

mapfile -t links < <(grep -oE "/files/kurs/file/[0-9]+_[^\"']+\.pdf" "$WORK/list.html" 2>/dev/null \
                     | sort -u -t/ -k5 -r | head -n "$BACKFILL_WEEKS")

if [ "${#links[@]}" -eq 0 ]; then
  problems+=("tidak ada tautan PDF yang cocok di halaman daftar — pola tautan mungkin berubah")
fi

# ---- 2. unduh + baca --------------------------------------------------------
: > "$WORK/rates.tsv"   # date <TAB> CODE <TAB> idr_per_unit
i=0
for l in "${links[@]}"; do
  i=$((i + 1))
  f="$WORK/$i.pdf"
  code="$(curl -sS -m 60 -o "$f" -w '%{http_code}' "$BASE_URL$l")"
  if [ "$code" != "200" ]; then
    problems+=("unduh gagal http=$code untuk $l")
    continue
  fi
  if ! pdftotext -layout "$f" "$WORK/$i.txt" 2>/dev/null; then
    problems+=("pdftotext gagal untuk $l")
    continue
  fi
  python3 - "$WORK/$i.txt" >> "$WORK/rates.tsv" <<'PY'
import re, sys

BULAN = {
    "JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5, "JUNI": 6,
    "JULI": 7, "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10, "NOVEMBER": 11, "DESEMBER": 12,
}

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
flat = " ".join(text.split())

# The period's FIRST day is the date Odoo needs: it carries a rate forward until
# the next row, so one row per decree covers the whole week.
m = re.search(r"BERLAKU UNTUK TANGGAL (\d{1,2}) ([A-Z]+) (\d{4})", flat)
if not m:
    sys.stderr.write("no validity date found in %s\n" % sys.argv[1])
    raise SystemExit(1)
day, month, year = int(m.group(1)), BULAN.get(m.group(2)), int(m.group(3))
if not month:
    sys.stderr.write("unknown month %r\n" % m.group(2))
    raise SystemExit(1)
date = "%04d-%02d-%02d" % (year, month, day)

# e.g.  1. Rp    17.960,00   Untuk dolar Amerika Serikat (USD) 1,-
#      24. Rp     2.661,06   " renminbi Tiongkok (CNY)         1,-
rows = re.findall(r"^\s*\d+\.\s*Rp\s*([\d.]+,\d{2})\s+.*?\(([A-Z]{3})\)", text, re.M)
if not rows:
    sys.stderr.write("no rate lines parsed in %s\n" % sys.argv[1])
    raise SystemExit(1)

for amount, code in rows:
    value = float(amount.replace(".", "").replace(",", "."))
    if value <= 0:
        continue
    print("%s\t%s\t%.4f" % (date, code, value))
PY
  if [ "${PIPESTATUS[0]:-0}" != "0" ] && [ ! -s "$WORK/rates.tsv" ]; then
    problems+=("gagal membaca isi KMK dari $l")
  fi
done

parsed_dates="$(cut -f1 "$WORK/rates.tsv" 2>/dev/null | sort -u)"
newest="$(printf '%s\n' "$parsed_dates" | tail -1)"
log "periode terbaca: $(printf '%s' "$parsed_dates" | tr '\n' ' ')"

if [ -z "$newest" ]; then
  problems+=("tidak ada kurs yang berhasil dibaca sama sekali")
else
  age=$(( ( $(date +%s) - $(date -d "$newest" +%s) ) / 86400 ))
  log "KMK terbaru berlaku sejak $newest ($age hari lalu)"
  if [ "$age" -gt "$MAX_AGE_DAYS" ]; then
    problems+=("KMK terbaru sudah $age hari (>$MAX_AGE_DAYS) — publikasi atau pengambilan macet")
  fi
fi

# ---- 3. muat ke tiap database ----------------------------------------------
if [ -s "$WORK/rates.tsv" ]; then
  python3 - "$WORK/rates.tsv" > "$WORK/rates.json" <<'PY'
import json, sys
data = {}
for line in open(sys.argv[1]):
    date, code, value = line.rstrip("\n").split("\t")
    data.setdefault(date, {})[code] = float(value)
print(json.dumps(data))
PY

  for db in $DBS; do
    log "--- $db"
    {
      printf 'RATES = '
      cat "$WORK/rates.json"
      printf '\nDRY_RUN = %s\n' "$([ "$DRY_RUN" = "1" ] && echo True || echo False)"
      cat <<'PY'
Rate = env["res.currency.rate"]
company_currencies = set(env["res.company"].search([]).mapped("currency_id").ids)
wanted = env["res.currency"].search([("id", "not in", list(company_currencies))])
by_code = {c.name: c for c in wanted}
if not by_code:
    print("KMK: tidak ada mata uang asing aktif — tidak ada yang dimuat")
created = skipped = 0
for date in sorted(RATES):
    for code, idr_per_unit in sorted(RATES[date].items()):
        currency = by_code.get(code)
        if not currency or not idr_per_unit:
            continue
        if Rate.search_count([("currency_id", "=", currency.id), ("name", "=", date),
                              ("company_id", "=", False)]):
            skipped += 1
            continue
        print("KMK: + %s %s  1 %s = %s IDR" % (date, code, code, f"{idr_per_unit:,.2f}"))
        if not DRY_RUN:
            # Odoo stores the inverse direction (1 IDR = n foreign).
            Rate.create({"currency_id": currency.id, "name": date,
                         "rate": 1.0 / idr_per_unit, "company_id": False})
        created += 1
shadow = Rate.search([("company_id", "!=", False)])
for row in shadow:
    print("KMK: PERINGATAN baris ber-company %s %s company %s membajak semua tanggal sesudahnya"
          % (row.name, row.currency_id.name, row.company_id.id))
if DRY_RUN:
    env.cr.rollback()
    print("KMK: DRY RUN — %s akan dibuat, %s sudah ada" % (created, skipped))
else:
    env.cr.commit()
    print("KMK: DONE — %s dibuat, %s sudah ada" % (created, skipped))
PY
    } > "$WORK/payload-$db.py"

    if ! docker exec -i "$MGMT_CONTAINER" odoo shell -d "$db" \
           --no-http --max-cron-threads=0 --http-port=8987 --gevent-port=8988 \
           < "$WORK/payload-$db.py" > "$WORK/out-$db.log" 2>&1; then
      problems+=("$db: odoo shell keluar dengan error")
    fi
    grep -E '^KMK: ' "$WORK/out-$db.log" | while read -r line; do log "  $line"; done
    if ! grep -qE '^KMK: (DONE|DRY RUN)' "$WORK/out-$db.log"; then
      problems+=("$db: pemuatan kurs tidak selesai — lihat log")
      tail -5 "$WORK/out-$db.log" | while read -r line; do log "  ! $line"; done
    fi
    if grep -q '^KMK: PERINGATAN baris ber-company' "$WORK/out-$db.log"; then
      problems+=("$db: ada baris kurs ber-company yang membajak baris shared — hapus manual")
    fi
  done
fi

# ---- 4. vonis ---------------------------------------------------------------
# WhatsApp is best-effort (that session has been logged out before); the record is
# not -- every verdict goes to syslog and a failing one leaves $ALERT_FILE behind.
send_wa() {
  local text="$1" secret to session code
  secret="$(grep -E '^BAILEYS_SHARED_SECRET=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  to="$(grep -E '^ALERT_WHATSAPP_TO=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="$(grep -E '^ALERT_WHATSAPP_SESSION=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  session="${session:-acct-2}"
  if [ -z "$secret" ] || [ -z "$to" ]; then
    log "WA: dilewati — BAILEYS_SHARED_SECRET atau ALERT_WHATSAPP_TO kosong"
    return 1
  fi
  code="$(curl -s -m 20 -o "$WORK/wa.out" -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $secret" -H 'Content-Type: application/json' \
    --data-raw "$(printf '{"to":"%s","type":"text","text":%s}' "$to" \
                  "$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
    "$BAILEYS_URL/sessions/$session/messages")"
  if [ "$code" = "200" ]; then
    log "WA: terkirim ke $to"
    return 0
  fi
  log "WA: GAGAL http=$code body=$(head -c 200 "$WORK/wa.out" 2>/dev/null)"
  return 1
}

host="$(hostname -s)"
if [ "${#problems[@]}" -eq 0 ]; then
  log "OK — kurs KMK mutakhir sampai $newest"
  rm -f "$ALERT_FILE"
  logger -t odoo-kmk-rate -p daemon.info -- "OK kurs KMK sampai $newest" 2>/dev/null || true
  exit 0
fi

msg="⚠️ SINKRON KURS PAJAK KMK BERMASALAH ($host)
$(date '+%d-%b-%Y %H:%M')

$(printf '• %s\n' "${problems[@]}")

Akibatnya kurs bisa basi: dokumen mata uang asing dikonversi memakai kurs minggu
lama, atau 1:1 kalau tabelnya kosong — tanpa pesan error.

Log: /var/log/odoo-kmk-rate.log
Daftar KMK: $LIST_URL"

log "MASALAH:"
printf '  - %s\n' "${problems[@]}"
mkdir -p "$(dirname "$ALERT_FILE")" 2>/dev/null
printf '%s\n' "$msg" > "$ALERT_FILE"
logger -t odoo-kmk-rate -p daemon.err -- "$(printf '%s' "$msg" | tr '\n' ' ')" 2>/dev/null || true
send_wa "$msg"
exit 1
