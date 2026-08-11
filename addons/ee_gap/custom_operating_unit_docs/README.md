# Custom Operating Unit — Documents

Stamps the Operating Unit on accounting, stock, purchase and sales documents,
and isolates them: a store user sees — and can book onto — only their own unit.

Auto-installs wherever Accounting and Inventory are present.

## What you get

* A stored, indexed `operating_unit_id` on the nine document models, derived
  from the journal, the warehouse, or (for a journal item) the analytic
  distribution. A unit chosen by hand is never overwritten.
* Record rules scoping all nine — written so a user with **no unit assigned is
  unrestricted**. Installing this module restricts nobody.
* A server-side guard that refuses a foreign unit at create *and* at write,
  because a record rule checks a document's pre-write state and would happily
  let a store user move a document to another store.

## Two design decisions worth knowing

**Stored column, not a JSONB domain.** `analytic_distribution` keys are
comma-joined ids across plans ("12,45"), so matching one analytic cannot use the
GIN index — it needs a LATERAL unnest per row, and that domain would be injected
into *every* `account.move.line` query, reconciliation included. An indexed
`int4` is three orders of magnitude cheaper.

**The columns are created by a `pre_init_hook`.** When the ORM finds a stored
computed field with no column it flags the whole table for recompute in a single
transaction. On a large `account_move_line` that is an outage. History is filled
separately by `scripts/ops/backfill_operating_unit.py`, in batches, outside the
`-u` window.

## Rollout

1. `-u` the module (fast — the hook only adds empty columns).
2. `RUN_DRY=0 … < scripts/ops/backfill_operating_unit.py`, then
   `VACUUM (ANALYZE) account_move_line;`.
3. `scripts/ops/report_operating_unit_coverage.py` until it reports zero.
4. Only then consider `custom_operating_unit.include_untagged = 0`.
5. Assign units to users **last** — that is the moment isolation switches on.
