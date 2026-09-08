---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_operating_unit
manifest_version: 19.0.0.1.0
---

# custom_operating_unit — Module Knowledge

## Purpose
Master data for the branch dimension: Head Office → Area → Store, as a real
model with a hierarchy, plus the user→unit assignment that the record rules in
the bridge modules read. Before this, "Operating Unit" was only an
`account.analytic.account` in a plan of that name, owned by
`custom_levis_localization`, with zero access-control effect.

## Models
- `operating.unit` — `code` (unique per company; for a store normally the
  `stock.warehouse.code`, which is the retail-import join key and must never
  change), `name`, `complete_name` (stored recursive), `ou_type`
  (`company`/`area`/`store`/`other`), `parent_id`/`child_ids`/`parent_path`
  (`_parent_store = True`), `company_id`, `analytic_account_id` (unique),
  `user_ids`, `manager_user_id`, `partner_id`, `note`.
- `operating.unit.mixin` — AbstractModel holding `operating_unit_id`
  (`index=True`, `ondelete="restrict"`) and `_check_operating_unit_allowed`.
- `res.users` — `operating_unit_ids`, `default_operating_unit_id`,
  `ou_all_access` (compute/inverse over `group_operating_unit_all`), and the
  three computed, **non-stored** fields the rules read: `ou_is_scoped`,
  `ou_allowed_ids`, `ou_include_untagged`.

## Key API
- `_ensure(code, name, company, ou_type="store", parent=None, **links)` —
  idempotent get-or-create keyed on (company, code). Never renames, only fills
  *empty* link fields. Every provisioning script and the Levi's migration go
  through it.
- `_analytic_index()` — `{analytic_id: ou_id}`, `ormcache`d. The stored-OU
  computes in the bridges run over whole journals; a per-line search would turn
  a 500-line bill into 500 queries. `create`/`write`/`unlink` clear the cache.
- `_descendant_ids()` — self + subtree, via `child_of` on `parent_path`.

## Security posture
- **Open by default.** `ou_is_scoped` is False when the user has no unit, holds
  `group_operating_unit_all`, or is `base.user_root`. Every rule is written as
  `<scoped domain> if user.ou_is_scoped else [(1, '=', 1)]`, evaluated as Python
  with `user` in scope. Installing the module therefore restricts nobody until
  an assignment is made — the only sane posture on nine live tenants.
- Groups: `group_operating_unit_user` (see the field / browse own units),
  `group_operating_unit_all` (head-office bypass), `group_operating_unit_manager`
  (CRUD + assignment, implies `_all`). Own `res.groups.privilege` under
  `custom_core.module_category_custom_platform`.
- `ir.config_parameter custom_operating_unit.include_untagged` (default `"1"`)
  decides whether documents with no unit stay visible to scoped users. Ship at
  `1`; flip per tenant only once the backfill coverage report is clean.

## Gotchas
- The write guard lives in a `@api.constrains`, not only in the rules: rules are
  bypassed by every `sudo()` path and a create-time check misses a document
  *moved* to another unit afterwards. `env.su` and the `ou_skip_check` context
  are the intentional escape hatches (crons, retail-import executor, queue_job,
  POS closing).
- Core's `_parent_store` raises `UserError("Recursion Detected.")` before the
  module's own `@api.constrains` on `parent_id` — tests must expect `UserError`
  for a cycle, `ValidationError` for the Head-Office rules.
- `models.Constraint(...)` table objects, not `_sql_constraints` (ignored in 19).
- `assertRaises` in Odoo's TransactionCase does not accept a tuple of exception
  classes.

## Related
- `custom_operating_unit_docs` / `_pos` / `_reports` — the isolation itself.
- `custom_levis_operating_unit` — migrates the 24 existing Levi's analytic OUs
  into this model without renaming anything.
- `custom_role_manager` — the orthogonal "which rights" axis.
