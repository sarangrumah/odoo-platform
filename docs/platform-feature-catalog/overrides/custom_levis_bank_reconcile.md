---
status: override
module: custom_levis_bank_reconcile
source: manifest + models/*.py
---

# custom_levis_bank_reconcile

## Purpose
The monthly `levis.pos.clearing` run settles a whole period in one go. This
module teaches the **line-by-line bank matching wizard** the same four facts, for
the days Finance wants to look a single settlement in the eye.

It changes **what is offered**, not how a reconciliation is written: the write
path is still `custom_account_reconcile`'s `_reconcile_with_amls` on top of core
`reconcile()`.

## Business Flow
1. **The Operating Unit is on the tender line.** Every candidate row shows which
   store its POS receivable belongs to, so a settlement is never matched against
   another outlet's sales by accident.
2. **A card settlement is matched at its gross.** The bank pays gross minus MDR
   while the tender receivable is carried at gross, so matching on the amount
   that actually landed would never find anything. The wizard reads the gross and
   the fee out of the statement narrative, targets the gross, and offers the fee
   ready-booked to the MDR expense account with the store's Operating Unit on it.
3. **Cash deposits get a suggestion, capped at the deposit.** One transfer often
   covers several days of cash sales, so the wizard fills the selection
   largest-first up to — never over — the statement amount, and leaves the
   remainder open.
4. **The statement line records which store it came from.** MID/TID and keyword
   resolution is stored on the line itself, so the reconciliation list can be
   filtered and grouped per Operating Unit.

The module is tenant-scoped and self-installing: it activates only where both
parent modules are present.

## Key Models
- `account.bank.statement.line` (inherited) — stores the resolved store /
  Operating Unit from MID, TID or narrative keyword.
- `custom.bank.reconcile.wizard` and `custom.bank.reconcile.wizard.line`
  (inherited) — gross-based card matching, the MDR fee line, and the capped cash
  suggestion.

## Important Fields
- The resolved Operating Unit on `account.bank.statement.line` — what makes the
  reconciliation list filterable per store, and what stops a cross-store match.
- The gross-versus-net distinction on the wizard line: the target is the tender
  receivable's gross, and the MDR difference is offered as a booked fee rather
  than left as an unexplained residual.
