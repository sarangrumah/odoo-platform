---
status: authored
module: custom_asset_lifecycle
manifest_version: 19.0.1.2.0
---

# custom_asset_lifecycle

## Purpose

`custom_accounting_asset` knows how to depreciate an asset and how to dispose of
one. It has no vocabulary for anything in between: a unit comes back from the
field broken, another never comes back at all, a third goes out to a vendor
under warranty and returns three weeks later. This module gives the register
that vocabulary, and attaches the resulting history to the physical serial.

Built for the ARKA-AIM drone fleet (3,590 units, 3,100 physical serials), but
nothing in it is tenant-specific.

## The rule everything hangs on: condition is not state

`condition` is a **separate field from** `state`. A damaged, under-repair or
reported-missing asset stays `state = 'running'` and keeps depreciating — IAS
16.55 / PSAK 16: depreciation does not cease while an asset is idle or retired
from active use, only at derecognition.

So **nothing in this module writes `state`**. The monthly depreciation cron,
which searches `state = 'running'`, keeps picking these assets up.
`test_depreciation_continues_while_in_repair` pins that down, and
`test_missing_asset_keeps_depreciating_until_written_off` pins down the missing
case specifically, because that is the one users expect to behave otherwise.

Depreciation stops at exactly one point: the existing disposal wizard.
`action_open_writeoff_wizard` routes to it with zero proceeds and the configured
loss account prefilled, so the loss equals net book value.

## Business Flow

```
        ┌── Report Damage ──► damaged ──► (repair confirmed) ──► in_repair
        │                        │                                  │
   ok ──┤                        │                        (repair done) ──► repaired
        │                        └──────────── Return To Service ◄──────────┘
        │                                            │
        └── Report Missing ──► missing ──────────────┘  (found again)
                                 │
                                 └── Write Off ──► written_off  ← state becomes 'disposed'
                                          │
                                          └── Register Replacement ──► new asset at fair value
```

1. **Report Damage** — flags the units, transfers their serials to the damage
   location, and optionally opens one `repair.order` per unit in one of three
   channels. Equipment cards are provisioned on the fly, because a repair with
   no equipment card records its history nowhere.
2. **Repair** — `in_house`, `third_party` (vendor required) or `warranty` (claim
   reference required). A warranty claim is excluded from the unit's lifetime
   repair cost, which is the figure Finance uses to decide whether a unit is
   worth keeping.
3. **Return To Service** — brings the serial home from the damage location and
   clears the condition. Blocked while a repair order is still open.
4. **Report Missing** — flags the units with a BAP reference and moves their
   serials to the lost/missing location so they stop counting as available
   on-hand stock. The asset keeps depreciating.
5. **Write Off** — the standard disposal wizard. This is derecognition.
6. **Register Replacement** — the client hands over a replacement unit that
   becomes company property. Capitalised at fair market value, linked to the
   unit it replaces, **and its acquisition journal is posted here**.

## Why the replacement wizard posts a journal entry

`custom.fixed.asset` posts **nothing** on creation. Assets are expected to reach
the GL through the vendor bill behind `custom_asset_from_receipt`. A replacement
unit handed over by a client has no vendor bill, so creating the asset alone
would grow the register while the GL stood still — silent register-vs-GL drift,
the same class of gap that once surfaced as a 34.98m variance on the ARKA-AIM
register.

So the wizard books it itself, at fair value:

```
DR  Fixed asset (the group's asset account)      market value
    CR  Compensation income (configured)         market value
```

Unticking *Post Acquisition Entry* is possible for the case where Finance has
already booked the entry by hand; the form says plainly what that costs.

The two events are deliberately kept apart — derecognising the old unit (loss =
NBV) and recognising the new one (income = fair value) are separate entries, and
their difference lands in profit or loss.

## Models

| Model | Role |
|---|---|
| `custom.fixed.asset` (inherit) | `condition`, missing report fields, `equipment_id`, repair figures, replacement lineage, the serial-movement helpers |
| `custom.asset.condition.log` | One immutable row per condition event. Carries the asset's code, serial and lot, so it *is* the unit's incident history |
| `repair.order` (inherit) | `x_repair_channel`, vendor, warranty claim fields, `x_fixed_asset_id`, and condition sync on state change |
| `maintenance.equipment` (inherit) | Non-stored `fixed_asset_id` back-link |
| `res.company` / `res.config.settings` | Damage and lost/missing locations, loss and compensation accounts, replacement journal, equipment category |

Wizards: `custom.asset.report.damage.wizard`,
`custom.asset.report.missing.wizard`, `custom.asset.replacement.wizard`,
`custom.asset.equipment.provision.wizard`, sharing
`custom.asset.condition.wizard.mixin` so the two reporting wizards cannot drift
apart on which assets they accept.

## Gotchas

**A serial's position must be read from the net, not from the largest quant
row.** A badly-sourced picking leaves `+1` and `-1` in the same location while
the unit really sits elsewhere. `custom_asset_stock_link` ≤ 19.0.1.1.0 filtered
`quantity > 0` inside the query, read the `+1` and ignored the `-1` beside it —
which had **2,572 of the 3,590 ARKA-AIM units showing in `ARKA/Stock` when they
were really in `WH/RUKO GUDANG PALEM`**. Fixed in `custom_asset_stock_link`
19.0.1.2.0; `_resolve_serial_source_location` here resolves the source the same
way and refuses to move a serial that nets to zero rather than minting another
negative quant.

**Equipment cards are keyed on the asset code, not the physical serial.** Core
maintenance puts a global `unique(serial_no)` on that column and the physical
serials are *not* unique — the ARKA-AIM listing repeats eight battery serials,
which fails the bulk provisioning partway through the fleet. The asset code is
unique per company and is already what each unit's `stock.lot` is named. The
physical serial goes into the note and `partner_ref`.

**Destinations must belong to the asset's own company.** Warehouse codes are not
unique across companies, so resolving `DMG` by code alone hands company 1's damage
warehouse to company 2 — which is exactly what the first production run of
`setup_asset_lifecycle.py` did to PT Aero Reksa Kreasi Angkasa. Stock then refuses
the transfer with a generic company-inconsistency error, in front of an operator
reporting a broken unit. Since 19.0.1.1.0 a constraint on `res.company` rejects the
configuration outright, the wizards name both companies if it happens anyway, and
the script resolves per company and creates a location for a company that has no
warehouse of its own.

The wizards also carry **no default destination**. Defaulting from
`self.env.company` looked harmless and was not: select an asset of another company
— which a two-company register makes easy — and the active company's location was
pinned onto it. 19.0.1.2.0 resolves the destination per asset instead, and the
replacement wizard takes its accounts from the replaced asset's company rather
than the active one.

**"The company's warehouse" is not a single thing.** PT Aero Inovasi Media has
four, all on sequence 10, so `search([...], limit=1)` resolves by id — and two of
the four are the damage and lost warehouses, the last place a returning unit
should be sent. Anywhere a warehouse has to be guessed, the register is asked
which one actually holds the fleet, and an explicitly ordered search is only the
last resort.

**Return To Service goes back to where the unit actually was.** The condition event
records `from_location_id` before the unit moves, because once it is sitting in the
damage warehouse nothing else knows where it came from. A fleet spread over several
locations has no single home, and the accounting asset location is not always mapped
to a warehouse one — on `prd_arkaaim` the ARKA units have no mapping at all, so
before 19.0.1.2.0 returning one to service failed with a message about damage
locations that had nothing to do with the real problem.

**Moving a serial posts nothing.** These units are already capitalised. They
live in the *Fixed Assets (Non-Valuated)* category at zero cost, so none of the
three conditions in `stock_account`'s `_should_create_account_move()` can be
met. `test_damage_moves_the_serial_and_posts_no_journal_entry` asserts a zero
`account.move` delta, and `setup_asset_lifecycle.py` asserts it again over the
whole fleet.

**Register-only units have no serial and are skipped, not rejected.** 490 of the
ARKA-AIM units carry no `lot_id` at all. Reporting damage on one records the
condition and moves nothing; the wizard shows how many were skipped.

**A finished repair does not return a unit to service.** The unit is still
physically in the damage warehouse when the repair order closes, so `repaired`
is its own condition and returning it home is an explicit act — it involves a
stock move somebody has to actually perform.

**View inheritance cannot select a group by its `string`.** The groups
`custom_repairs` adds carry no `name`, so the repair form extension inherits the
core `repair.view_repair_order_form` instead and appends into `//sheet`.

## Deployment

`scripts/tenants/arkaaim/setup_asset_lifecycle.py` — dry run by default,
`APPLY=1` to write. Wires the damage/missing locations (the client already
created the `DMG` and `WH/LM` warehouses), resyncs every unit's physical
position, and provisions equipment cards. It deliberately does **not** pick the
loss and compensation-income accounts: it warns loudly that Finance must choose
them, because write-offs and replacements refuse to post without them.

## Tests

`tests/test_asset_lifecycle.py` — 28 tests. Notably: depreciation continues
through damage and repair; a write-off closes the condition and stops it;
replacement posts the acquisition entry at fair value and gives the new unit a
full life; warranty is excluded from lifetime cost; a serial with an offsetting
negative quant is sourced from the right shelf; a serial that is nowhere is
refused; duplicate physical serials do not block equipment provisioning.

`custom_asset_stock_link`'s `test_cron_syncs_stale_positions` fails on a
database restored from production — the cron's `limit=2000` batch never reaches
the test's asset among 3,590. It fails identically on unmodified code; it is not
a regression.
