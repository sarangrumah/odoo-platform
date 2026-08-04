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
