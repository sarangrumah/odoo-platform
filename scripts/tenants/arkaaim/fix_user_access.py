# -*- coding: utf-8 -*-
"""Fix the go-live access complaints on prd_arkaaim (sheet item #7).

WHY THIS IS NEEDED
------------------
Three ARKA-AIM staff reported "akses belum bisa". The database shows three
distinct causes, none of which the user can see from the login screen:

1. ``Feri.01@erajaya.com`` was created with a capital F. Odoo matches the login
   with ``Domain('login', '=', login)`` (``res.users._get_login_domain``), i.e.
   case-SENSITIVE, so typing ``feri.01@erajaya.com`` can never authenticate.
   Any other login stored with uppercase has the same latent bug, so the script
   normalises every ``login <> lower(login)`` it finds.
2. Feri's ``company_ids`` holds only PT Aero Inovasi Media (AIM), so even after
   logging in there is no PT Aero Reksa Kreasi Angkasa (ARKA) to switch to.
3. ``sumida.01@erajaya.com`` has ``password IS NULL`` — the account was created
   but a password was never set, so no credential can ever match. Only a reset
   mail (or an admin-set password) can unblock it.

WHEN TO RUN
-----------
Once, on prd_arkaaim. Re-running is harmless: every step is idempotent and
skipped when already correct.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < fix_user_access.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = True  # True to persist
SEND_RESET_MAIL = False  # True to e-mail a set-password link to PASSWORDLESS logins
ARKA_COMPANY = "PT Aero Reksa Kreasi Angkasa"
GRANT_ARKA_TO = ["feri.01@erajaya.com"]  # logins that must see both companies
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

Users = env["res.users"].sudo()
arka = env["res.company"].sudo().search([("name", "=", ARKA_COMPANY)], limit=1)
if not arka:
    raise SystemExit("Company %r not found — wrong database?" % ARKA_COMPANY)

print("=" * 78)
print("prd_arkaaim access fix — %s" % ("COMMIT" if COMMIT else "PREVIEW ONLY"))
print("=" * 78)

# --- 1. logins stored with uppercase characters --------------------------
print("\n[1] Logins that are not lowercase (unreachable at the login screen)")
# Only e-mail logins: base/technical accounts ("User", "public") are matched by
# XMLID elsewhere and renaming them buys nothing.
mixed = Users.search([("active", "in", [True, False])]).filtered(
    lambda u: u.login and "@" in u.login and u.login != u.login.lower()
)
for user in mixed:
    target = user.login.lower()
    clash = Users.search(
        [("login", "=", target), ("id", "!=", user.id), ("active", "in", [True, False])],
        limit=1,
    )
    if clash:
        print("    SKIP  %-32s -> %-32s (taken by id %s)" % (user.login, target, clash.id))
        continue
    print("    id %-4s %-32s -> %s" % (user.id, user.login, target))
    if COMMIT:
        user.login = target
if not mixed:
    print("    (none)")

# --- 2. multi-company access --------------------------------------------
print("\n[2] Users that must be allowed into %s" % ARKA_COMPANY)
for login in GRANT_ARKA_TO:
    # =ilike: in preview mode the login has not been lowercased yet.
    user = Users.search([("login", "=ilike", login), ("active", "in", [True, False])], limit=1)
    if not user:
        print("    NOT FOUND  %s" % login)
        continue
    if arka in user.company_ids:
        print("    ok         %-32s already has %s" % (login, arka.name))
        continue
    print("    grant      %-32s + %s" % (login, arka.name))
    if COMMIT:
        user.company_ids = [(4, arka.id)]

# --- 3. accounts that can never authenticate -----------------------------
print("\n[3] Active internal users without a password")
env.cr.execute("SELECT id, login FROM res_users WHERE active AND password IS NULL ORDER BY id")
rows = env.cr.fetchall()
for uid, login in rows:
    user = Users.browse(uid)
    if user.share:
        continue
    print("    id %-4s %s" % (uid, login))
    if COMMIT and SEND_RESET_MAIL:
        user.action_reset_password()
        print("             -> reset mail sent")
if not rows:
    print("    (none)")
elif not SEND_RESET_MAIL:
    print("    (no mail sent — set SEND_RESET_MAIL = True to send set-password links)")

# --- summary -------------------------------------------------------------
print("\n[4] Resulting state for the three reported users")
for login in ("feri.01@erajaya.com", "mei.mey@erajaya.com", "sumida.01@erajaya.com"):
    # =ilike: pre-commit the login may still be stored with uppercase.
    user = Users.search([("login", "=ilike", login)], limit=1)
    if not user:
        print("    %-24s NOT FOUND" % login)
        continue
    # ``password`` never reads back through the ORM (write-only), so ask SQL.
    env.cr.execute("SELECT password IS NOT NULL FROM res_users WHERE id = %s", (user.id,))
    has_pwd = env.cr.fetchone()[0]
    print(
        "    %-24s id=%-4s pwd=%-5s companies=%s"
        % (
            user.login,
            user.id,
            has_pwd,
            ", ".join(user.company_ids.mapped("name")),
        )
    )

if COMMIT:
    env.cr.commit()
    print("\nCOMMITTED.")
else:
    env.cr.rollback()
    print("\nPreview only — nothing written. Set COMMIT = True to apply.")
