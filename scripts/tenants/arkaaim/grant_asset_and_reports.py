# -*- coding: utf-8 -*-
"""Grant the Asset and custom-Report groups to ARKA finance staff in prd_arkaaim.

WHY THIS IS NEEDED
------------------
Two menus are gated behind groups that most ARKA accounting staff never got, so
reports that exist look "missing" to them:

* ``custom_accounting_asset.group_asset_user`` gates the whole **Assets** menu —
  including *Assets > Asset Register*, i.e. the "Daftar Aset & Depresiasi" report
  (with its Export Excel button). Nothing is broken in the report; the users just
  cannot see the menu.
* ``custom_accounting_reports.group_report_user`` gates the **Reports** menu that
  holds every custom financial report (Trial Balance, General Ledger, Purchase
  Report, Credit Limit, P&L per Show, the operational reports, ...).

``account.group_account_user`` does NOT imply either of them, so an accountant
can have full Accounting access and still see neither menu.

WHEN TO RUN
-----------
On request, when ARKA finance staff report a missing Assets / Reports menu, or
after new finance users are created. Run interactively and eyeball the plan
before committing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < grant_asset_and_reports.py

By default it only PREVIEWS. Set GRANT_COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
# Who to grant to. Leave LOGINS empty to target every active internal user who
# already has SOURCE_GROUP (the accounting staff) — that keeps the list correct
# as people join or leave. Fill LOGINS to target an explicit set instead.
LOGINS = []
SOURCE_GROUP = "account.group_account_user"

# Never grant to these, even if they match SOURCE_GROUP. "User" (id=57 on
# prd_arkaaim) has no email and has never logged in, yet carries Administrator —
# it looks like an accidental import artefact, so widening it further is wrong.
EXCLUDE_LOGINS = ["User"]

GROUP_XMLIDS = [
    "custom_accounting_asset.group_asset_user",  # Assets menu + Asset Register report
    "custom_accounting_reports.group_report_user",  # Reports menu (all custom reports)
]

GRANT_COMMIT = False  # True to persist; False = preview only
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

groups = {}
for xmlid in GROUP_XMLIDS:
    grp = env.ref(xmlid, raise_if_not_found=False)
    if not grp:
        print("  !! GROUP NOT FOUND: %s — is the module installed? Skipped." % xmlid)
        continue
    groups[xmlid] = grp
    print("Group: %-52s id=%-5s %s" % (xmlid, grp.id, grp.full_name or grp.name))

if not groups:
    raise SystemExit("No target groups resolved — nothing to do.")

# ----- resolve the target users ------------------------------------------
if LOGINS:
    users = env["res.users"].browse()
    for login in LOGINS:
        user = env["res.users"].search([("login", "=", login)], limit=1)
        if not user:
            print("  !! NOT FOUND: %s — skipped" % login)
            continue
        users |= user
else:
    users = (
        env["res.users"]
        .search([("active", "=", True), ("share", "=", False)])
        .filtered(lambda u: u.has_group(SOURCE_GROUP))
    )
    print("\nTargeting every active internal user with %s (%d found)." % (SOURCE_GROUP, len(users)))

excluded = users.filtered(lambda u: u.login in EXCLUDE_LOGINS)
if excluded:
    users -= excluded
    print("Excluded by EXCLUDE_LOGINS: %s" % ", ".join(sorted(excluded.mapped("login"))))

print("-" * 78)
print("PLAN")
print("-" * 78)

planned = {}  # xmlid -> users to add
for xmlid, grp in groups.items():
    missing = users.filtered(lambda u, x=xmlid: not u.has_group(x))
    planned[xmlid] = missing
    print("\n%s" % xmlid)
    if not missing:
        print("    (nobody to add — all targeted users already have it)")
    for user in missing:
        print("    -> grant: %-42s (%s)" % (user.login, user.name))
    already = users - missing
    if already:
        print("    == already had it: %s" % ", ".join(sorted(already.mapped("login"))))

# ----- apply --------------------------------------------------------------
total = 0
for xmlid, missing in planned.items():
    if missing:
        missing.write({"group_ids": [(4, groups[xmlid].id)]})
        total += len(missing)

print("\n" + "-" * 78)
print("AFTER")
print("-" * 78)
header = "%-42s %s" % ("login", "  ".join(x.split(".")[-1] for x in groups))
print(header)
for user in users.sorted("login"):
    flags = "  ".join("%-16s" % user.has_group(x) for x in groups)
    print("%-42s %s" % (user.login, flags))

if GRANT_COMMIT:
    env.cr.commit()
    print("\nCOMMITTED — %d group assignment(s) applied." % total)
else:
    env.cr.rollback()
    print("\nDRY RUN — rolled back, nothing persisted (%d assignment(s) would be made)." % total)
    print("Set GRANT_COMMIT = True to apply.")
