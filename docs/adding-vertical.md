# Adding a New Vertical

A vertical is a domain-specific Odoo module (HR, Logistics, Manufacturing,
Property, etc.) that builds on `custom_core` and the platform's EE-gap addons.
This guide is for **operators**: it tells you what to expect when a developer
hands over a new vertical, where it appears, and how to keep it safe.

For the **developer-side** fork procedure see
`addons/verticals/_template/README.md`.

## Contents

- [Where new verticals live](#where-new-verticals-live)
- [Where they appear in Odoo](#where-they-appear-in-odoo)
- [Install / update](#install--update)
- [Migrations](#migrations)
- [Per-vertical security scoping](#per-vertical-security-scoping)
- [Acceptance checklist](#acceptance-checklist)

## Where new verticals live

Filesystem layout:

```
addons/
  verticals/
    _template/                  # canonical template, do not modify in-place
      README.md                 # 12-step fork checklist
      __manifest__.template.py  # placeholder manifest
      custom_vertical_example/     # fully-formed reference module
    custom_logistics/              # real verticals live next to _template
    custom_property/
    ...
```

The `_template/` folder is **never installed**; it has no `__manifest__.py` at
its root. The example sub-folder `custom_vertical_example/` *can* be installed for
exploration but should not run in production.

## Where they appear in Odoo

- **Apps list**: filter by category. The platform uses
  `Vertical/<Subcategory>` (e.g. `Vertical/Logistics`). Operators can install
  with the standard Apps UI once the module is in the addons path.
- **Top navbar**: every vertical attaches a top-level menu under the shared
  `custom_core.menu_custom_root`. So all verticals appear together under the **Custom**
  menu, not scattered across stock Odoo menus.
- **Settings -> Users -> Groups**: each vertical declares its groups under the
  `custom_core.module_category_custom_platform` category, keeping the user form
  organized.

## Install / update

Standard commands (executed inside the `web` container or via the host
`Makefile` wrapper):

```bash
# install
make install MODULE=custom_logistics DB=erp_dev

# upgrade after pulling new code
make update MODULE=custom_logistics DB=erp_dev

# upgrade everything (use sparingly in prod)
make update-all DB=erp_prod
```

Behind the scenes these run `odoo -i|-u <module> -d <db> --stop-after-init`.

**Production discipline:**

1. Always run `make update` against a freshly restored copy of the prod DB
   first.
2. Check the log for `WARNING odoo.modules.loading` lines.
3. Take a `pg_dump` snapshot before the production update.
4. Schedule updates inside the announced maintenance window.

## Migrations

Odoo's migration mechanism (folder layout):

```
custom_logistics/
  migrations/
    19.0.1.0.0/
      pre-migrate.py
      post-migrate.py
      end-migrate.py
```

- Bump the manifest `version` whenever a migration is required.
- `pre-migrate.py` runs **before** the new module XML loads; use it to rename
  columns, drop deprecated constraints, or pre-seed data.
- `post-migrate.py` runs **after** loading; use it for data backfills that
  depend on new fields.
- Always log progress; long-running migrations should batch and commit.
- Never touch `custom_pdp_audit_event` from a migration script (the postgres
  trigger will block it; that is by design).

## Per-vertical security scoping

Three layers, in order of strength:

1. **Group membership** (`security/<slug>_security.xml`). Each vertical must
   declare at least `group_user` and ideally `group_manager`. Both sit under
   `custom_core.module_category_custom_platform`.
2. **Model access** (`security/ir.model.access.csv`). One row per (model,
   group) combination. Read-only groups must have `perm_write=0,perm_create=0,
   perm_unlink=0`.
3. **Record rules** (`security/<slug>_record_rules.xml`). For multi-tenant
   data scope by `company_id` or `tenant_id`. Always test with at least two
   tenants in staging.

Cross-vertical do's and don'ts:

- **Do** name groups `<vertical>.group_user` so they namespace cleanly.
- **Do** use `pdp_class` on every new personal-data field
  (see `docs/pdp-compliance.md`).
- **Don't** grant verticals the `custom_pdp_masking.group_unmask_specific` group by
  default.
- **Don't** depend on another vertical's groups; depend on `custom_core` groups
  only. If two verticals need to share access, expose the shared group from
  `custom_core` itself.

## Acceptance checklist

Before signing off a new vertical for production:

- [ ] Installs cleanly on an empty DB.
- [ ] Updates cleanly on a copy of prod.
- [ ] Appears under **Custom** menu, not scattered.
- [ ] Groups visible under `Custom Platform` in user form.
- [ ] All new personal-data fields tagged with `pdp_class`.
- [ ] Record rules verified with two-tenant test.
- [ ] Migration scripts (if any) tested forward and (where possible) backward.
- [ ] Vertical-specific runbook exists at `docs/verticals/<slug>.md`.
- [ ] Entry added to `docs/architecture.md` service table if it introduces a
      new external dependency (Kafka topic, S3 bucket, scheduled job, etc.).
