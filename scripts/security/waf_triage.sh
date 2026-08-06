#!/usr/bin/env bash
# Triage the Coraza audit log before flipping WAF_MODE to On.
#
# The question this answers is not "what did the WAF catch" but "what would it
# have BROKEN". Those are different: an attack that scores 10 is the WAF working,
# while a successful user request that scores 10 is an outage waiting for someone
# to turn on blocking.
#
# The distinction it uses: the response status recorded in the same transaction.
# A request that Odoo answered 2xx/3xx was legitimate work that completed — if the
# score also crossed the threshold, blocking mode would have replaced that answer
# with 403. Those are listed FIRST and are the only entries that need action.
#
# Usage:
#   scripts/security/waf_triage.sh [audit-log-path]
#
# Then, once the "would have broken" section is empty over a representative
# window (a full working day including month-end reporting and an import run):
#   echo 'WAF_MODE=On' >> /opt/odoo-platform/.env
#   cd /opt/odoo-platform && docker compose \
#     -f docker-compose.yml -f docker-compose.multitenant.yml \
#     up -d --force-recreate --no-deps caddy
#   scripts/security/verify_front_door.sh
set -uo pipefail

LOG="${1:-/opt/odoo-platform/data/caddy/coraza/audit.log}"
[[ -r "$LOG" ]] || {
	echo "cannot read $LOG" >&2
	exit 1
}

python3 - "$LOG" <<'PY'
import re
import sys
from collections import Counter, defaultdict

raw = open(sys.argv[1], "rb").read().decode("utf8", "replace")

# Coraza writes one transaction per audit entry, parts separated by --<id>-<letter>--.
# Splitting on the A part header keeps each transaction whole.
txs = re.split(r"(?=--[A-Za-z0-9]+-A--)", raw)

broke = defaultdict(Counter)   # (method, path) -> Counter(rule ids)   on 2xx/3xx
caught = defaultdict(Counter)  # same, on 4xx/5xx
scores = {}
rule_msg = {}

for tx in txs:
    hits = re.findall(r'\[id "(\d+)"\][^\n]*?\[msg "([^"]*)"', tx)
    if not hits:
        continue
    req = re.search(r"^(GET|POST|PUT|PATCH|DELETE|HEAD) (\S+)", tx, re.M)
    if not req:
        continue
    method, path = req.group(1), req.group(2)
    # Response status lives in the F part (the upstream/own response line).
    st = re.search(r"^HTTP/\d(?:\.\d)? (\d{3})", tx, re.M)
    status = int(st.group(1)) if st else 0
    score = 0
    m = re.search(r"Inbound Anomaly Score Exceeded \(Total Score: (\d+)\)", tx)
    if m:
        score = int(m.group(1))

    # 949110/980xxx are the scoring/reporting rules, not findings in themselves.
    ids = [(i, msg) for i, msg in hits if not i.startswith(("949", "980"))]
    if not ids:
        continue
    for i, msg in ids:
        rule_msg[i] = msg[:64]

    # Query strings differ per request; group by path only.
    key = (method, path.split("?")[0])
    bucket = broke if 200 <= status < 400 else caught
    for i, _ in ids:
        bucket[key][i] += 1
    if score:
        scores[key] = max(scores.get(key, 0), score)


def dump(title, data, hint):
    print(f"\n=== {title} ===")
    if not data:
        print("  (none)")
        return
    print(f"  {hint}\n")
    for (method, path), rules in sorted(data.items(), key=lambda kv: -sum(kv[1].values())):
        sc = scores.get((method, path), 0)
        flag = "  <-- WOULD BE BLOCKED" if sc >= 5 else ""
        print(f"  {method} {path}   score={sc or '<5'}{flag}")
        for i, n in rules.most_common():
            print(f"      {i} x{n}  {rule_msg.get(i,'')}")


dump(
    "requests that SUCCEEDED but matched rules — fix these before WAF_MODE=On",
    broke,
    "Each of these is a working user flow. Any with score >= 5 becomes a 403.\n"
    "  NOTE: verify_front_door.sh fires its own attack payloads at /web/login,\n"
    "  /portal/, /web/session/authenticate and /web/dataset/call_kw/res.users/*.\n"
    "  In DetectionOnly those get a normal answer and land in THIS list — check the\n"
    "  audit entry's client IP before treating one of them as a false positive.",
)
dump(
    "requests that already failed — the WAF agreeing with the application",
    caught,
    "Scanner probes and genuine attacks. No action needed.",
)

print("\n=== rule frequency (all transactions) ===")
tot = Counter()
for d in (broke, caught):
    for rules in d.values():
        tot.update(rules)
for i, n in tot.most_common(15):
    print(f"  {i} x{n}  {rule_msg.get(i,'')}")
print()
PY
