---
status: draft
generated_at: 2026-06-09T00:00:00Z
generator: hand-authored
module: custom_arka_show_date
manifest_version: 19.0.1.8.0
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

## Event Description Block (1.3+)
The order also captures `x_custom_event_name`, `x_custom_event_location` and
`x_custom_dp_note`. `sale.order._custom_event_description()` joins them with the
show date (`dd.mm.yy`) into one string, which `sale.order.line._compute_name()`
appends as a second line under every product line's description. It reaches the
customer invoice through the standard `_prepare_invoice_line`.

## Down-Payment Line Description (1.4+, event detail added in 1.5)
`sale.advance.payment.inv._prepare_down_payment_invoice_line_values()` replaces
core's "Down payment of 50.00%" with
`sale.order._custom_down_payment_description(marker)`:

    <product names>, <event block> (Uang Muka 50%)

Both the invoice PDF and the Faktur Pajak read this one stored `name` — the
coretax exporter uses `line.product_id.name or line.name`, and a DP line has no
product — so rewriting it fixes both printouts without touching the shared
`custom_report_templates` / `custom_coretax_export` addons.

Two constraints hold this shape:
- **Single line, always.** The string lands in one cell of the coretax import
  file, where an embedded newline is not safe. The event block is therefore
  taken once from the order, not from each product line's multi-line `name`.
- **`x_custom_dp_note` is excluded** here (`include_dp_note=False`), because the
  trailing marker already states the down payment; including it would print
  "DP 50% (Uang Muka 50%)". A fixed-amount DP gets `(Uang Muka)`, no percentage.

## Settlement Deduction Line (1.6+)
On the *pelunasan* invoice, core labels the down-payment deduction line
"Down Payment (ref: INV/… on 08/14/2026)" via
`sale.order.line._get_downpayment_description()`, and that one string is what the
order's "Down Payments" section, the settlement invoice PDF **and** the Faktur
Pajak of the settlement all show — the coretax exporter takes every
`display_type == 'product'` line, including this negative one. The override
reuses `_custom_down_payment_description()` and keeps the core reference as the
trailing marker built by `_custom_down_payment_marker()`:

    <product names>, <event block> (Uang Muka ref: INV/ARKA/2026/08/002 tgl 14/08/2026)

Draft and cancelled down payments mirror core's own states
(`(Uang Muka Draft dd/mm/YYYY)`, `(Uang Muka Dibatalkan)`). Section lines
("Down Payments") and non-flagged companies keep the core wording. Dates are
formatted `dd/mm/YYYY` explicitly, not through `format_date`, because the string
also reaches the coretax import file.

## Event on the Buying Leg (1.7+)
`purchase.order` captures the same `x_custom_show_date` / `x_custom_event_name`
/ `x_custom_event_location`, hands them to the vendor bill through
`_prepare_invoice()`, and — where `custom_intercompany_procurement` mirrors the
PO into the sister company — writes them onto the mirrored sales order by
overriding `_custom_create_ic_mirror_so()`. Before this the event reached the
selling company only as free text in the header note ("MERDEKA RUN - MONAS",
"OPERRATIONAL DRONE SHOW - DANONE BALI"), which is why AIM could not report on
it: in prd_arkaaim exactly 1 of 12 ARKA vendor bills and 0 of 11 AIM vendor
bills carried a show date, so the cost side of the per-Show P&L was empty.

## Purchase Order Raised From the Sale (1.7+)
`sale.order.action_custom_create_ic_purchase_order()` creates a **draft**
purchase order on the sister company named by the intercompany rule
(`account.intercompany.rule` with `mirror_purchase_order`, `company_from_id` =
this company), carrying the event, the show date and the ordered lines, and
links back through `purchase.order.x_custom_event_source_so_id`. Confirming that
draft then fires the existing PO → SO mirror, so one sale produces the whole
chain: **ARKA sale → ARKA purchase → AIM sale**, all naming one event.

Two deliberate choices:
- **Draft, not confirmed.** The sister company's price is not the customer's
  price, so a buyer reviews it. Line `price_unit` / `name` / taxes are left to
  the core computes (supplier info), NOT copied from the sale — copying would
  book AIM's cost at ARKA's margin.
- **A separate link field.** `custom_intercompany_procurement` already declares
  `purchase.order.x_custom_ic_source_so_id`, but its mirror guard returns early
  when that field is set (`_custom_run_ic_po_mirror`). Reusing it would silently
  stop the PO from mirroring into AIM — the opposite of the point. Hence
  `x_custom_event_source_so_id`.

## Sale Product vs Purchase Product (1.8+)
The client runs two catalogues for one show: the customer order carries the
*Jasa* service ARKA sells, the purchase order on AIM carries the matching *Sewa*
rental AIM invoices back.

    Jasa Drone Show 250 Unit   (sold)   ->   Sewa Drone Show 250 Unit   (bought)

`product.template.x_custom_ic_purchase_product_id` ("Purchased As", shown next
to Purchase-ok on the product form) records the pairing, and
`action_custom_create_ic_purchase_order()` swaps the product when it builds the
purchase line — carrying the substitute's own UoM, since the two sides need not
be counted the same way. Resolution is **one hop only** (`product.product.
_custom_ic_purchase_product()`): a chain would walk the buyer to a product
nobody chose and a cycle would hang. An unpaired product is still bought as
itself, so the field is optional everywhere.

Odoo has no native sale-to-purchase substitution — `product.supplierinfo` prices
a product from a vendor, it does not replace it — which is why this is a field
and not a configuration of something existing.

Side effect worth knowing: the *Sewa* products carry vendor pricing, so a paired
line arrives on the purchase order **with a price**, where an unpaired one
arrives at 0.

`scripts/tenants/arkaaim/map_sale_to_purchase_products.py` fills the field from
the names already in the DB, matching on the **unit count** rather than the
words — the client writes the rental side three ways ("Sewa Drone Show 1500
Unit", "Sewa Drone 1000 Unit", "Sewa Drone 500 Unit") and only the number is
stable. It refuses to guess: no number, no counterpart, or more than one
candidate is reported and left for a human. Existing pairings are never
overwritten.

## Analytic Account per Event (1.7+)
`custom.arka.event.mixin` (models/arka_event_mixin.py) is inherited by
`sale.order`, `purchase.order` and `account.move`. It concatenates the event,
its location and the show date into one label —
`Soekarno Cup - Stadion Gelora Bung Tomo Surabaya - 24.08.26` — and resolves it
to a single `account.analytic.account` in the **Event** plan
(`data/analytic_plan.xml`, xmlid `analytic_plan_arka_event`), created on first
use.

- Matching is on `account.analytic.account.x_custom_event_key`, a normalised
  (whitespace-collapsed, upper-cased) copy of the label with a UNIQUE
  constraint — NOT on `name`, which is a translatable jsonb column, and not on
  what the user typed, because they retype spacing and case.
- The account is created with **`company_id = False`** on purpose: a
  company-scoped account would split one show into ARKA-revenue and AIM-cost
  halves. Shared analytic accounts are the only cross-company key Odoo offers,
  and they are what makes a consolidated P&L per event possible.
- Confirmation stamps `{account_id: 100}` on lines that carry **no**
  distribution (`sale.order.action_confirm`, `purchase.order.button_confirm`);
  a "Tag Event" button does the same for a bill with no source document. A
  distribution an operator split by hand is never overwritten.
- Gated on `res.company.x_custom_event_tracking_enabled` — deliberately NOT on
  `x_custom_show_date_enabled`, which makes the show date required on sales
  orders and re-anchors due dates; enabling that on AIM would block every AIM
  order without a show. The event flag makes nothing required and moves no due
  date, so it is safe on both sister companies — which it must be.

## Profit & Loss per Event (1.7+)
`custom.report.profit.loss.event` (`profit_loss_event`) is the analytic reading
of the same statement: it inherits the *branch* variant untouched — which
already pivots per analytic account over `analytic_distribution` — and only
points `_branch_plan()` at the Event plan and renames the residual column to
**Unassigned**. Two "View/Export by Event" buttons are added to the shared P&L
wizard.

Against the older *per Show* variant: that one keys on
`account.move.x_custom_show_date`, so two shows on one night collapse into one
column and an untagged overhead has nowhere to go. Per Event separates them and
accepts anything an operator can tag. Both remain, and both are screen + XLSX
only. `profit_loss_event` is registered in `REPORT_MODEL_MAP` (models/__init__)
— no QWeb router branch, which is correct for a dynamic-column report.

## Key Models
- `custom.arka.event.mixin` (AbstractModel) — event label, analytic account
  resolution, distribution stamping. Carries no fields: the three event fields
  are declared per model because their attributes differ (the order tracks and
  copies them, the journal entry does not).
- `res.company` (inherited) — `x_custom_show_date_enabled`,
  `x_custom_event_tracking_enabled` (two independent gate flags).
- `purchase.order` (inherited + mixin) — event fields,
  `x_custom_event_source_so_id`. Overrides `_prepare_invoice`,
  `_custom_create_ic_mirror_so`, `button_confirm`.
- `account.analytic.account` (inherited) — `x_custom_event_key` + UNIQUE.
- `product.template` / `product.product` (inherited) —
  `x_custom_ic_purchase_product_id` + `_custom_ic_purchase_product()`.
- `custom.report.profit.loss.event` — P&L pivoted per event analytic account.
- `sale.order` (inherited) — `x_custom_show_date` (Date),
  `x_custom_show_date_required` (computed view-driver). Overrides
  `_confirmation_error_message`, `_prepare_invoice`.
- `account.move` (inherited) — `x_custom_show_date` (Date). Overrides
  `_compute_needed_terms`.
- `account.payment.term` (inherited) — overrides `_compute_terms`.
- `sale.order.line` (inherited) — overrides `_compute_name` (event block) and
  `_get_downpayment_description` (settlement deduction label).

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

## Configuration Needed Before Any of This Does Anything
1. Settings ▸ Companies ▸ "Show Date & Event": tick **Enable Event Tracking**
   on BOTH sister companies (ARKA and AIM). Show Date stays ARKA-only.
2. An active `account.intercompany.rule` with `mirror_purchase_order` and
   `company_from_id` = ARKA is what the "Buat PO ke Sister Company" button
   reads to know the vendor; prd_arkaaim already has exactly one.
Until step 1, the module behaves exactly as 1.6.0 did.

## Gating & Scope
ARKA-only via the `res.company` flag (NOT name, NOT install). Customer invoices
only (`out_invoice`); vendor bills unaffected. Safe on multi-company / multi-
tenant DBs.

## Tests
`tests/test_event_chain.py` (`AccountTestInvoicingCommon`, two companies + an
intercompany rule): event onto the vendor bill and the customer invoice; the
label concatenation and what it skips; one account per event, shared across
companies, resilient to retyped case/spacing, distinct per show date;
stamping on sale/purchase confirm; a hand-split distribution surviving a
confirm; the gate keeping everything inert; the "Tag Event" button touching
only `display_type == 'product'` lines; the PO raised from the sale (event,
lines, back-link, tagging, and that it does NOT inherit the customer price);
the mirrored AIM order carrying the event fields and landing on the same
analytic account; the per-Event P&L columns; and the sale→purchase product
pairing — swapped on the purchase order, quantities and event intact, one hop
only, unpaired products bought as themselves, no self-pairing.

`tests/test_show_date.py` (`AccountTestInvoicingCommon`): propagation SO→invoice,
required-only-when-flag-on, due date anchored to show date (show+30, not
invoice+30), and flag-off falls back to invoice-date anchoring.
