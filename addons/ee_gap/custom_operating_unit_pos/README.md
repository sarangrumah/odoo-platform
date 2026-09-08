# Custom Operating Unit — Point of Sale

Scopes the point of sale to its Operating Unit, and stamps the unit on every
line of the session closing entry.

A POS belongs to exactly one store, so the whole chain follows from
`pos.config.warehouse_id`: the config's unit, the sessions opened on it, the
orders rung up in them.

## The closing entry

Core builds the closing move on the **POS journal**, which is normally
company-wide and carries no unit of its own — so its lines have nothing to
inherit. Each of core's vals hooks is wrapped instead (sale, tax, combine/split
receivable, invoice receivable, stock expense), and the move itself is given the
session's unit afterwards.

Skipping this would leave the entire POS revenue stream outside per-unit
reporting while everything still *looked* right — which is exactly why
`custom_levis_localization` already stamps the analytic leg of the same
dimension on those very lines. On a Levi's database both land, from the two
modules, on the same line.

## History

The columns are created ready-made by the `pre_init_hook` (same reason as in
`custom_operating_unit_docs`: `pos_order` grows into the hundreds of thousands
of rows, and letting the ORM create the column would queue a full-table
recompute in one transaction). So the computes never fill history — the POS
passes in `scripts/ops/backfill_operating_unit.py` do:

    pos_config  ← its warehouse
    pos_session ← its config
    pos_order   ← its session

Verified on a clone of `rnd_levis`: 23 configs, 302 sessions, 5102 orders filled,
zero left over.
