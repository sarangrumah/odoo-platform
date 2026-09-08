---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_role_manager
manifest_version: 19.0.0.1.0
---

# custom_role_manager — Module Knowledge

## Purpose
A **role** layer over native `res.groups`. Administrators pick a named position
("Accounting Supervisor", "Store Manager") and the module reconciles
`res.users.group_ids` for them. Odoo ships nothing like this in Community or
Enterprise; OCA's `base_user_role` is not ported to 19.0 and models a role as a
group, which this platform cannot do (see Gotchas).

## Models
- `custom.security.role` — `name`, unique `code` (the key used by SSO mapping and
  provisioning scripts), `group_ids` (m2m `res.groups`), `implied_role_ids`
  (m2m self, so Staff ⊂ Supervisor ⊂ Manager), plus classification fields
  `role_domain` / `level` / `scope` and the two upgrade flags `is_seed` and
  `customized`. `_all_group_ids()` walks the `implied_role_ids` closure and is
  cycle-safe by construction (a `seen` set), independently of the
  `_has_cycle("implied_role_ids")` constraint.
- `res.users` — `role_ids`, plus two read-only ledgers:
  `role_granted_group_ids` (what the engine granted last time — the only groups
  it may revoke) and `role_baseline_group_ids` (what the user held before roles
  were ever applied — never revoked).
- `custom.security.role.assign` — transient bulk-assignment wizard, bound to the
  `res.users` list view (`binding_model_id` + `binding_view_types="list"`).

## Business flow
1. Assign `role_ids` on a user (form, wizard, or `res.users.create`).
2. `write`/`create` calls `_apply_security_roles()` unless the `role_apply`
   context flag is set (that flag is how the engine's own writes avoid
   recursing).
3. The engine computes `target = role_ids._all_group_ids()`, grants
   `target − group_ids`, revokes
   `role_granted_group_ids − target − role_baseline_group_ids`, then rewrites
   the ledger.
4. Editing a role's composition re-applies it to every holder, including
   holders of roles that *inherit* it (`_holder_roles()` walks upward).

## Important fields / conventions
- Membership writes always go through the ORM on `res.users.group_ids`.
  `group_ids` holds only **direct** groups; the implied closure is
  `all_group_ids` (Odoo 19 names — `groups_id` and `users` are gone). Raw SQL on
  `res_groups_users_rel` leaves the closure stale, which is why
  `scripts/tenants/levis/84_tidy_admin_rights.py` also goes through the ORM.
- `models.Constraint("UNIQUE (code)", ...)` — Odoo 19 ignores the legacy
  `_sql_constraints` list.
- The module declares its **own** `res.groups.privilege`
  (`res_groups_privilege_role_manager`, sequence 105) pointing at
  `custom_core.module_category_custom_platform`.

## Seed catalogue
`data/seed_roles.py::SEED_ROLES` — 18 positions covering Head Office
(accounting AP/AR, tax, treasury, supervisor, manager, auditor, purchasing,
sales, inventory, IT) and retail (store manager, supervisor, cashier, stock
keeper, area manager). `sync_seed_roles(env)` is idempotent, skips group xml-ids
absent from the database, refreshes only roles with `customized = False`, and
re-applies the result to every holder. It is invoked by
`data/seed_roles_load.xml` — a `<function model="custom.security.role"
name="_sync_seed_roles"/>` in a **non-noupdate** data block, so it runs on
install *and* on every module update. That is deliberate: with a `post_init_hook`
only, a tenant that installs an app later (POS, Coretax…) would keep a role that
is silently missing that app's group forever. A test covers exactly this.

## Gotchas
- **A role must never be a `res.groups.privilege`.** Groups sharing a privilege
  render as one pick-one dropdown on the user form, so saving a user keeps one
  group and silently drops the others — this emptied every custom menu for 72
  users on `prd_levis_begbal` once already.
- **Only the ledger is revocable.** Revoking "everything not in the target"
  would strip groups granted by hand or additively by another module
  (`custom_finance_portal_sso` writes `group_ids` with `Command.link`), which is
  the classic way an RBAC layer destroys a production tenant.
- **Lock-out guards**: `_check_role_lockout` refuses to drop `base.group_system`
  from `self.env.user`, and from `base.user_admin` outside `env.su`.
- `group_role_manager` implies `base.group_erp_manager` — role editors can
  effectively grant anything. It is deliberately not implied by any business
  role in the catalogue.
- Editing a shipped role sets `customized = True` and permanently opts it out of
  platform refreshes. Tell administrators to **duplicate** a seed role rather
  than edit it if they want upgrades to keep flowing.

## Related
- `custom_operating_unit` — the orthogonal "which data" axis (roles answer
  "which rights").
- `custom_finance_portal_sso` — Keycloak role names; should delegate to
  `custom.security.role.code`.
- `docs/platform/role-matrix.md` — the position matrix rendered for clients.
