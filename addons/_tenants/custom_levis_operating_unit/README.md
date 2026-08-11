# Custom Operating Unit — Levi's Migration

Lifts the Operating-Unit dimension Levi's already runs — one analytic account
per store, wired to a warehouse and a purchase journal by
`custom_levis_localization` — into the platform's `operating.unit` master.

**Additive only.** Verified on a clone of `rnd_levis`: 25 units created (1 head
office + 24 stores, one of them archived to match its warehouse), every one
linked to its analytic account, warehouse and purchase journal, and the
`stock_warehouse` and analytic-account name/code tables byte-identical before
and after.

`stock.warehouse.code` is the key X24/X101 join on and drives the location
names and picking sequences. It is **copied** into `operating.unit.code`, never
modified — including for the head office, whose unit takes the EBR warehouse's
code so every unit is addressable the same way.

## After the migration

The Operating Unit is the master; the analytic account is one of its links.
Everything that reads `l10n_ou_analytic_id` keeps working, and picking a unit on
a journal item now fills that field — otherwise the ledger would quietly stop
carrying the dimension the P&L by branch, the GL analysis view and the retail
import are built on. The arrow never points the other way: this module never
writes `analytic_distribution`; `custom_levis_localization` still owns that.

## Adding areas

The migration builds a two-level tree (head office → stores) because that is
what exists today. Adding an area layer is pure data work afterwards — create a
unit with type *Area*, re-parent its stores — with no code change. An area
manager then needs exactly one assignment.

## Running it

Installed automatically wherever `custom_levis_localization` and
`custom_operating_unit_docs` are both present (`post_init_hook`). For a database
that already has the module, re-run it by hand:

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/90_migrate_operating_unit.py
