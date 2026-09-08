# Custom Operating Unit

Operating Unit master data — Head Office / Area / Store — and the user
assignment that data isolation is built on.

## Why

Odoo has companies and warehouses and nothing in between. On this platform an
"Operating Unit" existed only as an `account.analytic.account` in a plan named
*Operating Unit*, created per store by `custom_levis_localization`. That is a
fine reporting dimension but it carries no hierarchy, no link to the warehouse
or the POS, and cannot be used for access control — before this module there was
not a single `ir.rule` in the repository that scoped anything by branch.

## What it adds

| Model / field | Purpose |
|---|---|
| `operating.unit` | `code`, `name`, `ou_type` (company / area / store / other), `parent_id` hierarchy, `analytic_account_id` |
| `operating.unit.mixin` | `operating_unit_id` + the write guard, inherited by the document models in the bridge modules |
| `res.users.operating_unit_ids` | The assignment |
| `res.users.ou_allowed_ids` | Computed: the assignment expanded down the tree — what the record rules read |
| `res.users.ou_all_access` | Friendly checkbox over `group_operating_unit_all` |

## Two properties worth stating

**Installing this restricts nobody.** `ou_is_scoped` is false for a user with no
unit assigned, and every rule short-circuits to `[(1,'=',1)]` for them. Scoping
begins when units are assigned — which is deliberate on a platform with nine
live tenants.

**An area is one assignment, not twelve.** `ou_allowed_ids` expands
`child_of` over `parent_path`, so an area manager assigned `AREA-JKT` sees every
store beneath it, and re-parenting a store updates every affected user with no
denormalised table to maintain.

## Linking, not replacing

`analytic_account_id` (and, in the bridges, the warehouse / journal / POS
config) point at records the tenant already has. `_ensure(code, name, company,
…)` is the idempotent provisioning entry point: it never renames an existing
unit and never overwrites a link that is already set, so a migration script can
be re-run safely. A store's `stock.warehouse.code` is a retail-import join key
and is never touched.

## Gotchas

* Isolation of the actual documents lives in `custom_operating_unit_docs` (and
  `_pos`, `_reports`), which auto-install per app. This module alone gives you
  master data and a screen.
* `ou_allowed_ids` is **not stored** — no column, no mass recompute at upgrade.
* `_analytic_index()` is `ormcache`d; anything that changes
  `analytic_account_id` must clear the registry cache (`create`/`write`/`unlink`
  already do).
* The write guard honours `env.su`, so crons, the retail-import executor and
  queue_job workers are unaffected.
