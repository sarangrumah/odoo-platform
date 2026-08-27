---
status: draft
generated_at: 2026-08-11T00:00:00Z
generator: claude-code-handwritten
module: custom_levis_bank_reconcile
manifest_version: 19.0.1.1.0
---

# custom_levis_bank_reconcile

## Purpose
Teaches the line-by-line bank matching wizard (`custom_account_reconcile`) what a
Levi's POS settlement is: which store it belongs to, that it arrived net of MDR,
and that a cash deposit is a sum of trading days. It is the interactive
counterpart of `levis.pos.clearing`, which settles a whole month in one run —
same facts, same sources, one line at a time.

## Business Flow
- **Accounting → Reconciliation → Bank Reconciliation** now shows Operating Unit,
  narrative type, gross and MDR per statement line, with filters for
  settlements / cash deposits / *Store Not Identified* / *Amount Disagrees With
  Narrative*, and group-by Operating Unit.
- **Match** opens a **full page** (`view_bank_reconcile_wizard_page`, `target=current`),
  not the generic modal: the operator has to read store, gross, fee, trading day and a
  dozen candidate rows at once, and a dialog collapses those columns. The statement
  list stays in the breadcrumb. On a card settlement it preselects candidates at the
  **gross** (`amount + MDR`), with the fee pre-filled on the clearing config's MDR
  expense account and the store's analytic. Reconciling books
  Dr tender receivable-clearing / Dr MDR / Cr suspense; the receivable clears in full.
- **Match** on a cash deposit offers **Suggest**: fills the selection largest day
  first, never exceeding the statement amount; the shortfall stays open on suspense.
- **Re-read Bank Narrative** (list server action) re-resolves lines after a MID
  mapping is added.

## Key Models
- `account.bank.statement.line` (`_inherit`) — candidate search. `_levis_is_tender_line`,
  `_levis_match_target`, `_levis_day_window`, `_levis_candidate_domain`, `_levis_same_ou`,
  overrides of `_get_match_candidates` / `_get_auto_match_candidate`.
  The *fields* (`levis_gross`, `levis_mdr`, `levis_ou_analytic_id`, …) live in
  `custom_levis_localization`, not here.
- `custom.bank.reconcile.wizard` (`_inherit`) — `levis_target`, `levis_gap`,
  `action_levis_suggest`, MDR defaults in `default_get`, analytic on the fee leg.
- `custom.bank.reconcile.wizard.line` (`_inherit`) — `levis_ou_analytic_id`,
  `levis_ou_matches` (rows of another store are decorated as a warning).

## Integration Points
- **Depends on:** `custom_levis_localization` (narrative parser, MID map, clearing
  config, statement-line fields) + `custom_account_reconcile` (the wizard).
  `auto_install = False` **on purpose**: both parents are installed on all seven
  Levi's databases, so auto-install would change the reconciliation screen on four
  production databases as a side effect of any module-list refresh. Install per
  database (`-i custom_levis_bank_reconcile`).
- Reuses `levis.clearing.config` for the tender receivable accounts, the AR
  fallback account, the MDR account and `settlement_lag_days` — there is no second
  configuration to keep in step.
- Reconciliation itself is still `_reconcile_with_amls` → core `reconcile()`.
  The only change made there is that `writeoff_vals` now honours
  `analytic_distribution`.

## Gotchas
- **Another store's receivable is never offered** on a mapped line. An empty
  candidate list means the store has no open tender receivable in the window —
  a finding, not a reason to widen. *Search More* is the explicit override.
- **The target is the gross, not the amount that landed.** A settlement whose
  narrative could not be read falls back to the statement amount, because an
  unparsed MDR is never assumed to be zero.
- **Cash is never auto-matched.** `_get_auto_match_candidate` returns empty for a
  deposit even when one receivable happens to equal it: one transfer covering one
  day is a coincidence, not evidence.
- **Adding a MID mapping does not rewrite history by itself.** The statement-line
  compute deliberately does not depend on `levis.bank.mid.map`; run *Re-read Bank
  Narrative* on the affected lines.
- **Page buttons return `None` on purpose.** In a full-page form that reloads the
  record; returning an action instead would push a new breadcrumb on every click.
  (In a dialog, returning `None` would close it — which is why the generic wizard
  in `custom_account_reconcile` returns an action and this one does not.)
- `action_open_match_wizard` **creates** the wizard record before opening: a page
  opens on a res_id, so without it the screen renders blank and `default_get`
  never sees the statement line.
- The day window is `settlement_lag_days` plus 12 days back / 3 forward. A
  settlement older than that needs *Search More*.

- **The candidate ranking no longer lives here.** `score()` moved to
  `levis.clearing.matcher._score_candidate` in `custom_levis_localization`, and
  `_get_match_candidates` calls it. The weights are unchanged (+100 exact
  residual, +40 same trading day / +20 decaying, +15 tender account, +<=10
  proximity); the point of the move is that the clearing's allocation and this
  wizard's ranking can no longer disagree about which open item answers a
  settlement first. Change the weights there, not here.
- The matcher's `tolerance` argument is read from
  `levis.clearing.config._match_tolerance()` and ships at **zero**, so ranking is
  byte-identical to before until a tenant sets it. When set, it can only lift a
  near-miss into view (+80, below the +100 an exact match scores). It never sizes
  a write-off. `_get_auto_match_candidate` is deliberately **not** tolerance-aware
  — auto-match still requires an exact hit.

## Out of Scope
- No bank statement import (`custom_bank_import`), no narrative grammars (those
  are `levis.bank.narrative` — adding a bank is one `_parse_<format>` there), no
  month-end clearing (`levis.pos.clearing`), no cron and no automatic posting.
