#!/usr/bin/env bash
#
# origin_lockdown.sh — restrict the published front-door ports to Cloudflare.
#
# WHY THIS EXISTS
# ---------------
# eal-hub.erajaya.com resolves to Cloudflare, but the origin also answers a
# direct connection, and probes have been observed arriving from addresses that
# are not Cloudflare's (139.5.151.45). Until the origin refuses everyone else,
# every control that lives at the Cloudflare edge — WAF, bot fight, rate limits —
# is optional from an attacker's point of view: they simply address the origin.
#
# This script is the host-firewall half of closing that. The other half is
# Cloudflare Authenticated Origin Pulls, which cannot be done from here (see
# docs/runbooks/front-door-hardening.md).
#
# NOTHING HAPPENS WITHOUT --apply. The default is --plan, which prints the exact
# rules and changes nothing.
#
# WHY DOCKER-USER
# ---------------
# Caddy publishes 80/443 through Docker, so packets are DNAT'd before they ever
# reach the INPUT chain — an INPUT rule would never match them. DOCKER-USER is
# the one chain Docker guarantees it will not rewrite, and it is consulted for
# every container-bound packet. On this host it is currently empty.
#
# SAFETY MODEL
# ------------
# Locking a firewall around a live front door is the classic way to lock
# everyone out, including yourself, so:
#   * --apply REQUIRES a trial: rules are installed with an automatic rollback
#     armed (default 300s). If you do not run --commit before it fires, the box
#     un-does the change by itself. Walk away and it heals.
#   * RELATED,ESTABLISHED is accepted first, so connections open at the moment
#     you apply are never cut.
#   * Rules are NOT persisted across reboot on purpose. A reboot is a rollback.
#   * The allow list is read from caddy/Caddyfile's trusted_proxies block — the
#     same list Caddy trusts, kept fresh by refresh_cloudflare_ranges.sh — so
#     the firewall and the proxy can never disagree about who Cloudflare is.
#
# WHAT IT DOES NOT DO
# -------------------
# It does not touch the other published container ports. This host publishes 15
# of them to the LAN and 8443 on Caddy itself; that inventory is a separate
# decision and the script prints it rather than acting on it.
#
# Usage:
#   ./origin_lockdown.sh                          # plan (default), changes nothing
#   ./origin_lockdown.sh --allow 192.168.3.0/24 --plan
#   ./origin_lockdown.sh --apply --allow 192.168.3.0/24 [--trial 300]
#   ./origin_lockdown.sh --commit                 # disarm the auto-rollback
#   ./origin_lockdown.sh --rollback               # remove the rules now
#   ./origin_lockdown.sh --status
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CADDYFILE="${CADDYFILE:-$REPO_ROOT/caddy/Caddyfile}"
TAG="origin-lockdown"
STATE_DIR="/run/origin-lockdown"
PORTS="${PORTS:-80,443}"
TRIAL="${TRIAL:-300}"
MODE="plan"
EXTRA_ALLOW=()

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
	case "$1" in
		--plan) MODE="plan" ;;
		--apply) MODE="apply" ;;
		--commit) MODE="commit" ;;
		--rollback) MODE="rollback" ;;
		--status) MODE="status" ;;
		--allow) EXTRA_ALLOW+=("$2"); shift ;;
		--trial) TRIAL="$2"; shift ;;
		--ports) PORTS="$2"; shift ;;
		-h|--help) sed -n '2,60p' "${BASH_SOURCE[0]}"; exit 0 ;;
		*) die "unknown argument: $1" ;;
	esac
	shift
done

# ---------------------------------------------------------------- allow list
# Parsed from the trusted_proxies block rather than fetched, so that a stale
# Caddyfile shows up as one problem in one place. refresh_cloudflare_ranges.sh
# is what keeps it current; it exits 1 when the list has drifted.
read_cf_ranges() {
	[[ -r "$CADDYFILE" ]] || die "cannot read $CADDYFILE"
	awk '
		/trusted_proxies static/ { inblock = 1 }
		inblock {
			line = $0
			gsub(/\\$/, "", line)
			n = split(line, tok, /[[:space:]]+/)
			for (i = 1; i <= n; i++)
				if (tok[i] ~ /^[0-9a-fA-F:.]+\/[0-9]+$/) print tok[i]
			if ($0 !~ /\\[[:space:]]*$/) inblock = 0
		}
	' "$CADDYFILE"
}

mapfile -t CF_RANGES < <(read_cf_ranges)
[[ ${#CF_RANGES[@]} -ge 10 ]] || die "parsed only ${#CF_RANGES[@]} Cloudflare ranges from $CADDYFILE — refusing to build an allow list that small"

v4() { [[ "$1" != *:* ]]; }

# ---------------------------------------------------------------- rule build
# Ordering inside DOCKER-USER matters: established traffic is admitted before
# anything can drop it, then the allow list, then the drop. Every rule carries
# the tag so --rollback can find exactly what we added and nothing else.
build_rules() {
	local ipt="$1"   # iptables | ip6tables
	printf '%s -I DOCKER-USER 1 -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN -m comment --comment %s\n' "$ipt" "$TAG"
	local cidr
	for cidr in "${CF_RANGES[@]}" "${EXTRA_ALLOW[@]:-}"; do
		[[ -n "$cidr" ]] || continue
		if [[ "$ipt" == iptables ]]; then v4 "$cidr" || continue; else v4 "$cidr" && continue; fi
		printf '%s -A DOCKER-USER -s %s -p tcp -m multiport --dports %s -j RETURN -m comment --comment %s\n' "$ipt" "$cidr" "$PORTS" "$TAG"
	done
	printf '%s -A DOCKER-USER -p tcp -m multiport --dports %s -j DROP -m comment --comment %s\n' "$ipt" "$PORTS" "$TAG"
}

show_context() {
	note ""
	note "Published container ports on this host (NOT touched by this script):"
	docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null | grep -E '0\.0\.0\.0|:::' | sed 's/^/  /' >&2 || true
	note ""
	note "Caddy also publishes 8443. If it stays open, it is a bypass of everything below."
}

case "$MODE" in
status)
	echo "DOCKER-USER rules tagged '$TAG':"
	iptables -S DOCKER-USER | grep -- "$TAG" || echo "  (none — lockdown is NOT active)"
	ip6tables -S DOCKER-USER 2>/dev/null | grep -- "$TAG" || true
	[[ -f "$STATE_DIR/armed" ]] && echo "auto-rollback ARMED (pid $(cat "$STATE_DIR/armed"))" || echo "auto-rollback: not armed"
	;;

plan)
	echo "# Allow list: ${#CF_RANGES[@]} Cloudflare ranges from $CADDYFILE"
	[[ ${#EXTRA_ALLOW[@]} -gt 0 ]] && echo "# Plus operator-supplied: ${EXTRA_ALLOW[*]}"
	echo "# Ports: $PORTS   Trial before auto-rollback: ${TRIAL}s"
	echo
	build_rules iptables
	build_rules ip6tables
	show_context
	note ""
	note "This was a plan. Nothing was changed. Re-run with --apply to install it."
	;;

apply)
	[[ $EUID -eq 0 ]] || die "must run as root"
	iptables -S DOCKER-USER | grep -q -- "$TAG" && die "lockdown already installed — use --rollback first"
	if [[ ${#EXTRA_ALLOW[@]} -eq 0 ]]; then
		note "WARNING: no --allow given, so ONLY Cloudflare will reach $PORTS."
		note "         The bare-IP host (103.130.240.24) and anything on the LAN"
		note "         addressing this box directly will stop working."
		read -r -p "Type 'cloudflare-only' to continue: " ans
		[[ "$ans" == "cloudflare-only" ]] || die "aborted"
	fi

	mkdir -p "$STATE_DIR"
	iptables-save  > "$STATE_DIR/v4.rules"
	ip6tables-save > "$STATE_DIR/v6.rules"
	note "saved current tables to $STATE_DIR"

	while read -r cmd; do eval "$cmd"; done < <(build_rules iptables)
	while read -r cmd; do eval "$cmd"; done < <(build_rules ip6tables)

	# Armed rollback: survives this shell dying, and is disarmed by --commit.
	setsid bash -c "
		sleep $TRIAL
		[[ -f '$STATE_DIR/committed' ]] && exit 0
		iptables-restore  < '$STATE_DIR/v4.rules'
		ip6tables-restore < '$STATE_DIR/v6.rules'
		rm -f '$STATE_DIR/armed'
		logger -t origin-lockdown 'auto-rollback fired: no --commit within ${TRIAL}s'
	" >/dev/null 2>&1 &
	echo $! > "$STATE_DIR/armed"

	note ""
	note "INSTALLED. Auto-rollback fires in ${TRIAL}s unless you run: $0 --commit"
	note "Verify NOW, from a machine outside Cloudflare and from a browser:"
	note "  curl -sS -o /dev/null -w '%{http_code}\\n' https://eal-hub.erajaya.com/web/login   # expect 303"
	note "  curl -sS --max-time 5 https://103.130.240.24/ ; echo \"exit=\$?\"                    # expect a timeout"
	;;

commit)
	[[ -d "$STATE_DIR" ]] || die "nothing to commit — lockdown was never applied"
	touch "$STATE_DIR/committed"
	rm -f "$STATE_DIR/armed"
	note "auto-rollback disarmed. Rules stay until --rollback or reboot."
	note "They are deliberately NOT persisted: making them survive a reboot is a"
	note "separate, considered step (iptables-persistent), not a side effect."
	;;

rollback)
	[[ $EUID -eq 0 ]] || die "must run as root"
	if [[ -f "$STATE_DIR/v4.rules" ]]; then
		iptables-restore  < "$STATE_DIR/v4.rules"
		ip6tables-restore < "$STATE_DIR/v6.rules"
		note "restored the tables saved at apply time"
	else
		while iptables -S DOCKER-USER | grep -q -- "$TAG"; do
			iptables -D DOCKER-USER "$(iptables -S DOCKER-USER | grep -n -- "$TAG" | head -1 | cut -d: -f1 | awk '{print $1-1}')"
		done
		note "removed tagged rules (no saved snapshot was found)"
	fi
	rm -f "$STATE_DIR/committed" "$STATE_DIR/armed"
	;;
esac
