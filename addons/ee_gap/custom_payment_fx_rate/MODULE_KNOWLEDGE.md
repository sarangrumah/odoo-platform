---
status: draft
generated_at: 2026-08-26T00:00:00Z
generator: claude-code-handwritten
module: custom_payment_fx_rate
manifest_version: 19.0.1.1.0
---

# custom_payment_fx_rate

## Purpose
Gives a payment the exchange-rate field a bill already has. Odoo 19 ships `account.move.invoice_currency_rate` (stored, editable, with a "reset to the rate of the day" button in the bill header) but nothing equivalent on `account.payment`: a payment's journal entry is always valued from `res.currency.rate` at the payment date. Treasury needs the opposite — the rate on the bank advice is the rate that must hit the books.

## Business Flow
- **Payment in a foreign currency.** The payment form gains **Exchange Rate** under *Amount*, defaulted to the rate of the payment date, editable while the payment is a draft. The liquidity and counterpart lines of the generated entry are valued at that rate.
- **Company-currency payment settling a foreign document** (an IDR bank account paying a USD bill). The *Register Payment* wizard shows the same field; typing the rate re-proposes the amount (`100 USD × 16,200 = 1,620,000 IDR`) instead of making the user back-compute it. The created payment is in company currency, so the rate is *not* copied onto it — it had nothing left to value.
- Either way the difference against the rate carried by the bill lands on the exchange-difference account through the ordinary reconciliation, i.e. as a **realised** FX gain/loss. Nothing is re-valued silently.

## Key Models
- `res.currency` (`_inherit`) — `_get_conversion_rate` honours a `manual_fx_rate` context payload. This is the single seam: every amount Odoo derives from a currency passes through it, so the wizard's proposed amount, the journal entry, write-offs, withholding and early-payment-discount branches all follow without any balance being recomputed by hand.
- `account.payment` (`_inherit`) — hosts the stored rate and wraps `_prepare_move_lines_per_type` with the context.
- `account.payment.register` (`_inherit`) — hosts the wizard rate, wraps `_convert_to_wizard_currency` (used by every amount branch of `_get_total_amounts_to_pay`) and injects the rate into the payment vals.

## Important Fields
- `manual_currency_rate` (both models) — **company-currency units per one unit of the foreign currency**, i.e. the direction a user quotes ("1 USD = 16,200 IDR"). This is the *inverse* of the native `res.currency.rate` and of `account.move.invoice_currency_rate`, which are stored company → foreign. Compute + `store` + `readonly=False`, so it defaults to the rate of the day and survives an explicit edit. Deliberately *not* `precompute`: the compute reads non-precomputed fields, which Odoo warns about at registry load.
- `fx_foreign_currency_id` / `fx_show_rate` — on the payment, the payment currency when it differs from the company currency; on the wizard, that or else `source_currency_id`, so the field also appears when only the documents are foreign.
- `fx_expected_rate` — the rate of the day, kept alongside so a UI can flag a manual override.
- `fx_rate_hint` — the "per 1 USD" caption rendered next to the input. The currency itself comes from the widget, not the caption.

## Display
The input uses `widget="monetary"` with `options="{'currency_field': 'company_currency_id'}"`, so the rate reads as money in the company currency — `Rp 20.000,00`, thousands separated, instead of the bare `20000.000000` a float widget prints. The payment form has to carry an invisible `company_currency_id` for the widget; the wizard's core arch already declares one.

Consequence to know: the monetary widget formats to the *currency's* decimal places (2 for IDR), while the field stores 6. A rate smaller than the currency's rounding therefore displays as `0,00` — only reachable when the company currency is the stronger one (an IDR-based book never hits it, a USD-based book quoting IDR would). Pass `'field_digits': True` in the widget options if such a tenant ever appears.

## Gotchas
- The context payload is `{'currency_id': <id>, 'rate': <company units per foreign unit>}`. `_get_conversion_rate` only answers it for the pair `foreign ↔ company currency`; any other pair falls through to core, so a cross-currency conversion is never distorted.
- **A currency read off a journal item carries that item's context, not yours.** `_convert_to_wizard_currency` totals residuals per `line.currency_id`, so wrapping only the wizard in the context left the conversion using the rate of the day — silently: the proposed amount simply did not move. The override re-reads the installment lines under the context as well. Any future seam that converts through a record other than the payment/wizard needs the same treatment.
- `_fx_rate_of_the_day()` calls `_get_conversion_rate` under `manual_fx_rate=False`, otherwise computing the default would read back the manual rate.
- `_compute_amount_company_currency_signed` is re-declared with the full native `@api.depends` list plus `manual_currency_rate`: overriding a compute replaces its depends, so dropping the native ones would freeze the field.
- The wizard recomputes `amount` from `manual_currency_rate` through an `@api.onchange`, and skips it when `custom_user_amount` is set — a hand-typed amount beats the rate, same rule as core.
- Do not install alongside a module that also overrides `res.currency._get_conversion_rate` with a different context key without checking the order; the override chain is cooperative but the payloads are not.

## Tests
`tests/test_payment_fx_rate.py` — defaults, the untouched-rate baseline, the manual rate reaching the entry (and the entry staying balanced), the positive-rate constraint, the wizard's company-currency amount, the rate riding onto a foreign payment, and the no-op on a company-currency bill. The fixture currency of `AccountTestInvoicingCommon` is 2 foreign per 1 company unit from 2017, so the rate of the day in this module's direction is `0.5`.
