# -*- coding: utf-8 -*-
{
    "name": "Custom Role Manager",
    "summary": "Named security roles that bundle res.groups: pick 'Accounting Supervisor' "
    "instead of ticking thirty checkboxes, with safe revocation and shipped role templates "
    "for Head Office and retail positions.",
    "description": """
Custom Role Manager — Peran & Hak Akses
=======================================

Odoo grants rights one ``res.groups`` checkbox at a time. On a tenant with 80+
users that is both slow and unsafe: nobody can tell what "Accounting Staff"
is supposed to mean, and two users with the same job title end up with
different rights.

This module adds a **role** layer on top of the native groups, without
replacing them:

1. ``custom.security.role`` — a named bundle of groups (``group_ids``) that may
   inherit other roles (``implied_role_ids``), tagged by functional domain
   (accounting, inventory, …), organisational level (manager / supervisor /
   staff / read-only) and scope (head office / retail).
2. ``res.users.role_ids`` — assign one or more roles; the module reconciles
   ``res.users.group_ids`` through the ORM (never raw SQL — group membership is
   a computed closure over ``implied_ids``).
3. **Safe revocation.** The module remembers exactly which groups it granted
   (``role_granted_group_ids``) and which groups the user already had before
   roles were ever applied (``role_baseline_group_ids``). Changing a user's role
   revokes *only* what the role engine itself granted — groups granted by hand
   or by another module (SSO, for example) survive untouched.
4. **Shipped role templates** for the standard Head Office and store positions,
   defined in Python (``data/seed_roles.py``) so a platform upgrade can refresh
   them, while any role an administrator has edited is flagged ``customized``
   and left alone.
5. A **bulk assignment wizard** on the Users list, and a ``Re-apply Roles``
   button for repairing a user after manual tinkering.

Group xml-ids that do not exist on a database (module not installed there) are
silently skipped, so one seed catalogue serves every tenant of the platform.

Part of the Custom Platform — multi-tenant Odoo 19 for Indonesian SMB.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Custom Platform/Security",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": ["custom_core"],
    "capability_tags": [
        "rbac",
        "role-bundles",
        "user-provisioning",
        "access-rights",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/seed_roles_load.xml",
        "views/security_role_views.xml",
        "views/assign_role_wizard_views.xml",
        "views/res_users_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
