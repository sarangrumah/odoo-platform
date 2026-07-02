---
status: draft
generated_at: 2026-07-02T07:18:43Z
generator: bootstrap-v1
module: custom_accounting_asset
manifest_version: 19.0.0.1.0
---

# custom_accounting_asset

## Purpose
This module provides a fixed asset register and depreciation schedule, enabling users to track assets over their useful lives, manage depreciation lines, and generate reports on asset values and accumulated depreciation.

## Business Flow
1. **Asset Creation**: Users create new fixed assets through the form view.
2. **Depreciation Schedule Generation**: The system automatically generates a depreciation schedule based on the selected method (straight line or declining balance) and useful life.
3. **Manual Posting Override**: Accountants can manually post individual depreciation lines using the `action_post_now` method.
4. **Disposal Management**: Assets can be disposed of, with journal entries recorded for disposal gains or losses.
5. **Report Generation**: Users generate an asset register report via a wizard, which details each asset's acquisition value, accumulated depreciation, and book value.

## Key Models
- `custom.fixed.asset` — Represents individual fixed assets; holds acquisition data, depreciation schedule, and state.
  - Fields: `name`, `code`, `acquisition_date`, `useful_life_months`, `depreciation_method`, `asset_account_id`, `depreciation_line_ids`.
- `custom.fixed.asset.depreciation.line` — Represents a single depreciation line for an asset; tracks monthly depreciation amounts and journal entries.
  - Fields: `date`, `amount`, `posted`, `move_id`.

## Important Fields
- **custom.fixed.asset**
  - `state` (Selection: draft/running/disposed/cancelled) — Tracks the lifecycle state of the asset.
  - `acquisition_value` (Monetary) — The initial cost of the asset.
  - `useful_life_months` (Integer) — Defines the total useful life in months.
- **custom.fixed.asset.depreciation.line**
  - `date` (Date) — Date when depreciation is applied.
  - `amount` (Monetary) — Depreciation amount for a given month.

## Public Methods
- `custom.fixed.asset.action_post_now()` — Manually posts a single depreciation line to the GL.

## Integration Points
- **Depends on:** custom_core, custom_pdp_audit, custom_accounting_full, custom_accounting_reports, account.
- **Inherits from:** None.
- **Extended by:** None.
- **External calls:** None / Pajakku /v1/coretax/...
- **Cross-vertical:** Deployed in arkaim, jds, ppob.

## Gotchas
- The depreciation schedule is generated based on the asset's current parameters and existing posted lines. Unposted lines are recalculated when the `depreciation_method` or other relevant fields change.
- Manual posting of depreciation lines can be done using the `action_post_now` method but should only be used in specific scenarios.

## Out of Scope
- This module does not cover asset acquisition, disposal journal entries, or integration with external tax systems. These functionalities are handled by other modules such as custom_accounting_full and account.
