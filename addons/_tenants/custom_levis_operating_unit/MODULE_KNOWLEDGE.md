---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_levis_operating_unit
manifest_version: 19.0.0.1.0
---

# custom_levis_operating_unit — Module Knowledge

## Purpose
Lifts the Operating-Unit dimension Levi's already runs — one
`account.analytic.account` per store, wired to a warehouse and a per-store
purchase journal by `custom_levis_localization` — into the platform's
`operating.unit` master. Auto-installs where that localization and
`custom_operating_unit_docs` are both present.

## What it does
`models/setup.py::migrate_levis_operating_units(env)` — idempotent, additive:

| Source (existing) | Becomes |
|---|---|
| `res.company.l10n_ho_analytic_id` | the head-office unit, keyed on the **EBR warehouse's code** |
| `stock.warehouse.l10n_ou_analytic_id` | one store unit per warehouse, `code = warehouse.code` |
| `stock.warehouse.l10n_purchase_journal_id` | `operating.unit.purchase_journal_id` |
| `pos.config.warehouse_id` | `pos.config.operating_unit_id` (when the POS bridge is installed) |

An archived store gets an archived unit, fully wired, so reactivating it stays
the one-liner it is today.

`models/levis_links.py` gives `account.move.line` an onchange + a create-time
default that fills `l10n_ou_analytic_id` from `operating_unit_id` **when empty**.
After the migration the unit is the master, but the P&L by branch, the GL
analysis view and the retail import all read the analytic leg — it must keep
being written. The arrow never points the other way: this module never touches
`analytic_distribution`, `custom_levis_localization` still owns that.

It also relabels `l10n_ou_analytic_id` / `l10n_ou_analytic_display` to
"Operating Unit (Analytic)" — Odoo warns when two fields of a model share a
label, and the two dimensions must be told apart on screen.

## Non-negotiables
- **`stock.warehouse.code` is never modified.** It is the key X24/X101 join on,
  and it drives the location names (`14696/Stock`) and the picking sequences. It
  is *copied* into `operating.unit.code`.
- The analytic account, the purchase journal and the `pos.config` keep the names
  `41_normalize_ou.py` gave them. A test asserts warehouses and analytics are
  unchanged across a run.
- `_ensure()` never renames an existing unit and only fills *empty* links, so
  re-running is a no-op.

## Verified
On a clone of `rnd_levis` (2026-08-11): 25 units — 1 head office (`EBR`) + 24
stores, one archived — every one linked to its analytic, warehouse and purchase
journal; `stock_warehouse` and the Operating Unit analytics byte-identical before
and after. The single analytic left unlinked is the archived "My Company"
duplicate, which is correct.

## Running it again
`scripts/tenants/levis/90_migrate_operating_unit.py` (`RUN_DRY=1` by default) —
for databases where the module is already installed, or after
`41_normalize_ou.py` adds stores.

## Related
- `custom_levis_localization` — owns the analytic leg and the seeding.
- `custom_operating_unit` / `_docs` / `_pos` — the master, the isolation.
- `scripts/tenants/levis/41_normalize_ou.py` — the naming pass this builds on.
