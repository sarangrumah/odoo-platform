"""Assign security roles (and optionally Operating Units) from a reviewed CSV.

    RUN_DRY=0 CSV=/tmp/user_access_prd_levis_begbal.csv \
      docker exec -i -e RUN_DRY=0 -e CSV=/tmp/user_access_prd_levis_begbal.csv \
      odoo19-platform-odoo-mgmt odoo shell -d prd_levis_begbal --no-http \
      < scripts/security/assign_roles.py

Dry-run by default (``RUN_DRY=1``): prints what each user would gain and lose,
then rolls back. Produce the CSV with ``report_user_access.py``, have somebody
who knows the organisation fill in ``role_codes`` and ``ou_codes``
(pipe-separated), and run this.

Rows with an empty ``role_codes`` are skipped, so the file can be filled in and
applied a department at a time rather than in one sitting.

Everything goes through ``res.users.write``: the role engine revokes strictly
what it granted itself, so a group somebody was given by hand — or by the
Keycloak mapping — survives. That is also why this is safe to re-run.

``ou_codes`` is the switch: a user with units assigned starts seeing only those
units' data. Leave it empty to change rights without changing visibility.
"""

import csv
import logging
import os

from odoo.fields import Command

_logger = logging.getLogger("assign_roles")
logging.basicConfig(level=logging.INFO)

env = env  # noqa: F821 — odoo shell global

DRY = os.environ.get("RUN_DRY", "1") != "0"
PATH = os.environ.get("CSV", "/tmp/user_access_%s.csv" % env.cr.dbname)

if "custom.security.role" not in env:
    raise SystemExit("custom_role_manager is not installed on this database")

Role = env["custom.security.role"]
OU = env["operating.unit"] if "operating.unit" in env else None

roles_by_code = {r.code: r for r in Role.search([])}
units_by_code = {u.code: u for u in OU.with_context(active_test=False).search([])} if OU else {}

applied = skipped = 0
problems = []

with open(PATH, newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        login = (row.get("login") or "").strip()
        codes = [c.strip() for c in (row.get("role_codes") or "").split("|") if c.strip()]
        ous = [c.strip() for c in (row.get("ou_codes") or "").split("|") if c.strip()]
        if not login or not codes:
            skipped += 1
            continue

        user = env["res.users"].search([("login", "=", login)], limit=1)
        if not user:
            problems.append("no such user: %s" % login)
            continue
        unknown = [c for c in codes if c not in roles_by_code] + [c for c in ous if c not in units_by_code]
        if unknown:
            problems.append("%s: unknown code(s) %s" % (login, ", ".join(unknown)))
            continue

        before = set(user.group_ids.ids)
        vals = {"role_ids": [Command.set([roles_by_code[c].id for c in codes])]}
        if ous:
            vals["operating_unit_ids"] = [Command.set([units_by_code[c].id for c in ous])]
        user.write(vals)

        after = set(user.group_ids.ids)
        gained = env["res.groups"].browse(list(after - before))
        lost = env["res.groups"].browse(list(before - after))
        _logger.info(
            "%-34s roles=%-28s +%d -%d%s",
            login,
            ",".join(codes),
            len(gained),
            len(lost),
            "  units=%s" % ",".join(ous) if ous else "",
        )
        if lost:
            _logger.info("%-34s   lost: %s", "", ", ".join(lost.mapped("name"))[:150])
        applied += 1

for problem in problems:
    _logger.warning("  %s", problem)

_logger.info("")
_logger.info("%d user(s) updated, %d row(s) skipped (no role_codes), %d problem(s)", applied, skipped, len(problems))

if DRY:
    env.cr.rollback()
    _logger.info("DRY run — rolled back. Re-run with RUN_DRY=0 to apply.")
else:
    env.cr.commit()
    _logger.info("Committed.")
