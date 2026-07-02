---
status: draft
generated_at: 2026-07-02T08:46:25Z
generator: bootstrap-v1
module: custom_arka_aim_opening_balance
manifest_version: 19.0.1.0.0
---

# ARKA-AIM Opening Balances (31 May 2026)

## Purpose
This module loads the beginning balances for PT Aero Inovasi Media (AIM) and PT Aero Reksa Kreasi Angkasa (ARKA) as of 31 May 2026, creating necessary bank accounts if they are missing. It posts these balances as journal entries into the general journal.

## Business Flow
1. The module checks for the presence of specific bank accounts.
2. If any required accounts are missing, it creates them.
3. It then generates and posts opening journal entries for both companies on 31 May 2026.
4. The trial balance is verified to ensure that all debit and credit amounts match.

## Key Models
- **None**: This module does not define any new models but interacts with existing ones.

## Important Fields
- None: There are no specific fields defined in this module, as it primarily works with account.move records.

## Public Methods
- None: The module does not expose any public methods for direct user interaction.

## Integration Points
- **Depends on:** `account`
- **Inherits from:** `account.move` (adds journal entries)
- **Extended by:** None
- **External calls:** None
- **Cross-vertical:** Deployed in trn_arkaaim_begbal, prd_arkaaim

## Gotchas
- The module is idempotent and safe to re-run on upgrade.
- Companies are resolved by name, not hardcoded ID.
- Accounts are resolved by code within the company's `company_ids`, which means fixed external IDs are not portable across different companies.

## Out of Scope
- This module does not cover any additional business logic or data management beyond posting opening balances. If new requirements arise that involve more complex financial operations or data handling, a new custom module would be necessary.
