# Custom Cash Advance & Petty Cash

Employee cash advances (uang muka karyawan) with a full Finance cycle on
Odoo 19 Community.

> Odoo has no cash-advance feature in **either** edition. The Expenses app only
> models "the employee already paid, reimburse them", so money always moves
> *after* the spend. This module supplies the other direction. The OCA
> reference module `hr_expense_advance_clearing` is not available on 19.0 —
> Odoo 19 removed `hr.expense.sheet`.

## Flow

0. **Type** (`petty.cash.type`) — Petty Cash Awal, Realisasi, Claim, Cash
   Advance, Petty Cash, Travel… Each type carries its own advance account,
   journals, sequence and ceilings, per company. The first three drive the
   store float described below.
1. **Request** (`petty.cash.request`) — an employee asks for cash for an
   Operating Unit, optionally itemised into detail lines.
2. **Approval** — routed through `custom_approval_engine`'s matrix; when no
   matrix matches, a Finance user approves directly.
3. **Disbursement (Bank Out)** — Finance disburses the approved amount:
   `Dr Uang Muka Petty Cash (employee) / Cr Bank`.
4. **Realization** (`petty.cash.realization`) —
   * *Third-party* lines → a vendor bill (`in_invoice`) carrying PPN (`tax_ids`)
     and PPh (`x_custom_withholding_category_id`, applied by `custom_tax_id`),
     then paid out of the advance through the Petty Cash payment journal
     (`Dr AP / Cr Uang Muka`). The supplier invoice attachment is mandatory.
   * *Expense* lines → `Dr Expense / Cr Uang Muka` in one entry.
5. **Return / Reimburse / Settle** — leftover cash is returned
   (`Dr Bank / Cr Uang Muka`) or a shortfall reimbursed
   (`Dr Uang Muka / Cr Bank`); when the advance nets to zero the request is
   settled and the advance lines are reconciled.
6. **Monitoring** — kanban/list dashboards plus three reports (PDF / XLSX /
   on-screen table via `custom_accounting_reports`): **Kartu Uang Muka** (the
   per-employee movement card with a running balance), the **Outstanding**
   ledger and an **Aging** report.
7. **Vouchers** — printable Bukti Pencairan, Bukti Pertanggungjawaban and
   Bukti Penyelesaian with signature blocks.

## Store petty cash float

Retail tenants run the module the other way round: instead of one advance per
employee, each **store (Operating Unit)** holds a revolving float.

| Type kind | Role | Bank-Out | Gated on |
|---|---|---|---|
| **Petty Cash Awal** (`pc_initial`) | grants the store's float | yes | the store's plafon (1.000.000 by default, set by Finance) |
| **Realisasi** (`pc_realization`) | one spend out of the float | no — the cash is already in the drawer | the store's available balance |
| **Claim** (`pc_claim`) | a spend the float cannot cover | yes | nothing — this is the escape hatch |

A Realisasi reserves its full amount **from draft**, so a store cannot queue
several drafts that each look affordable on their own. Once Finance approves it,
the employee records the realization against that same request; every rupiah
realized frees a rupiah of the reservation ("saldo pulih sesuai nilai yang
direalisasikan"). Whatever was never realized is handed back by **Close &
Release**, which books nothing — that cash never left the store.

`Cash Advance → Finance Review → Store Floats` shows plafon, granted, reserved
and available per store, next to the advance-account GL balance. The two differ
between a realization and its replenishment, by design.

The plafon lives in `Accounting → Settings → Petty Cash → Initial Petty Cash per
Store` and can be overridden store by store on the float itself.

## Finance review & dashboard

`Cash Advance → Finance Review`

* **Review Queue** — everything awaiting approval, with inline Approve / Send
  Back, and a batch wizard (Approve / Send back / Refuse) whose reason is posted
  to each request's chatter.
* **Store Floats** — outstanding per Operating Unit; exhausted stores in red.
* **Outstanding per Operating Unit** — pivot of requested / realized / reserved /
  outstanding, pre-grouped by store and status.

`Cash Advance → Dashboard` is the same data over **list, kanban, pivot and
graph**, with filters per type kind, overdue, reserving-float and this month,
and group-by store / employee / type / status / month. Export uses Odoo's
native list export (XLSX / CSV).

## Multi-currency

Every generated journal item carries `currency_id` and `amount_currency`, so an
advance in a foreign currency books its correct counter-value and settles
through the company's exchange-difference journal. `amount_outstanding` is in
the request's currency; `amount_outstanding_company` is the figure to aggregate.

## Limits

Optional ceilings, resolved **employee → job position → type**, plus a cap on
simultaneous open advances and a block on borrowing again while an advance is
past its realization deadline. Enforcement is per type: `off` (default), `warn`
(chatter note) or `block`. `Petty Cash / Limit Override` grants exceptions and
is deliberately assigned to nobody out of the box.

## Configuration

Accounts and journals resolve **request → type → company**, so the per-type
setup (Cash Advance → Configuration → Advance Types) is the normal place to
configure them. The company-level fields under Accounting → Settings remain as
a fallback for tenants configured before types existed.

| Setting | Purpose |
|---|---|
| Advance Account | Reconcilable "Uang Muka" account, debited per employee. |
| Bank-Out Journal | Funds disbursement / receives returns. |
| Payment Journal | Pays third-party bills out of the advance. **Must be dedicated** — posting a realization repoints this journal's outstanding accounts at the advance account. |
| Expense Journal | Miscellaneous journal for expense entries (falls back to the first `general` journal). |
| Realization Deadline (days) | Default deadline after disbursement; drives the overdue filter + reminder cron. |
| Operating Unit Analytic Plan | Which analytic plan the OU field offers. Defaults to "Operating Unit"; an unknown name widens rather than blocks. |
| Disburse via account.payment | Book disbursement as a bank-reconcilable payment instead of a direct entry. |

## Operating Unit

The `l10n_ou_analytic_id` field (analytic plan "Operating Unit") is stamped
onto every generated journal item's `analytic_distribution`; when the Levi's
localization is installed the native `l10n_ou_analytic_id` line field is set
too. Without the localization the module runs unchanged.

## Security

* **Petty Cash / User** — employees: own requests/realizations only.
* **Petty Cash / Finance** — review, approve, disburse, post, settle, reports.
* **Petty Cash / Limit Override** — may raise a request past its ceiling.
  Granted to nobody by default; it is meant to be a named exception.
