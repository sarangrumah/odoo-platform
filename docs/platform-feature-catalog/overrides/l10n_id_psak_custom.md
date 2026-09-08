---
status: override
module: l10n_id_psak_custom
source: manifest + models/template_id_psak.py
---

# l10n_id_psak_custom

## Purpose
An alternative **5-digit Indonesian chart of accounts aligned to the PSAK
numbering convention**, for tenants that are not on the Erajaya group chart. It
sits between the upstream 4-digit `l10n_id` template and the 10-digit
`l10n_erajaya` one, and is what `trn_arkaaim` runs.

The module is `auto_install: True` and is a hard dependency of
`custom_accounting_full`, so in practice it is present on every database that
has the accounting layer — even the ones that then load a different chart.
Having it installed does not select it; a company still has to pick `id_psak`.

## Business Flow
- Odoo's `ir.module.module._compute_account_templates` discovers the
  `@template("id_psak")` methods and lists **PSAK** among the available charts.
- Selecting it creates 53 accounts under 12 hierarchical account groups on the
  1xxxx–8xxxx spine: 1xxxx Aset, 2xxxx Kewajiban, 3xxxx Ekuitas, 4xxxx
  Pendapatan, 5xxxx Harga Pokok Penjualan, 6xxxx Beban Operasional, 7xxxx
  Pendapatan/Beban Lain, 8xxxx Pajak Penghasilan.
- Two PPN 11% taxes (PMK 58/2022) are created — Keluaran and Masukan — with
  explicit repartition lines pointing at `21400` (PPN liability) and `11500`
  (PPN asset), rather than relying on defaults.
- Six journals are created with Bahasa labels: Faktur Penjualan, Tagihan
  Pembelian, Kas, Bank, Jurnal Umum, Selisih Kurs.
- Two fiscal positions close it out: **Ekspor** (drops PPN) and **Pelanggan
  Bebas Pajak**.
- PPh withholding taxes (21/23/26) are deliberately absent. They belong to
  `custom_pph_witholding` and `custom_tax_id`, which feed Bupot lines into
  Coretax; duplicating them here would double-book the withholding.

## Key Models
- `account.chart.template` (inherited) — hosts the `@template("id_psak")`
  definitions. No own model.

## Important Fields
- Chart template code `id_psak` — the selector value; `custom_accounting_full`
  and several tenant scripts branch on it (see the `WHT_COA_ALIAS` handling in
  the withholding loader).
- PPN repartition targets `21400` / `11500` — hard-coded in the template, so a
  tenant that renumbers these accounts must re-point the taxes by hand.
