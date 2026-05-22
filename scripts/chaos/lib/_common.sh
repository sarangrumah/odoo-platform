#!/usr/bin/env bash
# Shared helpers for chaos drill scripts.

set -euo pipefail

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . .env; set +a
fi

PROJECT="${COMPOSE_PROJECT_NAME:-odoo19-platform}"
COMPOSE_CMD="docker compose"

color_red()    { printf '\033[31m%s\033[0m\n' "$*"; }
color_green()  { printf '\033[32m%s\033[0m\n' "$*"; }
color_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
color_cyan()   { printf '\033[36m%s\033[0m\n' "$*"; }

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

snapshot_state() {
  color_cyan "== Snapshot @ $(now_iso) =="
  docker ps --filter "name=${PROJECT}-" \
    --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || true
  echo
}

wait_healthy() {
  local svc="$1"
  local timeout="${2:-120}"
  local elapsed=0
  while [ "$elapsed" -lt "$timeout" ]; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' \
      "${PROJECT}-${svc}" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ]; then
      color_green "  ${svc}: healthy (after ${elapsed}s)"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  color_red "  ${svc}: still not healthy after ${timeout}s — investigate"
  return 1
}

drill_report() {
  local name="$1" start="$2" end="$3" outcome="$4"
  echo
  color_cyan "== Drill Report =="
  echo "  Name:    $name"
  echo "  Started: $start"
  echo "  Ended:   $end"
  echo "  Outcome: $outcome"
  echo
  echo "Paste into docs/runbooks/disaster-recovery.md appendix."
}
