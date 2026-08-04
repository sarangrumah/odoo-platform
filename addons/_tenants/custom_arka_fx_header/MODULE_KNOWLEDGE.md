---
status: draft
generated_at: 2026-08-04T00:00:00Z
generator: hand-authored
module: custom_arka_fx_header
manifest_version: 19.0.1.0.0
---

# custom_arka_fx_header

## Purpose
Puts the **foreign-currency total** and the **applied exchange rate** into the
header of a customer invoice / vendor bill whose currency differs from the
company currency, so an approver sees both without scrolling and without
mentally inverting a rate. Display only — no posting, amount, or rate used by
the accounting engine is changed, and there is no schema change.

## Why it exists
Stock Odoo 19 already stores the rate on `account.move.invoice_currency_rate`
and renders it next to the currency in the header, but three things make it
unusable for this tenant:

1. It is printed in the `1 <company currency> = N <foreign>` direction —
   `1 IDR = 0.00037421 CNY`. IDR-based books quote the other direction
   (`1 CNY = 2,672.30 IDR`).
2. The document total in the foreign currency only appears at the bottom of the
   Invoice Lines tab.
3. The native block sits behind `base.group_multi_currency`, so it vanishes for
   any role that does not imply that group. The block added here carries no
   `groups` restriction.

## Business Flow
1. A user opens an invoice/bill written in a non-company currency.
2. `x_fx_is_foreign` computes True, revealing an `alert alert-info` block
   injected directly after the `oe_title` div (i.e. under the document number).
3. The block renders `amount_total` with the `monetary` widget (already in the
   document currency) and the rate as
   `1 <currency_id> = <x_fx_rate_company_per_unit> <company_currency_id>`.
4. On a same-currency document, or on a `move_type == 'entry'`, the block is
   invisible and the form is byte-for-byte the stock layout.

## Key Models
- `account.move` (inherited) — adds two non-stored computed display helpers.
  No overrides of any core method.

## Important Fields
- `account.move.x_fx_is_foreign` (Boolean, computed, **non-stored**) — True when
  `move_type` is in `out_invoice/out_refund/out_receipt/in_invoice/in_refund/
  in_receipt` **and** `currency_id != company_currency_id`. Journal entries
  (`entry`) are deliberately excluded: a raw entry has no single document
  currency, so the block would be misleading.
- `account.move.x_fx_rate_company_per_unit` (Float, `digits=(16, 4)`, computed,
  **non-stored**) — `1 / invoice_currency_rate`, i.e. how many units of company
  currency one unit of the document currency is worth. Guarded against a zero
  rate (returns 0.0 rather than raising `ZeroDivisionError`); real data with
  `invoice_currency_rate == 0.0` exists on `trn_arkaaim`.

## Public / Overridden Methods
None. Only the two `@api.depends` computes:
- `_compute_x_fx_is_foreign()` — depends on `move_type`, `currency_id`,
  `company_currency_id`.
- `_compute_x_fx_rate_company_per_unit()` — depends on `invoice_currency_rate`.

## Views
`views/account_move_views.xml` inherits `account.view_move_form` and xpaths
`//div[hasclass('oe_title')]` `position="after"`. The block is `name=
"arka_fx_header"` for downstream targeting.

## Gating & Scope
Tenant-scoped to the arkaaim DBs, enforced by *placement* (`addons/_tenants/`)
and by install, not by a company flag — the module is inert on any document
whose currency equals the company currency, so it is harmless if installed
elsewhere. `depends: ["account"]` only. Deployed on `prd_arkaaim` and
`trn_arkaaim`.

## Tests
No automated tests. Verified manually against a full clone of `prd_arkaaim`:
`BILL/2026/07/0002` renders 20,000.70 CNY at 2,672.2963, whose product
(53,447,796.61) matches the ledger's `amount_total_signed` (53,447,796.69) to
within rounding; an IDR customer invoice shows no block and an unchanged
layout; `get_view` as a plain accounting user still contains the block.
