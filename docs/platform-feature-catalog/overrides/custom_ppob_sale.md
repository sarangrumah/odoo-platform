---
status: override
module: custom_ppob_sale
source: manifest + models/*.py
---

# custom_ppob_sale

## Purpose
The **transactional core** of the PPOB vertical: the transaction state machine,
atomic drawdown against both the mitra wallet and the provider deposit, dispatch
to the provider adapter, and the reaper that resolves transactions left hanging.

## Business Flow
- `custom.ppob.transaction` runs the state machine
  `pending → inquiry_ok → in_progress → success / failed / timeout / refunded`.
- On dispatch: atomic wallet debit, atomic provider deposit (bucket) debit, then
  the provider adapter call. **GL is posted by the wallet and bucket helpers**,
  each posting its own paired entry — there is no separate compound sale move to
  reconcile.
- Per-transaction `vat_mode`, `dpp_amount` and `ppn_amount` are computed for
  reporting and for the daily rollup faktur (PMK-63/2022: margin, DPP nilai lain,
  gross, exempt). **PPN is recognised in the GL at the rollup faktur, not per
  transaction** — the volume makes per-transaction recognition unworkable.
- A cron reaper resolves stale `in_progress` transactions by calling the provider
  adapter's `status()` **before** refunding. It never blind-refunds, and it
  honours each provider's own `stale_threshold_minutes`. This is the guard
  against paying a customer twice when the provider was merely slow.
- A manual-sale wizard covers the operations desk.

## Key Models
- `custom.ppob.transaction` — the state machine and the tax fields.
- `custom.ppob.manual.sale.wizard` — operator-initiated sale.
- `custom.ppob.wallet.move`, `custom.ppob.provider.bucket.move` (inherited) —
  gain the `ppob_transaction_id` back-reference.
- `stock.picking` (inherited) — links physical voucher stock where a product
  class carries it.

## Important Fields
- `custom.ppob.transaction.state` — the workflow spine; `in_progress` is the
  state the reaper watches.
- `custom.ppob.transaction.vat_mode` / `dpp_amount` / `ppn_amount` — inherited
  from the product class, then frozen on the transaction so a later class change
  cannot restate history.
- Per-provider `stale_threshold_minutes` — how long a transaction may sit in
  `in_progress` before the reaper investigates it.
