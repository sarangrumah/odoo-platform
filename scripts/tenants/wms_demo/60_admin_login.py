# -*- coding: utf-8 -*-
"""
demo_wms / 60 — administrator login for the demo.

Run:
    docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_wms --no-http \
        < scripts/tenants/wms_demo/60_admin_login.py

Promotes the built-in admin user to the requested credentials and ensures it
carries full administration rights (Settings / technical / all WMS groups), so
the demo has a usable login. Idempotent: re-running just re-asserts the values.
"""

env = env  # provided by `odoo shell`
log = lambda m: print("[60-admin] " + m)

LOGIN = "am.ademaryadi@gmail.com"
PASSWORD = "M@ryadi86!"
NAME = "Ade Maryadi"

# The administrator user shipped with every DB (id 2 / base.user_admin).
admin = env.ref("base.user_admin", raise_if_not_found=False)
if not admin:
    admin = env["res.users"].search([("login", "=", "admin")], limit=1)
if not admin:
    raise Exception("No admin user found in this database.")

admin.write({
    "name": NAME,
    "login": LOGIN,
    "email": LOGIN,
    "password": PASSWORD,
    "active": True,
})

# Ensure full admin rights (Settings group implies the rest).
grp_settings = env.ref("base.group_system", raise_if_not_found=False)
if grp_settings and grp_settings not in admin.group_ids:
    admin.write({"group_ids": [(4, grp_settings.id)]})

env.cr.commit()
log("admin user updated -> login=%s  (uid=%s, name=%s)" % (admin.login, admin.id, admin.name))
log("groups: system=%s" % bool(admin.has_group("base.group_system")))
log("DONE — log in with the email above.")
