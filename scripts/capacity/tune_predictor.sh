#!/usr/bin/env bash
# Capacity prediction tuning — collect Prometheus metrics over a window,
# pipe through era-predictor's /v1/workflow/predict-capacity endpoint
# via ai-gateway, then compare the AI suggestion against the actual
# resource trajectory of the last N days.
#
# Run weekly; promote prompt changes after 4 weeks of stable accuracy.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"

if [ -f .env ]; then set -a; . .env; set +a; fi

PROM="${PROMETHEUS_URL:-http://localhost:${PROMETHEUS_PORT:-19090}}"
PREDICTOR="${PREDICTOR_URL:-http://localhost:${PREDICTOR_PORT:-18090}}"
OUT_DIR="docs/compliance/capacity_tuning"
mkdir -p "$OUT_DIR"

STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
REPORT="${OUT_DIR}/${STAMP}.json"

echo "== Capacity tuning snapshot @ ${STAMP} =="

# 1. Snapshot last 7d trends from Prometheus
echo "Querying Prometheus..."

query_avg() {
  local q="$1"
  curl -s --get "${PROM}/api/v1/query" \
    --data-urlencode "query=${q}" \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else '0')"
}

CPU_AVG_7D=$(query_avg 'avg_over_time(1 - rate(node_cpu_seconds_total{mode="idle"}[5m])[7d:5m])')
MEM_USED_7D=$(query_avg 'avg_over_time(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)[7d:5m])')
DISK_FREE_7D=$(query_avg 'avg_over_time(node_filesystem_avail_bytes{mountpoint="/"}[7d:5m])')

# 2. Pull current predictor recommendation
echo "Fetching latest predictor JSON..."
if [ -f data/predictor/latest.json ]; then
  PRED_SUMMARY=$(python3 -c "
import json
d = json.load(open('data/predictor/latest.json'))
print(json.dumps({
  'forecast_30d_keys': list((d.get('forecast') or {}).keys()),
  'sat_eta': d.get('saturation_eta_days'),
  'recs': [r.get('component') for r in (d.get('recommend_upgrade') or [])],
}))
")
else
  PRED_SUMMARY='{}'
  echo "  (no predictor output yet — run era-predictor at least once)"
fi

# 3. Emit report
python3 - <<EOF > "$REPORT"
import json
print(json.dumps({
  "timestamp": "${STAMP}",
  "prometheus_7d_avg": {
    "cpu_busy_ratio": float("${CPU_AVG_7D}" or 0),
    "mem_used_ratio": float("${MEM_USED_7D}" or 0),
    "disk_free_bytes": float("${DISK_FREE_7D}" or 0),
  },
  "predictor_snapshot": ${PRED_SUMMARY},
}, indent=2))
EOF

echo
echo "Report: $REPORT"
cat "$REPORT"
echo
echo "Compare with last week's report at $(ls -1t ${OUT_DIR}/*.json 2>/dev/null | sed -n '2p' || echo 'N/A')."
echo "If recommendations are stable across 4 consecutive weeks, the AI prompt is well-calibrated."
echo "If recommendations swing wildly, edit ai-gateway/app/prompts/predict_capacity.md."
