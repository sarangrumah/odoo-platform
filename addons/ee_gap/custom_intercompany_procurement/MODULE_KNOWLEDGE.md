---
status: draft
generated_at: 2026-07-02T07:54:45Z
generator: bootstrap-v1
module: custom_intercompany_procurement
manifest_version: 19.0.0.1.0
---

# custom_intercompany_procurement

## Purpose
This module automates the mirroring of purchase orders and stock pickings between sister companies within the Erajaya group, ensuring that when a purchase order is confirmed or an outgoing picking is validated in one company, corresponding draft sales orders and incoming pickings are automatically created in the other company. This process is designed to streamline intercompany transactions without manual intervention.

## Business Flow
1. **Purchase Order Confirmation:**
   - A purchase order (PO) is confirmed in the issuing company.
   - The module checks if there's a matching intercompany rule configured for mirroring POs.
   - If so, it creates a draft sales order (SO) in the receiving company.

2. **Stock Picking Validation:**
   - An outgoing stock picking is validated in the issuing company.
   - The module checks if there's a matching intercompany rule configured for mirroring pickings.
   - If so, it creates an incoming picking in the receiving company.

3. **Asset Loan Integration:**
   - When the mirrored SO in the receiving company is confirmed and includes the loan service line, the module automatically creates a draft internal asset-loan rental order (rental.order) in the receiving company.
   - The physical unit remains within the issuing company's location tree, while only the service line is invoiced.

## Key Models
- **account.intercompany.rule** — Defines mirroring rules between companies. Inherits from `account.intercompany.rule` and adds fields for PO and picking mirroring toggles.
- **purchase.order** — Extends purchase order to include intercompany mirroring logic.
- **sale.order** — Extends sales order to handle mirrored SOs and asset loans.
- **rental.order** — Links back to the original intercompany sales order that spawned it.

## Important Fields
- **account.intercompany.rule.mirror_purchase_order**: Boolean flag for enabling PO mirroring. Default is `False`.
- **account.intercompany.rule.mirror_picking**: Boolean flag for enabling picking mirroring. Default is `False`.
- **sale.order.x_custom_ic_mirror_so_id**: Reference to the mirrored SO in the receiving company.
- **sale.order.sale_order_id**: Links back to the original intercompany sales order that spawned it.

## Public Methods
- **purchase.order.button_confirm()**: Triggers the creation of a draft SO in the receiving company when a PO is confirmed.
- **sale.order.action_confirm()**: Creates an internal asset-loan rental order for mirrored SOs carrying the loan service line.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `custom_rental`, `purchase`, `sale_management`, `stock`
- **Inherits from:** `account.move` (adds `rental_line_ids`)
- **Extended by:** None
- **External calls:** None
- **Cross-vertical:** Deployed in arkaim, jds, ppob

## Gotchas
- The module assumes that the receiving company has a corresponding warehouse and sale journal configured.
- If no target warehouse is specified for pickings, the first available warehouse of the receiving company will be used.

## Out of Scope
- This module does not handle the automatic creation or mirroring of other types of documents (e.g., invoices).
- It does not cover scenarios where the mirrored SO includes physical products that need to be delivered.
- The module assumes that the loan service line is always present in the SO, which may not be the case for all sales orders.
