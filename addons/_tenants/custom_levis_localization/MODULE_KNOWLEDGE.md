---
status: draft
generated_at: 2026-07-02T08:56:04Z
generator: bootstrap-v1
module: custom_levis_localization
manifest_version: 19.0.1.0.0
---

# Levi's Localization (`custom_levis_localization`)

## Purpose
This module implements five specific requirements for the Levi's tenant: HS Code management on the product master, ensuring receipt quantities do not exceed demand quantities, skipping the inventory journal entry at goods receipt confirmation, generating branded payment vouchers and receipts, and providing a periodic inventory reconciliation tool that realigns GL inventory-asset accounts with actual on-hand stock value.

## Business Flow
1. **HS Code Management**:
   - Delivered as a `product.template` view that inherits `product.product_template_form_view` to surface the native `stock_delivery` `hs_code` field on the General Information tab (`views/product_template_views.xml:9-18`). There is no Python `product` override; the field itself comes from `stock_delivery`.
2. **Receipt Quantity Validation**:
   - On confirming an incoming stock picking, if any line's done quantity exceeds its demand quantity (compared with `float_compare`), a `UserError` is raised listing the offending products.
3. **Inventory Journal at Goods Receipt & Vendor Return (opt-in switch)**:
   - Governed by `ir.config_parameter` `custom_levis_localization.suppress_gr_journal` (default **OFF**). This build has no standard stock input/output interim accounts, so core real-time valuation posts nothing; the module books inventory GL directly via the category pair `property_stock_valuation_account_id` + `account_stock_variation_id` (same pair the Inventory Reconciliation tool uses).
   - Switch OFF (default): on a vendor **goods receipt** (source = supplier) it posts `Dr Stock Valuation / Cr Stock Variation` for `move.value` (ref `GR-VAL:<move id>`); on a vendor **return / RTV** (destination = supplier) it posts the exact reverse `Dr Stock Variation / Cr Stock Valuation` (ref `GR-RET-VAL:<move id>`). Both are idempotent by `ref` and only fire for `real_time` categories with the accounts + a stock journal set.
   - Switch ON (periodic): both receipt and return journals are suppressed; GL is trued up periodically by `levis.inventory.reconciliation`.
4. **Payment Vouchers & Payment Receipts**:
   - Two branded PDF documents are generated for payments on `account.payment`: a *Payment Voucher* for vendor/outbound payments and a *Payment Receipt* for customer/inbound payments. Each renders only for its matching payment direction.
5. **Periodic Inventory Reconciliation**:
   - Because receipts/deliveries do not post inventory journals in this setup, GL inventory-asset accounts drift from real on-hand value. `levis.inventory.reconciliation` computes, per valuation account, the actual stock value (`stock.quant.value`) vs the current GL balance and generates a DRAFT adjustment journal against an inventory-variation account for the accountant to review and post.

## Key Models
- `levis.inventory.reconciliation` — Manages periodic inventory reconciliations, computing differences between GL balances and actual stock values and producing a DRAFT `account.move`.
- `levis.inventory.reconciliation.line` — One line per stock-valuation account, holding the GL balance, stock value, and computed difference.
- `stock.move` — Overrides to skip GL journal entries on vendor goods-receipt moves.
- `stock.picking` — Overrides to validate receipt quantities against demand quantities.

## Important Fields
- **levis.inventory.reconciliation**:
  - `name`: Sequence-generated identifier. Defaults to `"/"` and is replaced in `create()` via the `levis.inventory.reconciliation` `ir.sequence` (prefix `INVREC/%(year)s/`).
  - `company_id`: Company for the reconciliation (defaults to the active company).
  - `date`: Date up to which posted GL balances are considered (default is today).
  - `journal_id`: General account journal used for generating the reconciliation entry.
  - `counterpart_account_id`: Inventory variation account where differences are booked when a category-level Stock Variation account is not set.
  - `line_ids`, `move_id`, `state` (draft/computed/generated), `total_difference` (computed sum of line differences), `currency_id`.

- **levis.inventory.reconciliation.line**:
  - `reconciliation_id`: Parent reconciliation (cascade delete).
  - `company_id`, `currency_id`: Related from the parent.
  - `account_id`: Valuation Account.
  - `counterpart_account_id`: Variation Account.
  - `book_value`: GL Balance.
  - `stock_value`: Actual on-hand stock value.
  - `difference`: Computed and stored, `stock_value − book_value`.

- **stock.move**:
  - `_is_levis_goods_receipt()`: True when the move enters from a supplier location (`location_id.usage == 'supplier'`).
  - `_is_levis_vendor_return()`: True when the move leaves to a supplier location (`location_dest_id.usage == 'supplier'`) — a vendor return / RTV.
  - `_levis_suppress_gr_journal()`: Reads the `suppress_gr_journal` config switch (default OFF).
  - `_should_create_account_move()`: Returns `False` for vendor receipts only when the suppress switch is ON; otherwise defers to core.
  - `_action_done()`: After super, calls `_levis_post_gr_journal()` (receipts) and `_levis_post_return_journal()` (vendor returns).
  - `_levis_book_valuation_entry(ref, label, incoming)`: Shared idempotent poster — `incoming=True` → Dr Valuation/Cr Variation; `incoming=False` → the reverse. No-op if already posted for `ref`, non-real-time category, missing accounts/journal, or zero `move.value`.

- **stock.picking**:
  - `button_validate()`: Validates the done quantity against demand quantities on incoming stock pickings (via `float_compare`). Raises an error if any line exceeds its demand.

## Public Methods
- **levis.inventory.reconciliation**:
  - `action_compute()`: Rebuilds lines, computing differences between GL balances and actual stock values.
  - `action_generate_move()`: Generates a DRAFT journal entry for the reconciliation and opens it.
  - `action_view_move()`: Returns an act_window action opening the generated `account.move`.
  - `_cron_generate_drafts()`: Creates one computed reconciliation per company and generates a DRAFT entry when a difference exists. Never posts automatically. Bound to an inactive monthly cron.

## Integration Points
- **Depends on**: `product`, `stock`, `stock_account`, `stock_delivery`, `purchase`, `account`.
- **Inherits from**: `stock.move` and `stock.picking`.
- **ir.sequence**: `seq_levis_inventory_reconciliation` (code `levis.inventory.reconciliation`, prefix `INVREC/%(year)s/`, padding 4).
- **ir.cron**: `cron_levis_inventory_reconciliation` runs `model._cron_generate_drafts()` monthly, shipped with `active=False`.
- **Reports**: Two `ir.actions.report` bound to `account.payment` (`action_report_payment_voucher`, `action_report_payment_receipt`) rendering QWeb templates `report_payment_voucher` / `report_payment_receipt`, using paperformat `paperformat_levis_payment` (`reports/paperformat.xml`).
- **Extended by**: None.
- **External calls**: None.
- **Cross-vertical**: The manifest names `prd_levis` / `rnd_levis` / `demo_levis` as the intended target databases, but nothing in the code enforces tenant scoping.

## Gotchas
- Tenant scoping is a deployment convention only — the manifest documents the Levi's databases as intended targets, but there is no runtime check preventing installation elsewhere.
- The `_cron_generate_drafts` cron is shipped with `active=False` (`data/inventory_reconciliation_data.xml:20`) and is monthly, so it does NOT run automatically unless a tenant enables it. When enabled it only creates DRAFT reconciliations/entries; it never posts.
- The payment reports are direction-guarded: the Payment Voucher renders only for outbound payments and the Payment Receipt only for inbound payments.

## Out of Scope
- This module does not cover inventory adjustments, backorders, or handling of internal transfers and manufacturing receipts. These functionalities are left to the core Odoo stock management processes.
- The GL-skip behavior focuses solely on vendor goods receipts; customer returns and outbound shipments keep posting normally.
- The payment vouchers and receipts are limited to vendor and customer payments; other types of financial transactions (e.g., intercompany) are not covered.
