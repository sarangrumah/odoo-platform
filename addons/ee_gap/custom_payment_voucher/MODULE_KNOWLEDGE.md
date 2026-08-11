# custom_payment_voucher — module knowledge

## What it is
Payment Voucher (outbound) and Payment Receipt (inbound) PDFs on
`account.payment`, plus three fields: `pv_note`, `pv_remark` and
`pv_override_outstanding_account_id`.

## Gotchas

**`<style>` and `<meta charset>` live inside `<main>`, not `<head>`.**
`ir_actions_report._prepare_html` keeps only the *children of `<main>`* and
writes them to a bare HTML file for wkhtmltopdf — no `<html>`/`<head>` wrapper
survives. A style block in `<head>` is dropped silently: the report still
prints, just unstyled, and the missing charset turns every Indonesian character
into latin-1 mojibake. The `pv_page_style` template exists to be called as the
first child of `<main>`. Do not "tidy" it back up into the head.

**No `web.html_container`.** These templates are self-contained on purpose: the
standard container pulls in the `report.url` asset callback, which makes
wkhtmltopdf hang for tens of seconds per document. The trade-off is that
`<main>` is mandatory — a template without it raises IndexError on print.

**Money goes through `pv_money`, never the monetary widget.** Odoo's widget
emits U+00A0 as the thousands separator and wkhtmltopdf renders it as a stray
`Â`. `pv_money` also forces Indonesian separators regardless of the user locale.

**`_compute_outstanding_account_id` re-declares `@api.depends`.** Re-declaring
*replaces* the inherited dependency set, so `payment_method_line_id` is relisted
alongside `pv_override_outstanding_account_id`. Drop it and the account stops
following the journal.

**Do not install alongside `custom_levis_localization`.** That module carries
its own copy of these reports (with Operating-Unit stamping). Both would appear
in the Print menu. The `pv_` prefix keeps the *fields* from clashing, nothing
more.

## Related
- `addons/_tenants/custom_levis_localization/reports/payment_*` — the original.
- `scripts/tenants/arkaaim/setup_payment_journals.py` — the journal config that
  decides which account the voucher's liquidity line shows.
