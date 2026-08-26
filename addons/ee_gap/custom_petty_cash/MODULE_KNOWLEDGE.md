# custom_petty_cash — Module Knowledge

## Purpose
The cash-advance cycle Odoo does not have. Neither Community **nor Enterprise**
ships an employee-advance concept — the Expenses app only knows "the employee
already paid, reimburse them", so money always moves *after* the spend. This
module supplies the other direction: request → approval → Bank-Out disbursement
→ realization (third-party vendor bill *or* plain expense) → return/reimburse →
settlement, with Kartu Uang Muka / Outstanding / Aging monitoring and advance
ceilings.

(The OCA reference implementation, `hr_expense_advance_clearing`, is not ported
to 19.0 and cannot be ported as-is: Odoo 19 removed `hr.expense.sheet`.)

## Models
- `petty.cash.type` — per-(company, kind) map from an advance type to its
  advance account, its four journals, its sequence and its limits. `kind` ∈
  `pc_initial` / `pc_realization` / `pc_claim` (the 0.6.0 store-float families)
  and `cash_advance` / `petty_cash` / `other` (pre-0.6.0, untouched by the
  float); `is_default` pre-selects one per company (constrained to one).
  Unique `(code, company_id)`.
- `petty.cash.float` — one revolving float per (company, Operating Unit).
  Carries the store's plafon and the four balances. See **Store float** below.
- `petty.cash.request` — pengajuan + pencairan + settlement. Inherits
  `mail.thread`, `mail.activity.mixin`, `approval.mixin`, `pdp.audited.mixin`.
  State: `draft → to_approve → approved → disbursed → in_realization → settled`
  (+ `cancelled`). `amount_outstanding` is the net balance of advance-account
  lines tagged to the request (`account.move.petty_cash_request_id`).
- `petty.cash.request.line` — optional detail lines (what the money is for).
- `petty.cash.review.wizard` — Finance's batch approve / send-back / refuse with
  a reason that lands in each request's chatter.
- `petty.cash.realization` — pertanggungjawaban; `action_post` builds the GL.
- `petty.cash.realization.line` — `line_type` `third_party` / `expense`.
- `account.move` — tagged with `petty_cash_request_id` / `petty_cash_realization_id`.
- `hr.employee.pc_advance_limit` / `hr.job.pc_advance_limit` — advance ceilings.
- `res.company` / `res.config.settings` — the *legacy* company-wide accounts +
  journals, plus params.
- `petty.cash.report.statement` / `.outstanding` / `.aging` — report engine
  subclasses; registered in `REPORT_MODEL_MAP` (see `models/report_dispatch.py`).

## Configuration resolution chain
Every account/journal lookup is **request → type → company**:

```python
account = (self.advance_account_id
           or self.advance_type_id.advance_account_id
           or self.company_id.petty_cash_advance_account_id)
```

The `res.company.petty_cash_*` fields predate `petty.cash.type` and are
deliberately **kept** as the bottom of the chain, so tenants configured before
0.5.0 (all four Levi's DBs, two of them holding live requests) keep working with
`advance_type_id` unset. `migrations/19.0.0.5.0/post-migrate.py` mirrors each
configured company into a "Petty Cash" type with `limit_enforcement = "off"`
and back-fills existing requests — behaviour after the upgrade is identical to
before it.

`_pc_payment_journal()` / `_pc_expense_journal()` live on the **request**, not
the realization, so all four lookups are type-aware in one place.

## Accounting
| Step | Dr | Cr |
|---|---|---|
| Disburse | Advance (per type, per employee) | Bank |
| 3rd-party bill | Expense+PPN | AP |
| 3rd-party PPh (custom_tax_id, auto) | AP | Hutang PPh |
| 3rd-party pay (Payment journal) | AP | Advance |
| Expense | Expense (COA) | Advance |
| Return | Bank | Advance |
| Reimburse | Advance | Bank |
| Settle | *advance lines reconcile to zero* | |
| Settle (foreign currency) | *exchange difference via `currency_exchange_journal_id`* | |

The Payment journal's payment-method `payment_account_id` is auto-set to the
advance account (`_configure_payment_journal`), so `account.payment.register`
credits the advance instead of a bank outstanding account.

### Multi-currency
Every generated line carries `currency_id` **and** `amount_currency`, built by
`request._pc_leg(amount_cur, amount_comp)`. Two rules that are easy to get wrong:

- `currency_id` is set even when it equals the company currency — Odoo stores it
  there too, and leaving it blank parks `amount_currency` at 0, which breaks
  foreign-currency reconciliation and the FX revaluation report.
- Convert **once per balanced pair** (`_pc_conv`) and pass the two halves.
  Converting each leg independently can round apart and the move refuses to
  post. `_post_expense_entry` therefore credits the *sum of the per-line
  conversions*, never a fresh conversion of the total.

`amount_outstanding` is in the **request's** currency; `amount_outstanding_company`
is the same balance in company currency and is the one to aggregate — summing
`amount_outstanding` across mixed currencies is meaningless. Both the
Outstanding and Aging reports and the limit checks use the company-currency
field.

`action_settle` tags any exchange-difference entry `reconcile()` produces with
`petty_cash_request_id` (`_pc_tag_exchange_moves`), so the FX move shows on the
smart button and in the Kartu Uang Muka instead of making the card look unclosed.

## Store float (0.6.0)
Every store (Operating Unit) is granted a revolving float — 1.000.000 by
default, `ir.config_parameter custom_petty_cash.initial_amount`, overridable per
store on `petty.cash.float.amount_plafon`. The three `pc_*` kinds are the whole
mechanism:

| Kind | Draws on the float? | Bank-Out? | Gate |
|---|---|---|---|
| `pc_initial` "Petty Cash Awal" | *grants* it | yes | ≤ the store's plafon |
| `pc_realization` "Realisasi" | reserves from **draft** | no | ≤ available |
| `pc_claim` "Claim" | no | yes | none — it *is* the over-plafon escape hatch |

```
available = Σ granted (approved pc_initial) − Σ (requested − realized) over open pc_realization
```

Three things about that formula are deliberate and easy to "fix" wrongly:

- **The reservation starts at `draft`** (`FLOAT_OPEN_STATES`). Finance asked for
  it: otherwise a store queues five drafts that each look affordable alone.
- **Realizing frees exactly what was realized** — "saldo pulih sesuai nilai yang
  direalisasikan". Reserve 300k, realize 250k → available climbs by 250k, and
  the un-realized 50k stays reserved until `action_close_release` hands it back.
  The cash for that 50k never left the drawer, so releasing it books nothing.
- **`amount_available` ≠ `amount_gl_balance`.** Available is the control ledger
  and assumes the realized spend gets replenished; the GL balance is what the
  advance account says and drops with every posted realization. They re-converge
  when the top-up is booked. Both are on the float form, labelled, with the
  reason in an inline alert — do not "reconcile" them by changing either.

`pc_realization` / `pc_claim` requests have **no disbursement step**: the money
is already in the store's drawer, so `_pc_realizable_states()` lets a realization
be recorded straight from `approved`, and `action_settle` routes to
`_settle_float_request()` (which releases the reservation) instead of demanding
a zero GL outstanding.

`float_id` is a **stored compute that never creates**. A compute that created
floats would spawn one every time an employee opened a blank request form;
creation happens only in `action_approve` on a `pc_initial` request and on the
Finance Configuration screen, and `action_approve` then calls
`rec._compute_float_id()` by hand because "a record I just created now exists"
is not a dependency change the ORM can see.

The module ships the kinds and the engine but seeds **no type records**:
`custom_petty_cash` is shared by six DBs and two of those tenants never asked for
the store float. `scripts/tenants/levis/101_setup_petty_cash_store_float.py`
(idempotent, PREVIEW by default) opts one tenant in — three types per company
inheriting the default type's accounting map, plus one float per OU analytic.

## Finance review + dashboard (0.6.0)
- **Finance Review ▸ Review Queue** — `action_petty_cash_review`, domain
  `state = to_approve`, with a dedicated list carrying inline Approve /
  Send Back buttons. The `petty.cash.review.wizard` is bound to the list
  (`binding_model_id`) for the multi-record case with a mandatory reason.
- **Finance Review ▸ Store Floats** — plafon / granted / reserved / available /
  GL per OU. Exhausted stores are red, under-20% ones amber.
- **Finance Review ▸ Outstanding per Operating Unit** — pivot-first, pre-grouped
  by OU × state.
- **Dashboard** — `action_petty_cash_dashboard`, `list,kanban,pivot,graph,form`
  over the same search view (filters per kind, overdue, reserving-float, this
  month; group by OU / employee / type / kind / status / month). Export is
  Odoo's native list export, so nothing custom to maintain.

`ir.actions.act_window` takes **`group_ids`**, not `groups_id`, on Odoo 19 —
the rename cost one install run.

## Limits
Resolution order for the outstanding ceiling: **employee → job → type**; `0.0`
at a level means "no limit here" and falls through. `limit_per_request`,
`max_open_requests` and `block_when_overdue` come from the type only.

`limit_enforcement` ∈ `off` (default, and what the migration seeds) / `warn`
(chatter note) / `block` (`UserError`). Checked at:
- `action_submit` — early, while the employee can still fix the amount;
- `action_disburse` — the authoritative gate; the amount and the peer set can
  both have moved since submission, and this is when the cash leaves.

Not at `action_approve`: the approver is the one who grants exceptions, via
`group_petty_cash_limit_override` (granted to nobody by default).

The peer set includes state `approved`, and `_pc_committed_company()` values an
approved-but-undisbursed peer at its **requested amount** — it has no journal
entries yet, so its GL outstanding is zero, and two same-afternoon requests
would otherwise each see an empty ledger and both pass.

## Reuse
- Approval: `approval.mixin` (custom_approval_engine) — `action_submit` calls
  `_approval_request_or_proceed`; `_approval_on_granted` → `action_approve`.
- Withholding/PPN: set `tax_ids` + `x_custom_withholding_category_id` on the
  bill line; `custom_tax_id.account_move._post` applies PPh + bukti potong.
- Reports: `custom.report.engine` / `custom.report.wizard.mixin` /
  `REPORT_MODEL_MAP` in custom_accounting_reports; aging reuses its `BUCKETS`.
  The **statement inherits `custom.report.partner.card.base`**, not the plain
  engine, for its `_flatten_for_screen` + `_xlsx_body`.
- OU: `l10n_ou_analytic_id` merged into `analytic_distribution` (guarded on
  `_fields` so it's a no-op without the localization).

## Gotchas
- Requires an Advance account + Bank-Out + Payment journals configured (on the
  type or the company) before disbursing / posting third-party lines.
- **The Payment journal must be dedicated.** `_configure_payment_journal`
  rewrites `payment_account_id` on every payment-method line of the journal it
  is handed. Point it at an ordinary bank journal and every vendor payment on
  that bank silently starts crediting the advance account. Levi's and ARKA both
  use a dedicated `PCPAY` cash journal.
- `report_dispatch.py` mutates the shared `REPORT_MODEL_MAP` at import — the
  addon is shared, so all three report codes appear on every DB that installs it.
- **A report code must be registered in TWO places**: `REPORT_MODEL_MAP` in
  `models/report_dispatch.py` *and* the `t-elif` chain in
  `reports/petty_cash_templates.xml`. Miss the first and the code silently falls
  back to the Trial Balance; miss the second and the PDF renders empty.
- PDF vouchers live in `reports/petty_cash_vouchers.xml` and use a self-contained
  `<main>` wrapper — no `web.html_container` (asset-callback stall). **`<style>`
  and `<meta>` must sit INSIDE `<main>`**: Odoo 19 keeps only the `//main`
  subtree, so the 0.4.0 voucher's `<head>` stylesheet printed unstyled.
- `l10n_ou_analytic_id`'s plan is resolved through
  `custom_petty_cash.ou_plan_name` (falling back to
  `custom_accounting_reports.branch_plan_name`, then `"Operating Unit"`). An
  unresolvable plan **widens** the field to every analytic account rather than
  blocking it — ARKA-AIM has no "Operating Unit" plan and the field was dead
  there. ARKA sets the param to `"Project"`.
- Odoo 19 renames that bite here: `account.move.payment_id` → `origin_payment_id`
  (used by the statement's movement classifier), `res.users.groups_id` →
  `group_ids`, and `_sql_constraints` is silently ignored — `petty.cash.type`
  uses `models.Constraint` (verified present in `pg_constraint` as
  `petty_cash_type_code_company_uniq`).
- On Odoo 19 `account.account.code` is company-dependent and `code_store` can
  hold **stale** keys for companies the account no longer belongs to. Always
  pair a code search with `('company_ids','in',company.id)` — prd_arkaaim's
  account 73 demonstrates this.
- `tests/test_request_flow.py::test_third_party_requires_attachment` fails on an
  ARKA tenant clone (`hr_expense._check_payable_receivable` wants a due date on
  payable lines). Verified identical on untouched 0.4.0 code — pre-existing, not
  a regression.

- CodeQL's `py/clear-text-logging-sensitive-data` treats any constant whose name
  contains *employee* as personal data, so printing one fails the scan. The
  ARKA setup script therefore calls its analytic-plan constant
  `ADVANCE_SLICE_PLAN_NAME` (value still `"Employee"`, `ir.config_parameter` key
  still `custom_petty_cash.employee_plan_name`). CodeQL ignores inline
  suppression comments, so renaming is the only fix that works.

## Tenant configuration
`scripts/tenants/arkaaim/setup_cash_advance.py` — idempotent, PREVIEW by
default. Maps CA → `1109000002` and PC → `1115200001` per company, creates the
dedicated `PCPAY` payment journal (and company 2's missing `CSH` cash journal,
**before** PCPAY so the cash lookup cannot pick PCPAY up), seeds the analytic
plans and params, and refuses to commit if Bank-Out and Payment resolve to the
same journal.
