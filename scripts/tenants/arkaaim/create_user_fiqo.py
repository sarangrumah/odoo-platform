# -*- coding: utf-8 -*-
"""Create the user syafiqo.zhafran@erajaya.com in prd_arkaaim, mirroring peer (Mei).

WHY THIS IS NEEDED
------------------
Item 23 of the client sheet "[ARKA AIM] List Issue After Go Live" (requested by
Mei, Fin AP, 7 Aug 2026): *"Akses belum bisa arka aim an Fiqo"*. He simply had no
user record — verified 2026-08-18, `res_users` had no row for that login, while
his Fin AP peers (feri.01, mei.mey, sumida.01, nuri.pancawati) were all present
and active. See ``docs/projects/arka-aim/ISSUE_SHEET_AUG2026_STATUS.md``.

PROFILE — MIRROR OF MEI
-----------------------
Confirmed with the requester: same access as Mei, who is the peer that asked for
him. Mei, Feri and Nuri all carry an identical group set, so mirroring any of
them gives the same result. Same approach as ``create_user_darwin.py``.

Worth knowing before you read the group list: the two groups displayed as
**"Administrator"** are ``account.group_account_manager`` (Accounting Manager)
and ``stock.group_stock_manager`` (Inventory Manager). Neither is
``base.group_system`` — this profile is NOT a system administrator. The stock
manager group is odd for a Fin AP user, but it is what every peer on this
database carries; trimming it is a separate decision for the whole group, not
something to do to one new user.

LOGIN IS CASE-SENSITIVE
-----------------------
Odoo 19 matches with ``Domain('login','=',login)``, so a login stored with any
capital letter can never be reached by typing it lowercase. That is exactly what
broke Feri/Mei/Sumida before (``fix_user_access.py``). This script therefore
lowercases LOGIN before doing anything.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < create_user_fiqo.py

By default it only PREVIEWS (no commit). Set CREATE_COMMIT = True to persist.

ALREADY RUN on prd_arkaaim 2026-08-18 — user created as id=81, group set
identical to Mei (13 groups, zero difference), and ``authenticate`` confirmed
the credentials resolve to uid 81. Pre-dump at
``/var/backups/odoo/prd_arkaaim-pre-user-fiqo-20260818.dump``. Re-running is
safe: an existing login is reported and left alone, never re-created.

TEMP_PASSWORD is a throwaway for first sign-in and must be changed by the
user immediately. Rotate it here if this script is ever reused.
"""

# ----- knobs -------------------------------------------------------------
LOGIN = "syafiqo.zhafran@erajaya.com"
NAME = "Syafiqo Zhafran"
TEMP_PASSWORD = "Od00!"
PEER_LOGIN = "mei.mey@erajaya.com"  # profile to mirror (group set + companies)
CREATE_COMMIT = False  # True to persist; False = preview only
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

LOGIN = LOGIN.strip().lower()

Users = env["res.users"]
peer = Users.search([("login", "=", PEER_LOGIN)], limit=1)
assert peer, "peer %s not found" % PEER_LOGIN

# mirror peer's explicit group set and company access
group_ids = peer.group_ids.ids
company_ids = peer.company_ids.ids
main_company = peer.company_id.id

print("=" * 64)
print("Create user %s — %s" % (LOGIN, "COMMIT" if CREATE_COMMIT else "PREVIEW"))
print("=" * 64)
print("Mirroring peer: %s (id=%s)" % (PEER_LOGIN, peer.id))
print("  main company : %s" % peer.company_id.display_name)
print("  companies    : %s" % ", ".join(peer.company_ids.mapped("display_name")))
print("  groups       :")
for g in peer.group_ids.sorted("id"):
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
print("  active       : %s" % new_user.active)
print("  internal     : %s" % (not new_user.share))
print("  main company : %s" % new_user.company_id.display_name)
print("  companies    : %s" % ", ".join(new_user.company_ids.mapped("display_name")))
print("  full accounting (account_user)   : %s" % new_user.has_group("account.group_account_user"))
print("  accounting manager               : %s" % new_user.has_group("account.group_account_manager"))
print("  system administrator (must be False): %s" % new_user.has_group("base.group_system"))
missing = set(group_ids) - set(new_user.group_ids.ids)
print("  groups matching peer             : %s" % ("YES" if not missing else "NO — missing %s" % sorted(missing)))

if CREATE_COMMIT:
    env.cr.commit()
    print("\nCOMMITTED. Temporary password set (see the TEMP_PASSWORD knob above).")
else:
    # roll back the in-memory create so preview leaves nothing behind
    env.cr.rollback()
    print("\nDRY RUN — rolled back, no changes committed. Set CREATE_COMMIT = True to persist.")
