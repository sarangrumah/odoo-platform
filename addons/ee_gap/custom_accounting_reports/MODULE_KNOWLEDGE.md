---
status: draft
generated_at: 2026-07-02T07:43:22Z
generator: bootstrap-v1
module: custom_accounting_reports
manifest_version: 19.0.0.1.0
---

# custom_accounting_reports

## Purpose
This module provides a comprehensive suite of financial reports for the Custom Platform, including P&L (Profit and Loss), Balance Sheet, General Ledger, Trial Balance, Cash Flow Statement, Aging Reports, Partner Ledger, Tax Reports, Day/Cash/Bank Books, Journal Audit, and more. It is designed to offer production-grade reporting capabilities tailored to the needs of a multi-tenant Odoo 19 environment.

## Business Flow
1. **User Selection**: The user selects a report type from the menu (e.g., Trial Balance, General Ledger).
2. **Wizard Input**: A wizard appears where the user inputs filters such as date range, company, and account.
3. **Report Generation**: Based on the selected report and input filters, the module processes the data to generate the required financial statements.
4. **Export/View**: The generated report is either exported in a format like XLSX or displayed directly within Odoo.

## Key Models
- `custom.report.advance` — Uang Muka / Down Payment Ledger
- `custom.report.aged.payable` — Aged Payable Report
- `custom.report.aged.receivable` — Aged Receivable Report
- `custom.report.balance.sheet` — Balance Sheet Report
- `custom.report.cash.flow` — Cash Flow Statement
- `custom.report.day.book` — Day Book / Cash Book / Bank Book
- `custom.report.journal.audit` — Journal Audit

## Important Fields
- **CustomReportAdvance**
  - `account_ids`: Selection of accounts related to Uang Muka.
  - `date_from`, `date_to`: Date range for the report.

- **CustomReportAgedReceivable, CustomReportAgedPayable**
  - `partner_ids`: List of partners involved in the aging process.
  - `aging_detail`: Boolean flag to switch between summary and detail layouts.

- **CustomReportBalanceSheet**
  - `account_type`: Selection of account types (e.g., asset_receivable, liability_payable).

- **CustomReportCashFlow**
  - `account_type`: Selection of account types for categorizing cash flows.

## Public Methods
- **CustomReportAdvance**
  - `action_activate()`: Activates the report and generates initial data.
  
- **CustomReportAgedReceivable, CustomReportAgedPayable**
  - `build_lines(filters)`: Builds the lines based on input filters.

- **CustomReportBalanceSheet**
  - `_get_account_balances(filters)`: Retrieves account balances for the given period.

- **CustomReportCashFlow**
  - `_bucket(label, code, type_codes, balances, sign=-1)`: Computes a bucket of accounts for cash flow categorization.

## Integration Points
- **Depends on**: `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account`
- **Inherits from**: `account.move` (adds `rental_line_ids`)
- **Extended by**: `custom_rental_prorata`, `custom_drone_rental`
- **External calls**: None
- **Cross-vertical**: Deployed in arkaim, jds, ppob

## Gotchas
- The module relies heavily on the `account.move` model for most of its operations.
- The `CustomReportAdvance` model auto-detects accounts based on their names, which might not cover all edge cases.

## Out of Scope
- This module does not handle real-time reporting or live data updates.
- It focuses solely on static reports and does not integrate with external tax systems directly.
