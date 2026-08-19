---
status: draft
generated_at: 2026-08-20T00:00:00Z
generator: claude-code-handwritten
module: custom_pos_tax_id
manifest_version: 19.0.0.1.0
---

# custom_pos_tax_id

## Purpose
Bridges Point of Sale and Indonesian tax identity so a retail sale can become an
e-Faktur when — and only when — the buyer asks for one.

Retail output VAT is reported **digunggung**: aggregated per masa, no buyer identity,
no per-transaction upload (`custom.report.ppn.digunggung`). A buyer who requests a
faktur pajak leaves that aggregate: the POS order is invoiced, which produces an
`out_invoice`, which `custom_coretax_export` already turns into an FK row. No parallel
FK-from-POS pipeline exists, and none is wanted — the two reports split on
`move_type`, so an invoiced order is dropped from the digunggung recap automatically.

## Business Flow
1. Cashier picks the customer in POS and fills in NPWP (or NIK) — the POS *Edit
   Partner* action opens `base.view_partner_form`, which `custom_tax_id` already
   extends, so no POS UI change was needed.
2. Cashier ticks *Invoice*. `pos.order._generate_pos_order_invoice()` refuses if the
   buyer has neither NPWP nor NIK.
3. The resulting `out_invoice` flows into the FK/OF export like any other invoice.

## Key Models
- `pos.order` — adds `_pos_tax_identity_missing()` and the guard on
  `_generate_pos_order_invoice()`; `x_custom_partner_npwp` is a related field shown on
  the back-office order form.
- `res.partner` — extends `_load_pos_data_fields` so the POS client can display the
  buyer's NPWP/NIK.

## Gotchas
- **The guard raises where it is still fixable, on purpose.** The FK layout has no
  blank-NPWP variant; without this the failure surfaces only when the tax team runs
  the masa export, days after the receipt was printed.
- **NIK is a valid alternative to NPWP** for an individual buyer, matching the
  NPWP/NIK fallback in `custom.report.faktur.pajak`.
- **Do not invoice ordinary walk-in sales to "clear" the guard.** An invoiced order
  leaves the digunggung recap; invoicing everything would demand an uploadable faktur
  per transaction, which is exactly what the PKP Pedagang Eceran regime avoids.

## Out of Scope
- Issuing the retail faktur (struk) itself; only the e-Faktur path is covered.
- POS UI work: partner editing rides the standard back-office form.
