# -*- coding: utf-8 -*-
"""Grant full Accounting access to selected users in prd_arkaaim.

WHY THIS IS NEEDED
------------------
Certain ARKA staff need to work in the Accounting app (create/edit journal
entries, reconcile, view all accounting). In Odoo that means adding each user to
the ``account.group_account_user`` security group ("Show Full Accounting
Features", which implies Billing). This script adds that group to a fixed list of
logins, idempotently — users who already have it are left untouched.

WHEN TO RUN
-----------
On request, when new accounting staff must be enabled. Run interactively so you
can eyeball the before/after summary before committing.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < grant_accounting.py

By default it only PREVIEWS (no commit). Set GRANT_COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
LOGINS = [
    "arman.effisan@erajaya.com",   # Arman
    "kurnia.adhi@erajaya.com",     # Kurnia
    "ricad.lingga@erajaya.com",    # Ricad (display name "Ricard")
]
GROUP_XMLID = "account.group_account_user"   # Accountant — full accounting features
GRANT_COMMIT = True     # True to persist; False = preview only
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

grp = env.ref(GROUP_XMLID)
print("Group: %s (id=%s) — %s" % (GROUP_XMLID, grp.id, grp.full_name or grp.name))
print("-" * 64)

to_add = env["res.users"].browse()
for login in LOGINS:
    user = env["res.users"].search([("login", "=", login)], limit=1)
    if not user:
        print("  !! NOT FOUND: %s — skipped" % login)
        continue
    if user.has_group(GROUP_XMLID):
        print("  == already has access: %s (%s)" % (login, user.name))
        continue
    print("  -> will grant: %s (%s, id=%s)" % (login, user.name, user.id))
    to_add |= user

if to_add:
    to_add.write({"group_ids": [(4, grp.id)]})

print("-" * 64)
print("After (has_group %s):" % GROUP_XMLID)
for login in LOGINS:
    user = env["res.users"].search([("login", "=", login)], limit=1)
    if user:
        print("  %-40s %s" % (login, user.has_group(GROUP_XMLID)))

if GRANT_COMMIT:
    env.cr.commit()
    print("\nCOMMITTED — %d user(s) granted." % len(to_add))
else:
    print("\nDRY RUN — no changes committed. Set GRANT_COMMIT = True to persist.")
