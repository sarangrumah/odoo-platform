#!/usr/bin/env bash
# Refresh the Cloudflare edge ranges in caddy/Caddyfile `trusted_proxies static`.
#
# Why this matters: those ranges are what makes CF-Connecting-IP believable. If
# Cloudflare adds a range that is not listed, requests from that edge fall back
# to the socket address, so every visitor arriving through it shares one
# rate-limit bucket and lands in the Odoo audit trail as a Cloudflare IP. It
# fails safe (never blocks traffic), so this is maintenance, not an outage risk.
#
# Prints a unified diff and exits 1 when the file would change, so it can run in
# CI as a drift check. Pass --write to apply.
set -euo pipefail

CADDYFILE="${CADDYFILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/caddy/Caddyfile}"
WRITE=0
[[ "${1:-}" == "--write" ]] && WRITE=1

v4=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4)
v6=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6)

# Guard against a truncated or error-page response silently emptying the list.
n=$(printf '%s\n%s\n' "$v4" "$v6" | grep -c '/')
if (( n < 15 )); then
	echo "refusing to rewrite: only $n ranges fetched (expected >= 15)" >&2
	exit 2
fi

# Ranges travel in the environment, not on stdin: stdin is already spoken for by
# the heredoc carrying the script itself.
export CF_RANGES="$(printf '%s\n%s\n' "$v4" "$v6")"

python3 - "$CADDYFILE" "$WRITE" <<'PY'
import os
import re
import subprocess
import sys
import tempfile

path, write = sys.argv[1], sys.argv[2] == "1"
ranges = [ln.strip() for ln in os.environ["CF_RANGES"].splitlines() if ln.strip()]

# Six per line for v4, four for v6 — same shape the file already uses.
v4 = [r for r in ranges if ":" not in r]
v6 = [r for r in ranges if ":" in r]


def chunk(items, n):
    return [items[i : i + n] for i in range(0, len(items), n)]


lines = ["\t\ttrusted_proxies static \\"]
groups = chunk(v4, 4) + chunk(v6, 4)
for i, g in enumerate(groups):
    tail = "" if i == len(groups) - 1 else " \\"
    lines.append("\t\t\t" + " ".join(g) + tail)
block = "\n".join(lines)

src = open(path).read()
pat = re.compile(r"\t\ttrusted_proxies static \\\n(?:\t\t\t[^\n]*\n)*?\t\t\t[^\n]*(?<!\\)\n")
m = pat.search(src)
if not m:
    sys.exit("could not locate the trusted_proxies block in " + path)
out = src[: m.start()] + block + "\n" + src[m.end() :]

if out == src:
    print("cloudflare ranges already current")
    sys.exit(0)

with tempfile.NamedTemporaryFile("w", suffix=".Caddyfile", delete=False) as fh:
    fh.write(out)
    tmp = fh.name
subprocess.run(["diff", "-u", path, tmp], check=False)
if write:
    # Write in place (do NOT replace the inode): the running container bind-mounts
    # this single file, and a new inode leaves it reading the old content while
    # `caddy reload` reports success. See docs/runbooks/front-door-hardening.md.
    with open(path, "w") as fh:
        fh.write(out)
    print("updated " + path + " — now recreate caddy, a reload is not enough")
sys.exit(1)
PY
