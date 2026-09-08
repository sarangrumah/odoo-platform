# Custom Role Manager

Named **roles** that bundle `res.groups`, so granting rights means picking
"Accounting Supervisor" instead of ticking thirty checkboxes.

## Why

Odoo grants access one group checkbox at a time. On a tenant with 80+ users that
is slow, unauditable, and inconsistent — two people with the same job title end
up with different rights. It is also how a tenant once lost every custom menu:
sixteen modules shared a single `res.groups.privilege`, the user form renders
groups that share a privilege as one pick-one dropdown, and saving a user
silently dropped the rest.

A role is **only a bundle**. It is never a `res.groups` and never a
`res.groups.privilege`, so it cannot reproduce that failure.

## Models

| Model | What it is |
|---|---|
| `custom.security.role` | A named position: `group_ids` + `implied_role_ids`, tagged by `role_domain` / `level` / `scope` |
| `res.users.role_ids` | The roles a user holds |
| `res.users.role_granted_group_ids` | Ledger — what the engine granted last time. **Only these may be revoked.** |
| `res.users.role_baseline_group_ids` | Snapshot of the groups the user held before roles were first applied. Never revoked. |
| `custom.security.role.assign` | Bulk-assignment wizard, bound to the Users list |

## Safe revocation

`_apply_security_roles()` revokes exactly

```
role_granted_group_ids − target − role_baseline_group_ids
```

so a group granted by hand, or additively by another module (the Keycloak SSO
mapping in `custom_finance_portal_sso`, for instance), is never taken away by a
role change. Every write goes through the ORM on `res.users.group_ids` —
membership is a computed closure over `res.groups.implied_ids`, and raw SQL on
`res_groups_users_rel` leaves that closure stale.

## Shipped roles

`data/seed_roles.py` holds the catalogue of standard Head Office and retail
positions (accounting staff/supervisor/manager, tax, treasury, purchasing,
sales, inventory, IT, auditor; store manager/supervisor/cashier/stock keeper,
area manager). It is Python, not an XML data file, because:

* `noupdate="1"` would freeze the roles forever — a corrected group list would
  never reach an installed tenant;
* `noupdate="0"` would clobber whatever an administrator changed locally.

`sync_seed_roles(env)` instead creates what is missing and refreshes only the
roles nobody has edited. Editing a shipped role sets `customized = True`, and
that role is left alone by every future upgrade (the form says so). Group
xml-ids that do not exist on the database are skipped, so the same catalogue
serves a POS retail tenant and a services tenant alike.

The sync runs from `data/seed_roles_load.xml`, a **non-`noupdate`**
`<function>` — so it fires on install *and* on every `-u custom_role_manager`.
That matters: a tenant that installs Point of Sale six months later gets the
cashier role's POS group on the next module update, whereas a `post_init_hook`
would have left the role permanently incomplete. There is also a
`Refresh shipped roles` server method (`action_sync_seed_roles`) for running it
by hand.

## Adding a position

Append a dict to `SEED_ROLES` and bump the manifest version — the next
`-u custom_role_manager` loads it. Prefer `implies` over copying groups.

## Gotchas

* **Do not reuse another module's `res.groups.privilege`.** This module declares
  its own (`res_groups_privilege_role_manager`) pointing at
  `custom_core.module_category_custom_platform`.
* `res.users.group_ids` holds only *direct* groups; the closure is
  `all_group_ids`. Never write to `all_group_ids`.
* The engine refuses to remove `base.group_system` from the current user, and
  from `base.user_admin` unless running as superuser — otherwise a mis-typed
  role locks everyone out of Settings.
* `group_role_manager` implies `base.group_erp_manager`: whoever edits roles can
  effectively grant any group in the system. Give it to administrators only; no
  business role in the catalogue implies it.
