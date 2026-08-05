#!/usr/bin/env bash
# Front-door security + routing verification for eal-hub.erajaya.com.
#
# Run it BEFORE and AFTER every ingress change. It asserts two things that pull
# in opposite directions:
#
#   1. the hardening is actually in effect (headers, scanner 404s, WAF verdicts)
#   2. nothing legitimate regressed (tenant chooser, portal SPA, BFF API,
#      Odoo login, File Browser)
#
# It talks to the ORIGIN, not to Cloudflare, via --resolve. Two gotchas this
# encodes, both of which have produced false "all healthy" results here before:
#
#   * curl to https://127.0.0.1/ sends Host: 127.0.0.1, matches no site block,
#     and Caddy answers an empty HTTP 200 (logged "NOP"). Always --resolve the
#     real hostname.
#   * a dead site still answers 200, so every check below asserts on the body
#     size as well as the status code.
#
# Usage:  scripts/security/verify_front_door.sh [host]
set -uo pipefail

HOST="${1:-eal-hub.erajaya.com}"
ORIGIN="${ORIGIN:-127.0.0.1}"
BASE="https://$HOST"
CURL=(curl -sk --max-time 20 --resolve "$HOST:443:$ORIGIN")

pass=0
fail=0

hdr_cache=""

check() { # check <label> <path> <expected-status> <min-bytes>
	local label="$1" path="$2" want="$3" minb="${4:-0}"
	local out code size
	out=$("${CURL[@]}" -o /dev/null -w '%{http_code} %{size_download}' "$BASE$path")
	code="${out%% *}"
	size="${out##* }"
	if [[ "$code" == "$want" ]] && ((size >= minb)); then
		printf '  \033[32mPASS\033[0m %-34s %s (%s bytes)\n' "$label" "$code" "$size"
		((pass++))
	else
		printf '  \033[31mFAIL\033[0m %-34s got %s/%s bytes, want %s/>=%s\n' \
			"$label" "$code" "$size" "$want" "$minb"
		((fail++))
	fi
}

header_present() { # header_present <header-name> [expected-substring]
	local name="$1" want="${2:-}" line
	line=$(grep -i "^$name:" <<<"$hdr_cache")
	if [[ -z "$line" ]]; then
		printf '  \033[31mFAIL\033[0m %-34s header absent\n' "$name"
		((fail++))
	elif [[ -n "$want" && "$line" != *"$want"* ]]; then
		printf '  \033[31mFAIL\033[0m %-34s %s (want *%s*)\n' "$name" "${line//$'\r'/}" "$want"
		((fail++))
	else
		printf '  \033[32mPASS\033[0m %-34s %s\n' "$name" "${line//$'\r'/}"
		((pass++))
	fi
}

header_absent() { # header_absent <header-name>  — leaks the upstream identity
	local name="$1"
	if grep -qi "^$name:" <<<"$hdr_cache"; then
		printf '  \033[31mFAIL\033[0m %-34s leaked: %s\n' "$name" \
			"$(grep -i "^$name:" <<<"$hdr_cache" | tr -d '\r')"
		((fail++))
	else
		printf '  \033[32mPASS\033[0m %-34s not sent\n' "$name"
		((pass++))
	fi
}

echo
echo "=== front door: $HOST (origin $ORIGIN) ==="

echo
echo "-- routing must still work --"
# / redirects to the tenant chooser; 302 with an empty body is correct here.
check "/ -> tenant chooser" / 302
# /signin is served directly (Next.js basePath), /signin/ is the one that 308s.
check "/signin (Next.js gateway)" /signin 200 1000
check "/portal/ (hub-portal SPA)" /portal/ 200 200
check "/api/health (portal BFF)" /api/health 200 10
check "/files/ (File Browser UI)" /files/ 200 500
# Odoo answers 303 to the database selector for a session with no tenant pinned
# yet, which the front door rewrites to the chooser. Anything else means the
# Odoo hop is broken.
check "/web/login (odoo-front)" /web/login 303 1
check "/web/static asset" /web/static/src/scss/primary_variables.scss 200 100

echo
echo "-- security headers --"
hdr_cache=$("${CURL[@]}" -D - -o /dev/null "$BASE/web/login")
header_present "strict-transport-security" "max-age=31536000"
header_present "x-content-type-options" "nosniff"
header_present "x-frame-options"
header_present "referrer-policy"
header_present "permissions-policy"
header_present "content-security-policy" "frame-ancestors"
header_absent "server"
header_absent "x-powered-by"

echo
echo "-- scanner probes must be refused, not served --"
# Before hardening every one of these returned 200 with the File Browser SPA,
# which is exactly why the scanning is relentless.
check "/.env" /.env 404
check "/files/xx.php" /files/xx.php 404
check "/files/vendor/phpunit/phpunit" /files/vendor/phpunit/phpunit 404
check "/wp-login.php" /wp-login.php 404
check "/.git/config" /.git/config 404
check "/phpmyadmin/" /phpmyadmin/ 404

echo
echo "-- RPC + database manager must be closed --"
check "/xmlrpc" /xmlrpc 403
check "/jsonrpc" /jsonrpc 403
check "/web/database/manager" /web/database/manager 403
check "/web/database/selector" /web/database/selector 302

echo
echo "-- WAF (skipped unless coraza is built in) --"
if "${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE/web/login?id=1%20OR%201=1--" | grep -q 403; then
	printf '  \033[32mPASS\033[0m %-34s blocked\n' "SQLi probe"
	((pass++))
elif docker exec odoo19-platform-caddy caddy list-modules 2>/dev/null | grep -q coraza; then
	printf '  \033[33mWARN\033[0m %-34s module present but not blocking (DetectionOnly?)\n' "SQLi probe"
else
	printf '  \033[33mSKIP\033[0m %-34s coraza not built into this Caddy\n' "SQLi probe"
fi

echo
echo "=== $pass passed, $fail failed ==="
((fail == 0))
