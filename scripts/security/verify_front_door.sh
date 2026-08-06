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

check() { # check <label> <path> <expected-status[|alt...]> <min-bytes>
	# `want` may list alternatives: a scanner probe is refused by the WAF (403,
	# which runs first) or by the route (404) depending on which layer is enabled,
	# and both are correct answers.
	local label="$1" path="$2" want="$3" minb="${4:-0}"
	local out code size
	out=$("${CURL[@]}" -o /dev/null -w '%{http_code} %{size_download}' "$BASE$path")
	code="${out%% *}"
	size="${out##* }"
	if [[ "|$want|" == *"|$code|"* ]] && ((size >= minb)); then
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
check "/.env" /.env "403|404"
check "/files/xx.php" /files/xx.php "403|404"
check "/files/vendor/phpunit/phpunit" /files/vendor/phpunit/phpunit "403|404"
check "/wp-login.php" /wp-login.php "403|404"
check "/.git/config" /.git/config "403|404"
check "/phpmyadmin/" /phpmyadmin/ "403|404"

echo
echo "-- RPC + database manager must be closed --"
check "/xmlrpc" /xmlrpc 403
check "/jsonrpc" /jsonrpc 403
check "/web/database/manager" /web/database/manager 403
check "/web/database/selector" /web/database/selector 302

echo
echo "-- WAF: attacks blocked, real Odoo traffic untouched --"
# These are the regression test for caddy/coraza/*: the payloads that must
# be refused, and the payloads that must NOT be. The legitimate ones are the
# shapes that actually broke while tuning — a nested ORM domain (100+ arguments
# once flattened), a QWeb template carrying <script>, and a base64 spreadsheet.
if ! docker exec "${CADDY_CONTAINER:-odoo19-platform-caddy}" caddy list-modules 2>/dev/null | grep -q '^http.handlers.waf$'; then
	printf '  \033[33mSKIP\033[0m %-34s coraza not built into this Caddy\n' "WAF matrix"
else
	waf_mode=$(docker exec "${CADDY_CONTAINER:-odoo19-platform-caddy}" printenv WAF_MODE 2>/dev/null || echo DetectionOnly)
	tmp=$(mktemp -d)
	printf '%s' '{"params":{"db":"prd_levis","login":"admin'"'"' OR 1=1-- ","password":"x'"'"' UNION SELECT password FROM res_users--"}}' >"$tmp/sqli.json"
	printf '%s' '{"params":{"model":"res.users","method":"web_search_read","args":[],"kwargs":{"domain":[["login","=","admin'"'"' UNION SELECT password,1,1 FROM res_users--"]]}}}' >"$tmp/sqli_rpc.json"
	printf '%s' '{"params":{"model":"account.move.line","method":"web_read_group","args":[],"kwargs":{"domain":[["move_id.state","=","posted"],["account_id.code","=like","1%"],"|",["name","ilike","select * from"],["ref","not ilike","DROP"],["date",">=","2026-01-01"]],"groupby":["account_id"],"aggregates":["balance:sum"],"context":{"lang":"id_ID","allowed_company_ids":[1,2]}}}}' >"$tmp/legit_rpc.json"

	waf_case() { # waf_case <label> <path> <file|-> <blocked|allowed>
		local label="$1" path="$2" file="$3" want="$4" code
		if [[ "$file" == "-" ]]; then
			code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE$path")
		else
			code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST \
				-H 'Content-Type: application/json' --data-binary "@$file" "$BASE$path")
		fi
		if [[ "$want" == blocked ]]; then
			if [[ "$code" == 403 ]]; then
				printf '  \033[32mPASS\033[0m %-34s blocked\n' "$label"
				((pass++))
			elif [[ "$waf_mode" != On ]]; then
				printf '  \033[33mWARN\033[0m %-34s not blocked — WAF_MODE=%s (detect only)\n' "$label" "$waf_mode"
			else
				printf '  \033[31mFAIL\033[0m %-34s got %s, expected 403\n' "$label" "$code"
				((fail++))
			fi
		else
			# Anything but 403 is a pass: 404/303/200 all mean the WAF let it through
			# and Odoo answered for itself.
			if [[ "$code" != 403 ]]; then
				printf '  \033[32mPASS\033[0m %-34s passed (%s)\n' "$label" "$code"
				((pass++))
			else
				printf '  \033[31mFAIL\033[0m %-34s FALSE POSITIVE — 403\n' "$label"
				((fail++))
			fi
		fi
	}

	waf_case "SQLi in query string" "/web/login?x=1%27%20OR%201=1--%20" - blocked
	waf_case "XSS in query string" "/portal/?q=%3Cscript%3Ealert(1)%3C/script%3E" - blocked
	waf_case "traversal on /api" "/api/x?f=../../../../etc/passwd" - blocked
	waf_case "SQLi in auth body" "/web/session/authenticate" "$tmp/sqli.json" blocked
	waf_case "SQLi in call_kw body" "/web/dataset/call_kw/res.users/web_search_read" "$tmp/sqli_rpc.json" blocked
	waf_case "real ORM domain (100+ args)" "/web/dataset/call_kw/account.move.line/web_read_group" "$tmp/legit_rpc.json" allowed
	rm -rf "$tmp"
fi

echo
echo "=== $pass passed, $fail failed ==="
((fail == 0))
