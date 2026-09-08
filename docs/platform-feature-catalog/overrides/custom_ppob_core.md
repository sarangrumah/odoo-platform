---
status: override
module: custom_ppob_core
source: manifest + models/*.py
---

# custom_ppob_core

## Purpose
Foundation of the **PPOB (Payment Point Online Bank)** vertical — Erajaya's
value-added services business: pulsa, data packages, electricity tokens and bill
payment sold through a network of *mitra* (B2B resellers) on a prepaid model.
Ported from the ERA PPOB R&D suite and rewired onto the platform's own
accounting and tax modules rather than its original standalone ones.

## Business Flow
- **Partner extensions** mark a `res.partner` as mitra or provider, carry a
  per-partner transaction cap, and hold an NPWP flag — the flag drives the PPh
  withholding rate applied to that partner's commission.
- **Product classification** (`custom.ppob.product.class`) is the routing key:
  it decides which wallet a transaction draws from and which VAT mode applies —
  margin, DPP nilai lain, gross, or exempt — per PMK-63/2022 for pulsa and
  voucher distributors.
- **Product catalogue** holds each sellable item with its denomination, default
  cost price, an inquiry-required flag for postpaid bills, and GL account
  overrides where a product must not use its class defaults.
- **Pricing tiers** set per-mitra selling prices per product, so the same
  denomination sells at different prices to different resellers.
- **Chart-of-account scaffolding** is created idempotently by a post-init hook
  that searches by code before creating. It slots beside a tenant's existing
  `l10n_id` or PSAK chart instead of duplicating accounts — which is what lets
  the vertical be installed onto a database that already has a chart.
- Sequences are created for transactions, wallet moves, bucket moves, VA topups
  and commission accruals; security groups for user, operations, manager and API
  integration.

## Key Models
- `custom.ppob.product.class` — the classification that drives wallet routing and
  VAT mode.
- `custom.ppob.product` — the sellable catalogue entry.
- `custom.ppob.price.tier` + `custom.ppob.price.tier.line` — per-mitra pricing.
- `custom.ppob.account.mapping` — role-addressed GL accounts, resolved by code so
  the vertical adapts to the tenant's chart.
- `res.partner` (inherited) — mitra/provider flags, transaction cap, NPWP flag.

## Important Fields
- `custom.ppob.product.class.vat_mode` — margin / other-valuation / gross /
  exempt. This single field decides how PPN is computed for every transaction in
  the class; getting it wrong misstates output tax across the whole vertical.
- `res.partner` NPWP flag — selects the PPh 23 rate on commission.
- `custom.ppob.account.mapping` — resolved by account *code*, not by ID, which is
  why the vertical can be installed on charts it did not create.
