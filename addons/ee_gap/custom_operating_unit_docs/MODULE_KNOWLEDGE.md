---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_operating_unit_docs
manifest_version: 19.0.0.1.0
---

# custom_operating_unit_docs — Module Knowledge

## Purpose
Turns the Operating Unit from master data into enforced data isolation on the
accounting, stock, purchase and sales documents. Auto-installs wherever those
apps are present, so a tenant without them never sees it.

## What it adds
- `operating_unit_id` (stored, indexed, `readonly=False`) on `account.move`,
  `account.move.line`, `account.payment`, `account.bank.statement.line`,
  `stock.picking`, `stock.move`, `stock.quant`, `purchase.order`, `sale.order`.
- Link fields on `operating.unit`: `warehouse_id` (unique), `journal_id`,
  `purchase_journal_id`, plus the `_warehouse_index()` / `_journal_index()`
  ormcaches.
- Nine `ir.rule` records, all the same shape (see below).
- `_prepare_invoice()` on PO and SO carries the unit onto the invoice.

## Where the unit comes from
| Model | Source |
|---|---|
| `account.move` | the journal's unit, else the user's default |
| `account.move.line` | the move; if none, the first unit found in `analytic_distribution` |
| `account.payment`, `account.bank.statement.line` | related to the move |
| `stock.picking` / `stock.move` | `picking_type_id.warehouse_id` |
| `stock.quant` | `location_id.warehouse_id` (recomputed freely — quants churn) |
| `purchase.order` | `picking_type_id.warehouse_id` |
| `sale.order` | `warehouse_id` (hence the `sale_stock` dependency, not `sale`) |

Every compute except the quant one **skips records that already have a unit**,
so a manually chosen unit is never silently overwritten.

## The two things that make this safe
1. **`pre_init_hook` creates the columns, not the ORM.** A stored computed field
   whose column is missing makes Odoo flag the entire table for recompute in one
   transaction at the end of the registry load. On a large `account_move_line`
   that is an outage of exactly the shape that took 13 databases down here once.
   The hook also creates a **partial** index (`WHERE operating_unit_id IS NOT
   NULL`), free to build while the column is empty. Later version bumps must do
   the same from a `pre-migration.py` — call `hooks.create_operating_unit_columns(cr)`.
2. **The rules neutralise themselves.** Every `domain_force` reads
   `<scoped domain> if user.ou_is_scoped else [(1, '=', 1)]`, and `ou_is_scoped`
   is false for a user with no unit. Installing the module restricts nobody.

## Rule shape
```python
(['|', ('operating_unit_id', '=', False)] if user.ou_include_untagged else []) \
    + [('operating_unit_id', 'in', user.ou_allowed_ids.ids)] \
    if user.ou_is_scoped else [(1, '=', 1)]
```
The untagged branch is what keeps history visible on day one, before the
backfill. Flip `custom_operating_unit.include_untagged` to `"0"` per tenant once
`scripts/ops/report_operating_unit_coverage.py` reports zero.

`account.journal` and `account.account` are deliberately **not** scoped:
restricting them breaks posting, the reconciliation widget and the report
engine in ways that are very hard to diagnose, and the document rules already
achieve the isolation.

## Gotchas paid for once
- **A record rule does not stop a scoped user *moving* a document to another
  unit.** Odoo checks write access against the record's pre-write state. The
  guard is `operating.unit.mixin._check_operating_unit_allowed`.
- **`@api.constrains` alone was not enough.** Constraints are validated at
  *flush*, and the flush may run through a different (elevated) environment than
  the one that made the change — in which the guard short-circuits on `env.su`
  and lets the foreign unit through. The mixin therefore also checks from
  `create`/`write`, which pins the check to the environment that actually wrote.
  A test covers the move-it-afterwards case precisely because it slipped through
  the first implementation.
- `domain_force` is `safe_eval`'d as Python: it must be a **single physical
  line**, an indented continuation raises `unexpected indent`.
- `sale.order.warehouse_id` lives in `sale_stock`, not `sale`.
- `precompute=True` is not usable here — the dependencies (`analytic_distribution`,
  `warehouse_id`) are not precomputed themselves.

## Related
- `scripts/ops/backfill_operating_unit.py` — batched SQL history fill, run
  outside the `-u` window.
- `scripts/ops/report_operating_unit_coverage.py` — the go/no-go for
  `include_untagged = 0`.
- `custom_operating_unit_pos`, `custom_operating_unit_reports`,
  `custom_levis_operating_unit`.
