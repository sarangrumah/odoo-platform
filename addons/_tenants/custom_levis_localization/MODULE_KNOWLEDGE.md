---
status: draft
generated_at: 2026-07-02T08:56:04Z
generator: bootstrap-v1
module: custom_levis_localization
manifest_version: 19.0.1.0.0
---

# Levi's Localization (`custom_levis_localization`)

## Purpose
This module implements four specific requirements for Levi's tenant, including HS Code management on product templates, ensuring receipt quantities do not exceed demand quantities, skipping inventory journal entries at goods receipt confirmation, and generating branded payment vouchers and receipts.

## Business Flow
1. **HS Code Management**:
   - During the creation or modification of a product template, users can now input and manage the HS Code.
2. **Receipt Quantity Validation**:
   - On confirming an incoming stock picking, if any line's done quantity exceeds its demand quantity, a `UserError` is raised listing the offending products.
3. **Inventory Journal Skipping at Goods Receipt Confirmation**:
   - For vendor goods receipts (moves from supplier locations), no GL journal entry is created, but the stock valuation layer still updates to maintain correct on-hand quantities and values.
4. **Payment Vouchers & Payment Receipts**:
   - Two branded PDF documents are generated for payments: one for vendor/outbound payments and another for customer/inbound payments.

## Key Models
- `levis.inventory.reconciliation` — Manages periodic inventory reconciliations, computing differences between GL balances and actual stock values.
- `stock.move` — Overrides to skip GL journal entries on certain types of stock moves.
- `stock.picking` — Overrides to validate receipt quantities against demand quantities.

## Important Fields
- **levis.inventory.reconciliation**:
  - `name`: Unique identifier for the reconciliation process, auto-generated if not provided.
  - `date`: Date up to which GL balances are considered (default is today).
  - `journal_id`: Account journal used for generating the reconciliation entry.
  - `counterpart_account_id`: Inventory variation account where differences are booked.

- **stock.move**:
  - `_is_levis_goods_receipt()`: Determines if a move is a vendor goods receipt.
  - `_should_create_account_move()`: Returns `False` for vendor receipts, skipping GL journal entries.

- **stock.picking**:
  - `button_validate()`: Validates the done quantity against demand quantities on incoming stock pickings. Raises an error if any line exceeds its demand.

## Public Methods
- **levis.inventory.reconciliation**:
  - `action_compute()`: Computes differences between GL balances and actual stock values.
  - `action_generate_move()`: Generates a draft journal entry for the reconciliation process.
  - `_cron_generate_drafts()`: Automatically creates reconciliations with DRAFT entries.

## Integration Points
- **Depends on**: `product`, `stock`, `stock_account`, `stock_delivery`, `purchase`, `account`.
- **Inherits from**: `stock.move` and `stock.picking`.
- **Extended by**: None.
- **External calls**: None.
- **Cross-vertical**: Deployed in specific Levi's databases (`prd_levis`, `rnd_levis`, `demo_levis`).

## Gotchas
- The module is tenant-scoped, meaning it should only be installed on the Levi's databases. Misinstallation can lead to unexpected behavior across other tenants.
- The `_cron_generate_drafts` method runs automatically for each company but does not post any journal entries; it merely creates DRAFT reconciliations.

## Out of Scope
- This module does not cover inventory adjustments, backorders, or handling of internal transfers and manufacturing receipts. These functionalities are left to the core Odoo stock management processes.
- It also does not handle customer returns or outbound shipments, focusing solely on vendor goods receipt confirmations.
- The payment vouchers and receipts are limited to vendor and customer payments; other types of financial transactions (e.g., intercompany) are not covered.
