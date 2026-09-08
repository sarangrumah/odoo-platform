---
status: override
module: l10n_erajaya
source: manifest + models/template_erajaya.py + data/template/*.csv
---

# l10n_erajaya

## Purpose
Registers **Erajaya's own 10-digit Indonesian chart of accounts** as a selectable
Odoo 19 chart template (template code `erajaya`), so a new company in the group
starts on the group standard instead of the upstream 4-digit `l10n_id` chart or
the 5-digit `l10n_id_psak_custom` one. Despite the brand in its name this is a
**shared** module: both live Erajaya tenants run it — ARKA-AIM (`prd_arkaaim`)
and Levi's / Era Busana Retailindo (`prd_levis_begbal`).

Bulk content ships as CSV rather than XML records: **534 accounts, 29 account
groups, 78 taxes and 7 tax groups**. The CSVs were produced once by
`tools/gen_l10n_erajaya.py` from the 548-row client master CoA in
`imports/arka_aim_coa.csv` plus a live tax dump, with bank/cash and
brand-specific accounts filtered out so the template stays company-neutral.

## Business Flow
- An operator creates the company, then picks **Erajaya** in Settings →
  Accounting → Chart Template. Odoo discovers the template through the
  `@template("erajaya")` methods on `account.chart.template`, which is why the
  module must stay in the `Accounting/Localizations/Account Charts` category.
- Loading the template applies the root metadata: 10 code digits, country `id`,
  receivable `erajaya_1106000001`, payable `erajaya_2103100001`.
- Company defaults follow: anglo-saxon accounting on, bank prefix `1103`, cash
  prefix `1102`, transfer prefix `1101`, FX gain/loss accounts, and the default
  12% non-luxury sale and purchase taxes.
- The stock `sale` and `purchase` journals are renamed to **Penjualan** and
  **Pembelian** so the journal list reads in Bahasa Indonesia from day one.
- Fiscal positions (`erajaya_fpos_domestic` and siblings) are created last.
- Per-tenant deviations are *not* handled here. Levi's strips the accounts EBR
  does not use through `scripts/tenants/levis/30_fix_coa.py`; ARKA-AIM's
  development database seeds its own variant via `custom_arka_aim_seed`.

## Key Models
- `account.chart.template` (inherited) — carries the `@template("erajaya")`
  methods that expose the chart, its company defaults, journals and fiscal
  positions. The module declares no model of its own.

## Important Fields
- `code_digits` = `"10"` — the group standard. A tenant on a different digit
  count cannot share this template.
- `property_account_receivable_id` = `erajaya_1106000001` — Trade Receivables.
- `property_account_payable_id` = `erajaya_2103100001` — Trade Payables.
- `bank_account_code_prefix` / `cash_account_code_prefix` = `1103` / `1102` —
  every new bank or cash journal numbers itself from these.
