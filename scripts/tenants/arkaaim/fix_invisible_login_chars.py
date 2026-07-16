# -*- coding: utf-8 -*-
"""Strip invisible Unicode characters from res.users logins.

WHY THIS IS NEEDED
------------------
A login pasted from a spreadsheet or chat can carry a zero-width / invisible
character (word joiner U+2060, ZWSP U+200B, BOM U+FEFF, non-breaking space ...).
It is impossible to see in the UI and impossible to type, so the user simply can
never log in — the stored login never matches what they enter. On prd_arkaaim
Tania's login was "⁠tania.01@erajaya.com" and she had never logged in once.

WHAT IT DOES
------------
Finds active users whose login contains an invisible character, shows the
codepoints, and rewrites the login to the cleaned value. Refuses to touch a user
when the cleaned login would collide with another existing user (that needs a
human decision — likely a duplicate account to merge or archive).

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < fix_invisible_login_chars.py

By default it only PREVIEWS. Set FIX_COMMIT = True to persist.
"""

import unicodedata

# ----- knobs -------------------------------------------------------------
FIX_COMMIT = False  # True to persist; False = preview only
# Characters that are invisible/zero-width and must never appear in a login.
INVISIBLE = {
    "​",  # zero width space
    "‌",  # zero width non-joiner
    "‍",  # zero width joiner
    "⁠",  # word joiner
    "﻿",  # zero width no-break space / BOM
    " ",  # non-breaking space
    "᠎",  # mongolian vowel separator
}
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)


def clean(login):
    """Drop invisible characters and surrounding whitespace."""
    return "".join(ch for ch in login if ch not in INVISIBLE).strip()


def describe(login):
    """Render the login with its suspicious codepoints spelled out."""
    parts = []
    for ch in login:
        if ch in INVISIBLE:
            parts.append("<U+%04X %s>" % (ord(ch), unicodedata.name(ch, "?")))
        else:
            parts.append(ch)
    return "".join(parts)


users = env["res.users"].search([("active", "=", True)])
affected = users.filtered(lambda u: u.login and clean(u.login) != u.login)

if not affected:
    print("No logins contain invisible characters — nothing to do.")
else:
    print("Users whose login carries invisible characters:")
    print("-" * 78)

fixed = 0
for user in affected:
    target = clean(user.login)
    print("\n  id=%-4s name=%s" % (user.id, user.name))
    print("    stored : %s" % describe(user.login))
    print("    cleaned: %s" % target)
    print("    last login: %s" % (user.login_date or "NEVER — consistent with an untypable login"))

    if not target:
        print("    !! SKIPPED: cleaning would leave an empty login.")
        continue
    clash = env["res.users"].search([("login", "=", target), ("id", "!=", user.id)], limit=1)
    if clash:
        print("    !! SKIPPED: login %r already belongs to id=%s (%s)." % (target, clash.id, clash.name))
        print("       Two accounts for one person — merge or archive one by hand.")
        continue

    user.login = target
    fixed += 1
    print("    -> fixed")

print("\n" + "-" * 78)
if FIX_COMMIT:
    env.cr.commit()
    print("COMMITTED — %d login(s) fixed." % fixed)
else:
    env.cr.rollback()
    print("DRY RUN — rolled back (%d login(s) would be fixed). Set FIX_COMMIT = True." % fixed)
