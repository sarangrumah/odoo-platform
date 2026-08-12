"""What every user can actually do today — the input to a role assignment.

    docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/security/report_user_access.py

Read-only. Writes a CSV to /tmp/user_access_<db>.csv with one row per active
user: their current direct-group count, the high-privilege groups they hold,
the roles they already carry, and empty ``role_codes`` / ``ou_codes`` columns
for a human to fill in. That file is the input to ``assign_roles.py``.

Why this exists: on a tenant that has never had roles, "who should be what" is
not in the database — every user tends to look identical. On prd_levis_begbal
all 84 active users hold Accounting Manager, POS Manager, Stock Manager and
Purchase Manager alike. A list like that is not something to guess at; it is
something to hand to whoever knows the organisation.

**Count the closure, not the membership table.** Querying
``res_groups_users_rel`` for ``base.group_system`` on prd_levis_begbal returns
13 users and reads like a tidy situation. It is not: 84 of 84 hold it through
``all_group_ids``, because a legacy group they all carry implies it. The direct
count is the one that flatters; the effective count is the one that is true, so
this prints both.
"""

import csv
import logging

_logger = logging.getLogger("user_access")
logging.basicConfig(level=logging.INFO)

env = env  # noqa: F821 — odoo shell global

# Groups worth calling out by name: holding one is a decision, not an accident.
FLAGGED = [
    ("base.group_system", "Settings"),
    ("base.group_erp_manager", "Admin"),
    ("account.group_account_manager", "Acc.Manager"),
    ("point_of_sale.group_pos_manager", "POS.Manager"),
    ("stock.group_stock_manager", "Stock.Manager"),
    ("purchase.group_purchase_manager", "Purch.Manager"),
]

flagged = []
for xmlid, label in FLAGGED:
    group = env.ref(xmlid, raise_if_not_found=False)
    if group:
        flagged.append((group, label))

users = env["res.users"].search([("active", "=", True)], order="login")
path = "/tmp/user_access_%s.csv" % env.cr.dbname

with open(path, "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["login", "name", "direct_groups", "flagged", "current_roles", "role_codes", "ou_codes"])
    for user in users:
        held = [label for group, label in flagged if group in user.all_group_ids]
        writer.writerow(
            [
                user.login,
                user.partner_id.name or "",
                len(user.group_ids),
                "|".join(held),
                "|".join(user.role_ids.mapped("code")) if "role_ids" in user._fields else "",
                "",  # role_codes — to fill in
                "",  # ou_codes  — to fill in
            ]
        )

_logger.info("%d active user(s) → %s", len(users), path)
_logger.info("")
for group, label in flagged:
    effective = users.filtered(lambda u, g=group: g in u.all_group_ids)
    direct = users.filtered(lambda u, g=group: g in u.group_ids)
    note = "" if len(effective) == len(direct) else "   <-- mostly implied, not granted"
    _logger.info(
        "  %-14s effective %3d / direct %3d  of %d users%s",
        label,
        len(effective),
        len(direct),
        len(users),
        note,
    )
_logger.info("")
_logger.info(
    "Fill role_codes (and ou_codes, if scoping) in that CSV, then feed it to "
    "scripts/security/assign_roles.py. Role codes: %s",
    ", ".join(env["custom.security.role"].search([]).mapped("code"))
    if "custom.security.role" in env
    else "(custom_role_manager not installed)",
)
