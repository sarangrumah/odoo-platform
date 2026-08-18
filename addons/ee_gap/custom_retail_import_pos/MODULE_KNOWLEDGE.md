---
status: draft
generated_at: 2026-08-05T00:00:00Z
generator: claude-code
module: custom_retail_import_pos
manifest_version: 19.0.0.6.0
---

# custom_retail_import_pos

## Purpose
The POS half of the retail importer. `custom_retail_import` deliberately does **not** depend on `point_of_sale` — the ARKA-AIM tenant runs the importer without POS, and a hard dependency would force-install the POS application there — so everything that only makes sense once `pos.order` exists lives in this bridge instead. `auto_install: True`, so it appears by itself on any tenant that has both.

Its job is to make POS session close book **exactly** the amounts the source workbook already states, rather than whatever Odoo's own tax engine would recompute from prices.

## Business Flow
- **Source amounts survive the import.** `pos.order.line` gains `ri_src_net` / `ri_src_tax` / `ri_src_discount` / `ri_is_return`, filled by the X24DN and X48 executors from the workbook's own columns. `_prepare_base_line_for_taxes_computation` feeds `ri_src_net` / `ri_src_tax` into the tax engine's `manual_tax_amounts` hook.
- **Why that hook is needed:** the source file truncates net per line (`net = trunc(total / 1.11)`, `tax = total - net`) while Odoo rounds tax globally per order. Without the override the two disagree by ±1 rupiah per line — small individually, material over 16k orders.
- **Returns move to their own COA.** A line with `ri_is_return` is re-pointed from `Gross Sales-<category>` to `Sales Return-<category>` via `_ri_return_account`, so returns report separately instead of netting silently against revenue.
- **Discounts ride the store's own closing entry.** `pos.session._create_account_move` appends the source `NET DISCOUNT AMOUNT` reclass to the session's closing move **while it is still draft**, rather than posting a separate summary journal. A store can tie its own closing entry to its own day; it cannot tie a detached summary journal to anything.
- **The reclass counterparty follows whichever account core booked the line to**, decided by `ri_is_return` and computed by the pure helper `_ri_reclass_legs`:
  - sale &rarr; Dr `Sales Discount-<cat>` / Cr `Gross Sales-<cat>` (grosses revenue back up);
  - return &rarr; Dr `Sales Return-<cat>` / Cr `Sales Discount-<cat>` (grosses the return back up and gives the discount back).
- **Descriptive columns are kept on the posted records** so the ledger stays auditable against the workbook: cashier (`ri_staff_id` / `ri_staff_name`), the four discount slots folded into `ri_discount_type` / `ri_discount_code` / `ri_discount_description`, and the transaction's member / notes / Omni order id on `pos.order`.

## Key Models
- `pos.order.line` (inherit) — the `ri_src_*` amount trio, `ri_is_return`, the cashier and discount-slot columns, `_ri_return_account`, `_prepare_base_line_for_taxes_computation`.
- `pos.order` (inherit) — cashier, member, customer phone, transaction note, Omni order id.
- `pos.session` (inherit) — `_ri_discount_reclass_line_vals` + the `_create_account_move` override.

## Integration Points
- **`custom_accounting_reports`** — the `Sales Detail (XStore X24DN)` report reads `pos.order.line` and `ri_src_discount`. That module archives the menu on tenants with no POS; this module's `post_init_hook` re-shows it when POS arrives later. The lookup is a soft `env.ref(..., raise_if_not_found=False)` **on purpose**: a real dependency on `custom_accounting_reports` would stop this module auto-installing on a tenant that has the importer and POS but not the reports module.
- **`custom_retail_import`** — supplies the `ri_src_*` values; this module never parses a file itself.

## Gotchas
- **Adding a hard dependency here breaks `auto_install`.** `auto_install: True` fires only when *every* dependency is already installed, so each new entry in `depends` narrows the set of tenants that get the bridge automatically. Reach for a soft `env.ref` or an `in self.env` guard instead.
- **`pos.order.line.discount` is 0 on imported lines.** The X24DN discount is booked as a contra-revenue reclass, not as a line discount, so anything reading `discount` sees zero — the real figure is `ri_src_discount`.
- **POS prices here are tax-inclusive**: `price_unit` equals `price_subtotal_incl` per unit and is already net of discount.
- The discount reclass must be appended while the closing move is **draft**; after `_create_account_move` returns and the move posts, the same edit would need a reversal instead.
- **A return's discount must never gross up `Gross Sales`.** Until 18-Aug-2026 the reclass used `Gross Sales-<cat>` as the counterparty for every discounted line, so a returned item left `Sales Return-<cat>` sitting at the amount NET of discount *and* inflated revenue the line never earned. Both halves are fixed by keying the counterparty off `ri_is_return`.
- **X24DN signs a return's `NET DISCOUNT AMOUNT` negative**, matching its negative net, so `_ri_reclass_legs` normalises to a magnitude before applying direction. An exchange can still net a whole category to the opposite sign, which flips the legs rather than writing a negative debit — both cases are covered in `tests/test_reclass_legs.py`.

## Out of Scope
- File parsing, profiles, feeds and the mailbox bridge — see `custom_retail_import`.
- The X-store vs Odoo reconciliation report — see `custom_retail_import_recon`.
- COGS booking for these sales — see `levis.cogs.run` in `custom_levis_localization`; Odoo 19 has no FIFO vacuum.
