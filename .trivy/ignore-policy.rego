# Package-level trivy suppressions — justify EVERY rule.
#
# This file exists because `.trivyignore` (and `.trivyignore.yaml`) can only
# suppress by vulnerability ID. Suppressing a whole package that way means
# pasting in a list of CVE IDs that goes stale the moment a new one is
# published, which is exactly the case we have below. Rego matches on the
# package, so it keeps working.
#
# Verified against trivy v0.70.0 (the version trivy-action v0.36.0 installs)
# AND v0.73.0, in both directions: the targeted findings disappear and every
# unrelated finding in the same image still reports.

package trivy

default ignore = false

# linux-libc-dev — Linux kernel headers, ~118 HIGH/CRITICAL on the odoo image
# (ubuntu 24.04 base) and climbing every week.
#
# Why this is not a real exposure: the package ships C headers under
# /usr/include/linux. Nothing in it is ever executed, and a container does not
# run its own kernel — it uses the host's. A kernel CVE reported against these
# headers is a statement about the *host* kernel, which is patched by patching
# the host, not by rebuilding this image.
#
# Why it cannot be fixed here: the fixed versions trivy points at are published
# by Ubuntu for the base image. `apt-get --only-upgrade linux-libc-dev` inside
# our Dockerfile would pull a header package that does not match the running
# host kernel, which is worse than leaving it alone. The real fix is upstream
# republishing odoo:19 on a newer base.
#
# REVIEW: drop this rule and re-scan whenever the odoo base image is bumped —
# if upstream has caught up, the noise is gone and this suppression should go
# with it. Do NOT widen this rule to other OS packages; those are genuinely
# actionable in our own Dockerfile (see the targeted openssl upgrade there).
ignore {
	input.PkgName == "linux-libc-dev"
}

# Go stdlib v1.26.5, as compiled into the static docker CLI that
# tenant-orchestrator ships (`usr/local/bin/docker`, gobinary target). Eight
# HIGH findings as of 18-Aug-2026, led by CVE-2026-33818 (encoding/asn1 DoS).
#
# Why it cannot be fixed by bumping, which is what the Dockerfile comment tells
# you to do first: 29.7.2 is the newest static release Docker publishes and it
# is *also* built with go1.26.5 (verified by reading the build stamp out of the
# tarball). The fix needs go1.26.6, and no Docker release carries it yet.
#
# Why the exposure is negligible here: the binary is only ever invoked as
# `docker exec` against /var/run/docker.sock, mounted read-only, on the local
# host. It parses no ASN.1 from a remote peer — there is no TLS transport and no
# registry pull in that path.
#
# The rule is pinned to the exact vulnerable version ON PURPOSE, so it expires
# by itself: the moment the CLI is rebuilt on any other Go build, this stops
# matching and every finding reports again. Do NOT relax it to `PkgName ==
# "stdlib"` alone — that would hide every future Go CVE in every binary.
ignore {
	input.PkgName == "stdlib"
	input.InstalledVersion == "v1.26.5"
}
