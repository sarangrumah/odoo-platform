---
status: draft
generated_at: 2026-08-05T00:00:00Z
generator: claude-code-handwritten
module: custom_coretax_export
manifest_version: 19.0.1.6.1
---

# custom_coretax_export

## Purpose
Emits the XLSX workbooks DJP's Coretax accepts as **import** files: e-Faktur Keluaran
(FK/OF), Retur Masukan, Bupot Unifikasi, Bupot PPh 21, and Bupot Non-Resident. Unlike
`custom_coretax`'s XML wizard — whose envelope is a placeholder schema never aligned to a
published XSD — every layout here is transcribed column-for-column from the official DJP
template workbooks, including their typos (`Nomor Setifikat Insentif`) and their
per-template casing (`PPH23` in Unifikasi vs `PPh26` in Non-Resident).

## Business Flow
Two shapes, depending on the layout.

**e-Faktur Keluaran (FK/OF)** — four entry points, one row builder:
1. **Invoice form** — `Export e-Faktur (FK)` button on a posted customer invoice.
2. **Invoice list** — select any number of invoices, then *Actions ▸ Export e-Faktur
   Keluaran (FK/OF)*; one workbook holds the whole selection in date order.
3. **Reporting ▸ Export e-Faktur Keluaran (FK)** — date range plus optional customer and
   sales-journal filters, with a live count before committing.
4. **Reporting ▸ Export File Import Coretax** — the whole-masa-pajak wizard.

All four validate the selection, build FK/OF rows, render with xlsxwriter, and return the
file. Entry points 1–3 hand back an `ir.actions.act_url` pointing at an `ir.attachment`;
entry point 4 writes to its own binary field and re-opens its form.

**Bupot / Retur / Tax List** — pick a template plus masa/tahun in the masa-pajak wizard,
which dispatches through `_BUILDERS` to the matching `_rows_*` builder.

## Key Models
- `custom.coretax.fk.builder` — **AbstractModel.** Owns the FK/OF column layout and every
  helper the templates share (`_fmt_date`, `_digits`, `_partner_address`, `_line_vat`,
  `_item_jenis`, `_render`). Both wizards pull it in via `_inherit`, so the helpers stay on
  `self` where the other `_rows_*` builders expect them; `account.move` reaches it through
  `self.env[...]`. No table, so it needs no `ir.model.access` row.
- `custom.coretax.template.export.wizard` — **TransientModel.** The original masa-pajak
  wizard; owns `_rows_bppu` / `_rows_bp21` / `_rows_bpnr` / `_rows_retur` / `_rows_taxlist`
  and the `_pemotong()` signer logic. Its `_rows_fk` now just delegates to the builder.
- `custom.coretax.fk.export.wizard` — **TransientModel.** Date-range FK/OF export with
  optional partner/journal filters and a computed `preview_count`.
- `account.move` — extended with `action_coretax_fk_export()`, written multi-record so the
  form button and the list-view server action share one implementation.

## Important Fields
- **custom.coretax.template.export.wizard**
  - `template`: `Selection` — bppu / bp21 / bpnr / fk / retur / taxlist.
  - `masa_pajak`, `tahun_pajak`: the tax period; `_period_bounds()` turns them into dates.
  - `company_id`: the pemotong.
  - `file_data` / `file_name` / `line_count`: the rendered result, shown for download.
- **custom.coretax.fk.export.wizard**
  - `date_from` / `date_to`: required, default first/last day of the current month.
  - `partner_ids`, `journal_ids`: optional filters; empty means all.
  - `preview_count`: computed count of matching posted invoices.

## Public Methods
On `custom.coretax.fk.builder`:
- `_coretax_fk_check_moves(moves)` → `(moves_ordered, company)`; raises on empty, non-
  `out_invoice`, not posted, missing `invoice_date`, or more than one company.
- `_coretax_fk_rows(moves, company=None)` → `([FK_COLUMNS, OF_COLUMNS], data_rows)` for an
  arbitrary invoice recordset.
- `_coretax_fk_export(moves, filename=None)` → validate, build, render, attach, return an
  `act_url` download.
- `_coretax_fk_filename(moves, stem=...)` — one naming rule for every entry point.
- `_round_and_plug(raw_values, rounding)` → `(written_values, total)`.

## Gotchas
- **The money grid is whole rupiah, fixed by the DJP format — not `currency.rounding`.**
  Odoo ships IDR with a rounding of `0.01` and both production tenants keep it that way, so
  deriving the grid from the ledger would emit decimal cells Coretax does not accept. The
  constant is `FK_AMOUNT_ROUNDING`. The integer grid is also what makes the FK↔OF tie hold
  bit-exactly.
- **Two invariants are guaranteed on the values as literally written**, because that is what
  Coretax validates: `HARGA_TOTAL - DISKON == DPP` on every OF row, and the FK totals equal
  the sum of the OF column beneath them. Hence `_round_and_plug` rounds every line but the
  last one DOWN and lets the last absorb the residual — the client's reference workbook does
  the same (`1.246.666 + 1.246.666 + 1.246.668 = 3.740.000`).
- **`DISKON` is derived last, from the DPP actually written**, and the gross is rebuilt from
  `line.discount` rather than `price_unit * quantity` — the latter is wrong when a
  price-included tax is in play, since `price_unit` is then gross of PPN but `price_subtotal`
  is not.
- **`x_custom_dpp_factor` is `digits=(12, 6)`.** A factor entered as 11/12 stores as
  `0.916667`, so totals land a rupiah or two off figures computed from an exact 11/12. That
  is the tax master applied faithfully — do not "fix" it in the exporter, and do not assert
  absolute literals from the reference workbook in tests; assert the tie instead.
- **The pemotong guard is scoped per layout.** `NPWP Penandatangan` is a bupot column only,
  so FK/OF and Retur Masukan must not be blocked on it (`_SIGNER_TEMPLATES`,
  `_fk_pemotong()`). NPWP and NITKU stay mandatory everywhere.
- **Nothing is silently dropped.** A draft or cancelled invoice in the selection raises and
  names the record: a tax file that quietly omits an invoice is worse than one that refuses
  to render. (A move with no product lines is still skipped per-move, but an entirely empty
  result raises.)
- **`_render` deliberately does not use `custom.report.engine`.** The engine prefixes a
  title/company/period banner and formats numbers for humans; a DJP import file must start
  its header on row 1 and carry raw values.
- **A plain 11% tax is exported as 12% on a DPP Nilai Lain of 11/12, never as an 11% tariff.**
  Coretax knows only the statutory 12% rate; the 11%-effective rate is the PMK 131/2024 nilai-lain
  arrangement, which `l10n_id` books the short way as a bare 11% tax (its "12% (Non-Luxury Good)"
  is rated `amount=11.0`). So `_line_vat` translates: `TARIF_PPN` 12, `DPP_LAIN` 11/12 of DPP,
  `CHECK_DPP_LAIN` 'Y', and the FK gets `KD_JENIS_TRANSAKSI` 04. The rupiah is untouched —
  12% × 11/12 == 11% exactly — so the file still ties to the GL. A tax explicitly configured
  `x_custom_dpp_method = nilai_lain` keeps its own factor and rate and is not second-guessed.
- **`FG_UANG_MUKA` is derived, not hard-coded.** `_is_uang_muka()` reads the originating sale
  order line's `is_downpayment`, because core bills a down payment through a product-less "fake"
  line that nothing else distinguishes. Every billed line must be one: the settlement faktur
  carries the deducted down payment *alongside* the goods, and flagging it would tell Coretax two
  down payments were issued. The companion columns (`NOMOR_FAKTUR_UM_SEBELUMNYA`, `UANG_MUKA_*`)
  stay empty — they want the *nomor faktur pajak* Coretax assigned to the earlier faktur, which
  this database does not hold.
- **Only `out_invoice` is exported.** Credit notes are not FK records — they belong to Faktur
  Pengganti or Retur Masukan, which have their own paths.
- **"Tidak ada faktur ... yang cocok" is almost always the company, not the period.** Both
  wizards export one NPWP at a time and default `company_id` to the active company, so a
  group user sitting on the holding company sees an empty July while the invoices sit in a
  sibling company. `_coretax_fk_empty_hints()` (builder mixin) reruns the search with one
  filter dropped at a time — other companies, unposted invoices, credit notes, the
  partner/journal filters — and both the wizard banner (`empty_reason`) and the `UserError`
  quote the result. Add a probe there, not in the wizards, so all entry points inherit it.
- **`REFERENSI` on an FK row is `move.name`, never `move.ref`.** On a customer invoice
  `ref` holds the source order / customer reference — in the Levi's flows, the sales-order
  number — so the old `move.ref or move.name` shipped the SO and the invoice number never
  appeared in the column the tax team reconciles the upload against. The bupot layouts keep
  `move.ref` on purpose: their reference document is a vendor bill, where `ref` really is
  the counterparty's invoice number.
- **`ir.actions.server` uses `group_ids`, not `groups_id`,** on Odoo 19. In XML data the
  rename fails as a bare `ParseError` that names no field.

## Integration Points
- `custom_tax_id` supplies the identity fields this module reads: `res.company`
  (`x_custom_nitku_suffix`, `x_custom_npwp_penandatangan`, `x_custom_coretax_user_id`,
  `_check_coretax_pemotong()`), `res.partner` (`x_custom_npwp`, `x_custom_nitku`,
  `x_custom_tin`, `_custom_coretax_nitku()`), `account.tax` (`x_custom_dpp_method`,
  `x_custom_dpp_factor`, `_dpp_adjust()`), and `uom.uom.x_custom_coretax_code` with its
  `CORETAX_UOM_FALLBACK` of `UM.0018`.
- `custom_coretax` supplies `x_custom_nsfp` on `account.move`, which `_rows_retur` needs to
  point a retur at the faktur it reverses.
- `sale` is optional: `_item_jenis` falls back to the originating order's products only when
  `sale_line_ids` is present.

## Out of Scope
- PPnBM: the columns are emitted as literal `0`.
- Foreign-currency invoices: amounts are written in the invoice currency without conversion
  to IDR.
- POS orders: retail sales are not invoices and are not exported.
