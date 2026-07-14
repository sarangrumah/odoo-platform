# -*- coding: utf-8 -*-
"""Create the user darwin.sitio@erajaya.com in prd_arkaaim, mirroring peer (Arman).

WHY THIS IS NEEDED
------------------
Darwin was requested for Accounting access alongside Arman/Kurnia/Ricad, but had
no user record. This creates him as a full peer of Arman (id=40): internal user +
full Accounting (account_user + account_invoice) + multi-company (both ARKA
companies) + bank-account validation + Sales salesman. A temporary password is
set so he can sign in and change it.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < create_user_darwin.py

By default it only PREVIEWS (no commit). Set CREATE_COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
LOGIN = "darwin.sitio@erajaya.com"
NAME = "Darwin Sitio"
TEMP_PASSWORD = "Od00!"
PEER_LOGIN = "arman.effisan@erajaya.com"  # profile to mirror (group set + companies)
CREATE_COMMIT = True  # True to persist; False = preview only
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Users = env["res.users"]
peer = Users.search([("login", "=", PEER_LOGIN)], limit=1)
assert peer, "peer %s not found" % PEER_LOGIN

# mirror peer's explicit group set and company access
group_ids = peer.group_ids.ids
company_ids = peer.company_ids.ids
main_company = peer.company_id.id

print("Mirroring peer: %s (id=%s)" % (PEER_LOGIN, peer.id))
print("  main company : %s" % peer.company_id.display_name)
print("  companies    : %s" % ", ".join(peer.company_ids.mapped("display_name")))
print("  groups       :")
for g in peer.group_ids.sorted("full_name"):
    print("     - %s" % (g.full_name or g.name))
print("-" * 64)

existing = Users.with_context(active_test=False).search([("login", "=", LOGIN)], limit=1)
if existing:
    print("!! User %s already exists (id=%s, active=%s) — NOT creating." % (LOGIN, existing.id, existing.active))
    new_user = existing
else:
    new_user = Users.create(
        {
            "name": NAME,
            "login": LOGIN,
            "password": TEMP_PASSWORD,
            "company_id": main_company,
            "company_ids": [(6, 0, company_ids)],
            "group_ids": [(6, 0, group_ids)],
        }
    )
    print("Created user %s -> id=%s" % (LOGIN, new_user.id))

print("-" * 64)
print("Resulting profile:")
print("  login        : %s" % new_user.login)
print("  name         : %s" % new_user.name)
print("  main company : %s" % new_user.company_id.display_name)
print("  companies    : %s" % ", ".join(new_user.company_ids.mapped("display_name")))
print("  has full accounting (account_user): %s" % new_user.has_group("account.group_account_user"))

if CREATE_COMMIT:
    env.cr.commit()
    print("\nCOMMITTED. Temporary password set to: %s" % TEMP_PASSWORD)
else:
    # roll back the in-memory create so preview leaves nothing behind
    env.cr.rollback()
    print("\nDRY RUN — rolled back, no changes committed. Set CREATE_COMMIT = True to persist.")
