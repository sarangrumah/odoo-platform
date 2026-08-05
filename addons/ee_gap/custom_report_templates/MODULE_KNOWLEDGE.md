---
status: draft
generated_at: 2026-08-05T00:00:00Z
generator: hand-authored
module: custom_report_templates
manifest_version: 19.0.0.6.0
---

# custom_report_templates

## Purpose
Re-styles the three core business documents — Customer Invoice, Sales
Quotation/Order and Purchase Order — plus a Journal Voucher, to a clean
Wave/Excel-style layout. The layout is shared by every tenant; branding and the
handful of per-tenant differences are read from `res.company`, so no tenant
needs a code fork.

## How it takes over the core reports
It does **not** inherit `account.report_invoice_document`. It defines its own
standalone templates and re-points the native print actions in
`reports/report_actions.xml` (`account.account_invoices`,
`account.account_invoices_without_payment` → `report_name =
custom_report_templates.report_invoice`, and the equivalents for sale/purchase).

Each wrapper (`report_invoice`, …) is deliberately self-contained: plain
`<html><body><main>` instead of `web.html_container`, because the core wrapper
pulls assets over the `report.url` callback, which intermittently stalls
wkhtmltopdf on this platform. `_prepare_html` keeps only the children of
`<main>`, so `<meta charset>` and `<style>` live **inside** `<main>` — moving
them out makes wkhtmltopdf fall back to latin-1 and print mojibake ("Â¥").

## Layout rules (wkhtmltopdf 0.12.6.1 / Qt-WebKit)
Documented at the top of `reports/report_common_templates.xml` and binding on
every change:
- **Never** use the Bootstrap grid (`row`/`col-*`). Flexbox collapses to stacked
  full-width blocks. Use `<table>` with explicit `%` widths.
- Style everything **inline**. The Bootstrap stylesheet arrives over the same
  flaky external callback, so utility classes cannot be relied on.

## Shared partials (`reports/report_common_templates.xml`)
Callers set context variables before `t-call`; QWeb shares the caller scope.
Conventional names: `o` (record), `company`, `accent`, `currency`.

- `id_date` — Indonesian long date ("9 Juni 2026") built from a month map,
  because `format_date` / `context_timestamp` are not exposed in this QWeb
  sandbox and the `id_ID` locale is not active.
- `money` — locale-correct amount with a normal space instead of the monetary
  widget's NBSP (which prints as a stray "Â"). Never put a literal `%` in a QWeb
  expression — the compiler %-formats expression strings.
- `brand_header` — logo + address (left), title + caller-supplied meta rows
  (right, injected via `<t t-out="0"/>`).
- `party_band` — accent band + party address (BILL TO / FOR).
- `items_table` — caller sets `lines` and `qty_field`; all three line models use
  the unified `tax_ids` field in Odoo 19.
- `bank_block` — "BANK TRANSFER TO" band (see below).
- `comments_box` — OTHER COMMENTS box with a body slot; `white-space: pre-line`
  so `\n` in company text becomes line breaks.
- `totals_block` — subtotal, one row per tax group from `o.tax_totals`, TOTAL,
  optional BALANCE DUE.
- `signature_block` — caller sets `signer` and `doc_noun`; optional customer
  signature column when `show_customer_sig` is set (quotations only).

## Bank account on the invoice
Two mutually exclusive renderings, chosen by
`res.company.report_show_bank_block`:

- **Flag off (default, historical behaviour)** — the bank lines print inside the
  OTHER COMMENTS box: `o.partner_bank_id` when the invoice nominates an account,
  otherwise the free-text `res.company.report_bank_details`.
- **Flag on** — `bank_block` prints a dedicated accent band under the item
  table: `o.partner_bank_id` if set, otherwise every `res.partner.bank` owned by
  `company.partner_id` whose `company_id` matches (or is empty), each as bank
  name / `A/C: <acc_number>` / `a.n. <acc_holder_name or company.name>`.
  `report_bank_details` is appended below as free text (NPWP etc.). The
  OTHER COMMENTS box drops its bank lines so the number is not printed twice;
  `o.narration` stays there either way.

Because the band falls back to the company's own bank accounts, Finance only has
to fill Settings → Companies → Bank Accounts — no report change per tenant.

## Signature line
`report_invoice.xml` passes
`company.report_invoice_signer_label or o.invoice_user_id.name` as `signer`.
Companies that sign as a department (e.g. "Finance") set the label; everyone
else keeps printing the salesperson. Sale and purchase reports are unaffected.

## Key Models
- `res.company` (inherited, `models/res_company.py`) — report configuration
  only; no behaviour, no overrides.

## Important Fields (all on `res.company`)
- `report_bank_details` (Text) — bank / NPWP free text. Printed in the
  OTHER COMMENTS box, or under the bank band when that band is on.
- `report_show_bank_block` (Boolean, default False) — print the dedicated
  BANK TRANSFER TO band on customer invoices.
- `report_invoice_signer_label` (Char) — printed under the invoice signature
  line instead of the salesperson; empty = salesperson.
- `report_show_product_name` (Boolean, default False) — print the product name
  as a bold first line above every document line, for companies whose users
  overwrite the line description with free text.
- `report_footer_note` (Char, default "Thank You For Your Business").

All five are exposed on Settings → Companies → **Report Templates** tab
(`views/res_company_views.xml`). The accent colour comes from
`brand_accent_color` (Home Console tab, `custom_home_console`).

## Gating & Scope
Per-company fields, not per-tenant code. Every new flag must default to the
pre-existing rendering so tenants that do not opt in keep their current PDFs.
Currently installed on the arkaaim DBs only (`prd_arkaaim`, `trn_arkaaim`,
`trn_arkaaim_begbal`); adding a field still requires
`-u custom_report_templates` on each of them or the Settings view errors.

## Related
- `scripts/tenants/arkaaim/setup_invoice_bank.py` — idempotent odoo-shell script
  that creates the bank accounts, fills `report_bank_details`, and sets
  `report_show_product_name` / `report_show_bank_block` /
  `report_invoice_signer_label`. `COMMIT` knob, preview by default.
- `custom_studio_lite` — remains available for ad-hoc header/footer XPath tweaks
  on top of this baseline.
- `custom_arka_show_date` — rewrites down-payment line names upstream precisely
  so this shared addon does not need a tenant fork.

## Tests
None. Verified by rendering
`custom_report_templates.report_invoice_document` for a real invoice in an
`odoo shell` and inspecting the HTML, then printing the PDF.
