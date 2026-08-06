# Revoke Settings-level rights from users who should not hold them.
#
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       < scripts/tenants/levis/84_tidy_admin_rights.py
#
# Dry-run by default: it reports and rolls back. ADM_APPLY=1 commits.
#
# WHY
# ---
# On 6-Aug-2026 every one of the 73 active users of prd_levis_begbal held
# base.group_system. That group carries write access to ir.ui.view, and a view is
# rendered in every other user's browser -- so on a database where everyone is an
# admin, any single compromised session can serve script to everybody, including
# whoever is approving payments. Revoking it is the cheapest real reduction of
# that blast radius available on this tenant.
#
# WHAT IT TOUCHES -- deliberately narrow
# --------------------------------------
# Two groups only:
#   base.group_system       "Settings" -- the menu, ir.ui.view write, technical
#                           features, and the ability to grant rights
#   base.group_erp_manager  "Access Rights" -- implied by group_system, and NOT
#                           removed automatically when group_system goes, because
#                           Odoo materialises implied groups and never withdraws
#                           them retroactively. Leaving it behind would keep the
#                           user able to re-grant themselves everything, which
#                           would make this whole script theatre.
#
# It does NOT touch the functional manager groups (account.group_account_manager,
# hr.group_hr_manager, purchase.group_purchase_manager, ...). Every user on this
# tenant holds ~107 groups -- effectively the entire catalogue -- and deciding who
# should keep which app is a business review, not a security cleanup. Users keep
# doing their jobs; they lose Settings.
#
# The removal goes through the ORM (`group_ids` with a 3-tuple), never SQL,
# because res.groups membership is a computed closure over implied_ids: a DELETE
# on res_groups_users_rel leaves the closure stale and the user keeps the rights
# through an implied path. Same reason the 3-Aug restore had to use the ORM.
#
# ROLLBACK
# --------
# Membership is written to a CSV before anything changes (ADM_BACKUP, default
# /tmp/group_system_backup_<db>.csv). To undo:
#   ADM_RESTORE=/tmp/group_system_backup_prd_levis_begbal.csv ADM_APPLY=1 \
#   docker exec -i ... odoo shell -d prd_levis_begbal --no-http < this_script
#
# Env flags:
#   ADM_KEEP=login1,login2   logins that KEEP admin (required unless ADM_RESTORE)
#   ADM_APPLY=1              commit; otherwise everything is rolled back
#   ADM_BACKUP=<path>        where to write the membership backup
#   ADM_RESTORE=<path>       re-grant from a backup file instead of revoking
import csv
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[adm] " + m)

DB = env.cr.dbname
APPLY = os.environ.get("ADM_APPLY") == "1"
BACKUP = os.environ.get("ADM_BACKUP", "/tmp/group_system_backup_%s.csv" % DB)
RESTORE = os.environ.get("ADM_RESTORE")
KEEP = [l.strip() for l in os.environ.get("ADM_KEEP", "").split(",") if l.strip()]

TARGET_XMLIDS = ["base.group_system", "base.group_erp_manager"]
targets = {x: env.ref(x) for x in TARGET_XMLIDS}
group_user = env.ref("base.group_user")

# ------------------------------------------------------------------ restore
if RESTORE:
    with open(RESTORE) as fh:
        rows = list(csv.DictReader(fh))
    log("restoring %d membership rows from %s" % (len(rows), RESTORE))
    by_group = {}
    for r in rows:
        by_group.setdefault(r["group_xmlid"], []).append(int(r["uid"]))
    for xmlid, uids in by_group.items():
        grp = env.ref(xmlid)
        users = env["res.users"].browse(uids).exists()
        users.write({"group_ids": [(4, grp.id)]})
        log("  %-24s -> %d users" % (xmlid, len(users)))
    if APPLY:
        env.cr.commit()
        log("RESTORED and committed.")
    else:
        env.cr.rollback()
        log("dry-run: rolled back. Set ADM_APPLY=1 to commit.")
    raise SystemExit(0)

# ------------------------------------------------------------------ revoke
if not KEEP:
    raise SystemExit(
        "[adm] refusing to run with an empty ADM_KEEP: that would leave nobody "
        "able to administer %s. Pass the logins that must keep Settings." % DB
    )

keep_users = env["res.users"].search([("login", "in", KEEP)])
missing = set(KEEP) - set(keep_users.mapped("login"))
if missing:
    raise SystemExit(
        "[adm] these ADM_KEEP logins do not exist in %s: %s. Refusing to run "
        "rather than silently keeping fewer admins than you intended." % (DB, ", ".join(sorted(missing)))
    )

holders = env["res.users"].search([("group_ids", "in", targets["base.group_system"].ids), ("active", "=", True)])
losing = holders - keep_users
log(
    "db=%s  holders of group_system=%d  keeping=%d  revoking from=%d" % (DB, len(holders), len(keep_users), len(losing))
)
log("keeping: " + ", ".join(sorted(keep_users.mapped("login"))))

# Backup first, and back up BOTH groups for everyone who has them, so a restore
# reproduces the exact prior state rather than an approximation of it.
with open(BACKUP, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["uid", "login", "group_xmlid"])
    n = 0
    for xmlid, grp in targets.items():
        for u in env["res.users"].search([("group_ids", "in", grp.ids)]):
            w.writerow([u.id, u.login, xmlid])
            n += 1
log("backup written: %s (%d rows)" % (BACKUP, n))

if not losing:
    log("nothing to do.")
    raise SystemExit(0)

for xmlid, grp in targets.items():
    subset = losing.filtered(lambda u, g=grp: g in u.group_ids)
    if subset:
        subset.write({"group_ids": [(3, grp.id)]})
        log("revoked %-24s from %d users" % (xmlid, len(subset)))

# The failure mode that matters is a user left with no user-type group at all:
# they would still log in, see an empty menu, and file a ticket that looks like
# data loss rather than a rights change.
#
# It is not hypothetical. On prd_levis_AP (4 users) and prd_arkaaim (10) the
# Internal User group was never materialised on the row -- those accounts were
# internal users only *through* group_system implying it. Taking Settings away
# would have taken their login with it. Grant the baseline explicitly instead:
# it is what they already had in effect, so it is not an escalation, and the
# alternative is to leave the tenant half-cleaned.
stranded = losing.filtered(lambda u: group_user not in u.group_ids)
if stranded:
    log(
        "granting base.group_user to %d users who held it only by implication: %s"
        % (len(stranded), ", ".join(stranded.mapped("login")[:5]) + ("…" if len(stranded) > 5 else ""))
    )
    stranded.write({"group_ids": [(4, group_user.id)]})

still_stranded = losing.filtered(lambda u: group_user not in u.group_ids)
if still_stranded:
    env.cr.rollback()
    raise SystemExit(
        "[adm] ABORTED: %d users still lack base.group_user after the grant (%s). "
        "Rolled back." % (len(still_stranded), ", ".join(still_stranded.mapped("login")[:5]))
    )

still = env["res.users"].search_count([("group_ids", "in", targets["base.group_system"].ids), ("active", "=", True)])
log("after: %d active users hold group_system (expected %d)" % (still, len(keep_users)))
log("sample group counts after: " + ", ".join("%s=%d" % (u.login, len(u.group_ids)) for u in losing[:3]))

if APPLY:
    env.cr.commit()
    log("COMMITTED. Undo with ADM_RESTORE=%s ADM_APPLY=1" % BACKUP)
else:
    env.cr.rollback()
    log("dry-run: rolled back. Set ADM_APPLY=1 to commit.")
