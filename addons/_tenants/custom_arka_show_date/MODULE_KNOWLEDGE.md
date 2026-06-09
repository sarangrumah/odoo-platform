---
status: draft
generated_at: 2026-06-09T00:00:00Z
generator: hand-authored
module: custom_arka_show_date
manifest_version: 19.0.1.0.0
---

# custom_arka_show_date

## Purpose
Adds a **Show Date** to the sale → invoice flow for opt-in companies (PT ARKA)
and anchors customer-invoice payment-term due dates to the show date instead of
the invoice date. Gated by a `res.company` boolean flag so it is safe on a
multi-company tenant DB (e.g. AIM + ARKA): only the flagged company is affected.

## Business Flow
1. An operator ticks `res.company.x_custom_show_date_enabled` on the PT ARKA
   company (Settings → Companies → PT ARKA → "Show Date" page).
2. On a quotation, `x_custom_show_date` becomes required — but only when the
   order's company has the flag on (enforced server-side at confirm).
3. On confirmation the date stays on the Sales Order (`copy=True`).
4. `sale.order._prepare_invoice()` copies `x_custom_show_date` onto the customer
   invoice (`account.move`, `out_invoice`).
5. `account.move._compute_needed_terms` is overridden: for an `out_invoice` of a
   flagged company with a show date set, it re-runs the core compute on the move
   with context `arka_show_date_ref=<show_date>`.
6. `account.payment.term._compute_terms` reads that context key and substitutes
   it for `date_ref`, so every `date_maturity` and the early-payment
   `discount_date` are anchored to the show date. Non-flagged companies are
   untouched (pure pass-through).

## Key Models
- `res.company` (inherited) — `x_custom_show_date_enabled` (Boolean gate flag).
- `sale.order` (inherited) — `x_custom_show_date` (Date),
  `x_custom_show_date_required` (computed view-driver). Overrides
  `_confirmation_error_message`, `_prepare_invoice`.
- `account.move` (inherited) — `x_custom_show_date` (Date). Overrides
  `_compute_needed_terms`.
- `account.payment.term` (inherited) — overrides `_compute_terms`.

## Important Fields
- `res.company.x_custom_show_date_enabled` (Boolean, default False) — gate.
- `sale.order.x_custom_show_date` (Date, copy=True, tracking=True).
- `sale.order.x_custom_show_date_required` (Boolean, computed, non-stored) —
  related to `company_id.x_custom_show_date_enabled`; drives view
  required/invisible attrs.
- `account.move.x_custom_show_date` (Date, copy=False).

## Public / Overridden Methods
- `sale.order._confirmation_error_message()` — blocks confirm when the flag is
  on and no show date is set (does not block drafts).
- `sale.order._prepare_invoice()` — adds `x_custom_show_date` to invoice vals.
- `account.move._compute_needed_terms()` — re-declares the core `@api.depends`
  (`invoice_payment_term_id`, `invoice_date`, `currency_id`,
  `amount_total_in_currency_signed`, `invoice_date_due`) plus `x_custom_show_date`
  and `company_id.x_custom_show_date_enabled`; injects the anchor context.
- `account.payment.term._compute_terms(date_ref, *args, **kwargs)` — consumes
  the `arka_show_date_ref` context key.

## Gating & Scope
ARKA-only via the `res.company` flag (NOT name, NOT install). Customer invoices
only (`out_invoice`); vendor bills unaffected. Safe on multi-company / multi-
tenant DBs.

## Tests
`tests/test_show_date.py` (`AccountTestInvoicingCommon`): propagation SO→invoice,
required-only-when-flag-on, due date anchored to show date (show+30, not
invoice+30), and flag-off falls back to invoice-date anchoring.
