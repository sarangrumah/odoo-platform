# Custom Accounting Full

Multi-company accounting depth for Odoo CE. Covers what an Indonesian
SMB-mid group needs to operate with ≥2 legal entities under one
ownership: Indonesian COA, intercompany mirroring, consolidation
reporting, and a branch (kantor cabang) analytic dimension.

## Modules in Scope

### 1. Indonesian Chart of Accounts (PSAK-aligned)

- `account.chart.template` "Indonesia (PSAK) — Custom Platform"
- ~70 account templates covering Aset / Kewajiban / Ekuitas /
  Pendapatan / HPP / Beban / Pajak (1xxxx – 8xxxx)
- Tax templates: PPN 11% (and 12% placeholder), PPh 23 2% / 4%,
  PPh 4(2) 10%, PPh 26 20%
- 4 fiscal positions seeded for common scenarios (PKP, non-PKP,
  no-NPWP, foreign vendor)

### 2. Intercompany Automation

- `account.intercompany.rule` — declares (company_from, company_to,
  direction). Per-pair, per-direction unique.
- `account.intercompany.account.mapping` — explicit account
  translation between sister companies' charts.
- `account.move._post` override — on posting outbound invoice / bill,
  auto-creates the mirror draft in the sister company.
- Idempotent: a posted move tracks its mirror via
  `x_custom_ic_mirror_id`; re-posting won't duplicate.
- Optional `auto_validate` to skip the draft step on the mirror.

**Lookup heuristic**: the receiving company is the one whose
`res.company.partner_id` equals the invoice's commercial partner.
This is the standard Odoo way of representing "Company B as a vendor
of Company A".

### 3. Consolidation Engine

- `account.consolidation.config` — declares a perimeter
  (parent + subsidiaries + elimination accounts + presentation currency
  + fiscal year).
- `build_trial_balance(date_from, date_to)` returns per-account rows
  pivoted by company column + an elimination column + a consolidated
  total.
- Wizard `account.consolidation.report.wizard` lets the user pick
  perimeter + period + report type (Trial Balance / P&L / Balance
  Sheet) and renders to QWeb PDF.

Elimination logic: for each `elimination_account_id`, sum the balance
across the perimeter; book the inverse as the elimination delta so the
consolidated total ends at zero (or the legitimate residual when the
intercompany pair didn't fully match).

### 4. Branch (Kantor Cabang) Dimension

- `account.analytic.account.x_custom_branch_code` — free-form code
- `x_custom_is_branch_root` — flag for the analytic account that
  represents the legal branch
- `x_custom_branch_root_id` — computed (recursive) — every descendant
  resolves to its branch root, enabling per-branch P&L queries
  without restructuring journals

## Security Groups

- `custom_accounting_full.group_consolidation_viewer` — run reports.
- `custom_accounting_full.group_consolidation_admin` — design
  perimeters + intercompany rules (inherits viewer).

## Audit Trail

Every consolidation report run and every intercompany mirror creation
writes to `pdp.audit_log` via `pdp.audited.mixin` (chained,
tamper-evident).

## Dependencies

- `custom_core`, `custom_pdp_core`, `custom_pdp_audit`
- Odoo: `account`, `analytic`

## Install

```bash
make install MODULE=custom_accounting_full DB=<tenant_db>
```

After install, in the Odoo Apps Settings → Accounting → Chart of
Accounts: pick "Indonesia (PSAK) — Custom Platform" and click "Install"
to load the COA into the active company.

## Roadmap (not in P2A)

- Cashflow indirect method (categorize each move's effect via account
  tags) — needs an additional tag taxonomy on accounts.
- Budget vs. actual reporting tied to analytic plans.
- Asset depreciation lifecycle (linear, degressive, disposal,
  re-evaluation) — large enough to warrant its own module.
- Customer follow-ups / dunning levels — separate workflow scope.

## Reference

- `docs/architecture.md` — accounting layer
- `docs/coretax.md` — Coretax integration (consumes the PPh / PPN
  templates seeded here)
