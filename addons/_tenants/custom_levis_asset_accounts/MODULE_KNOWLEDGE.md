---
status: draft
generated_at: 2026-08-18T00:00:00Z
generator: claude-code-handwritten
module: custom_levis_asset_accounts
manifest_version: 19.0.2.1.0
---

# custom_levis_asset_accounts

## Purpose
Seeds the EBR (Erajaya/Levi's) asset categories as `custom.fixed.asset.group`
records and wires each one to the right accounts in the Erajaya chart, so the
fixed-asset engine in `custom_accounting_asset` has somewhere to book to. The
module carries no models of its own beyond an `_inherit` on the group; it is
configuration expressed as code.

## Business Flow
Two `<function>` data records run on every module update, in this order:

1. `_seed_erajaya_asset_groups` — upserts twelve categories: six owned fixed
   assets (`FA-*`, cost `1205xxxxxx` / accum `1205 2xxxxx` / expense
   `7204xxxxxx`) and six right-of-use counterparts under PSAK 73 (`ROU-*`, cost
   `1206 1xxxxx` / accum `1206 2xxxxx` / expense `7205xxxxxx`).
2. `_apply_erajaya_revaluation_defaults` — fills the IAS 16 revaluation accounts
   (OCI surplus, impairment loss, OCI income, retained earnings) onto every group
   of that company.

Both are idempotent and non-destructive: an existing group only has its **empty**
fields filled, never overwritten, so a manual correction by Finance survives the
next upgrade.

## Key Models
- `custom.fixed.asset.group` (`_inherit`) — the seed methods live here. No new
  fields; the module only populates the ones `custom_accounting_asset` defines.

## Integration Points
- **`custom_accounting_asset`** owns `custom.fixed.asset.group` and the
  depreciation engine that reads these defaults.
- **`l10n_erajaya`** supplies the chart. Accounts are resolved **by code within
  each company** — `account.account.code` is company-dependent in Odoo 19, so
  resolution must go through `with_company()`.
- A company without the Erajaya codes (e.g. an `id_psak` company) resolves
  nothing and is skipped automatically, which is what keeps this tenant module
  safe to install anywhere.

## Gotchas
- **A group with no `default_journal_id` breaks `action_confirm()`.** All six
  owned categories were once seeded without one and every asset confirmation
  raised until the journal was wired by hand. The seed now resolves the company's
  `DEPRE` general journal for any category that has a depreciation-expense
  account. Land carries no expense account and is deliberately left without a
  journal — it is not depreciated.
- **Land is cost-only, in both branches.** Neither `FA-LAND` nor `ROU-LAND` gets
  an accumulated-depreciation or expense account: the chart has none for them
  (accum starts at `1205201000` / `1206201000`, i.e. Building). If Finance ever
  leases land on a term that must be amortised under PSAK 73, those two accounts
  have to be added to the chart before `ROU-LAND` can depreciate.
- **ROU useful life is a placeholder.** 60 months exists only to keep the form
  valid; a right-of-use asset amortises over its own lease term and must be set
  per lease.
- **ROU expense defaults to the G&A line.** `7205xxxxxx` ("Depreciation - Right
  of Use Asset - X") mirrors how the owned groups point at `7204xxxxxx`. The
  chart also carries a *selling* variant (`7110001000` / `7110002000` /
  `7110099000`); an asset booked against a store cost centre needs its expense
  account overridden on the asset itself, because only one of the two can be a
  group default.
- The note claiming `1205202000` "Accum depre - Vehicles" is missing from the
  chart is **stale** — the account exists and `FA-VEH` resolves it.

## Out of Scope
- Depreciation posting, revaluation and disposal — all in
  `custom_accounting_asset`.
- The opening asset register and per-unit subledger — see the ARKA-AIM modules.
- Creating the accounts themselves; the chart is `l10n_erajaya`'s job.
