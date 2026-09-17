# -*- coding: utf-8 -*-
{
    "name": "Coretax Import File Export (DJP Templates)",
    "summary": "Emit DJP-conformant Coretax import workbooks: e-Faktur Keluaran (FK/OF), "
    "Retur Masukan, Bupot Unifikasi, Bupot PPh 21, Bupot Non-Resident",
    "description": """
Coretax Import File Export
==========================

Produces the XLSX workbooks DJP's Coretax accepts as *import* files. Unlike
``custom_coretax``'s XML wizard — whose envelope is a placeholder schema never
aligned to a published XSD — every layout here is transcribed column-for-column
from the official DJP template workbooks, including their typos (``Nomor
Setifikat Insentif``) and their per-template casing (``PPH23`` in Unifikasi vs
``PPh26`` in Non-Resident).

Why a standalone renderer
-------------------------
``custom.report.engine`` prefixes a title/company/period banner and formats
numbers for humans. A DJP import file must start its header on row 1 and carry
raw values, so these wizards drive ``xlsxwriter`` directly rather than
subclassing the report engine.

Templates covered
-----------------
- **e-Faktur Keluaran — Mitra Pajakku** (``Import FK`` sheet) — two-record
  layout: one ``FK`` row followed by its ``OF`` item rows, 35 + 16 columns.
- **e-Faktur Keluaran — Coretax** — two sheets, ``Faktur`` (18 columns) beside
  ``DetailFaktur`` (14).
- **Retur Masukan — Coretax** — two sheets, ``Retur`` (12) beside
  ``DetailRetur`` (15).
- **Retur Masukan — Mitra Pajakku** (``Import RM``) — one ``RM`` row per credit
  note followed by its ``OF`` rows, 24 + 23 columns.

Every column tuple is transcribed verbatim from the client's own templates in
``docs/projects/levis/tax-templates/``. These are import files read **by
position**, so a column added, dropped or reordered makes the upload fail in a
way correct arithmetic does not rescue; ``tests/test_template_shapes.py`` pins
the shapes.

Faktur Keluaran has two possible sources, chosen on the wizard:

- **Faktur penjualan** — one FK per ``out_invoice``, buyer identified. This is
  what a B2B seller exports.
- **Rekap digunggung** — one FK per trading day per store, for a PKP Pedagang
  Eceran whose sales never become invoices at all. Figures come from
  ``custom.report.ppn.digunggung`` rather than being re-derived, so the export
  and the number Finance carries into the SPT cannot drift apart. The buyer
  fields follow DJP's own instruction for a non-TIN buyer: NPWP
  ``0000000000000000``, ID TKU ``000000``, kode transaksi ``04`` (DPP Nilai
  Lain, which is what the PMK 131 restatement produces).

The two sources never overlap — the digunggung report covers exactly the moves
that are *not* invoices — so "Keduanya" double-counts nothing and is the
complete picture for a retailer.
- **Bupot Unifikasi** (PPh 23 / 4(2) / 22 / 15) — 23 columns.
- **Bupot PPh 21** — 27 columns, carries Gross Up and PTKP.
- **Bupot Non-Resident** (PPh 26 / 4(2)) — 32 columns, carries TIN, kode
  negara, passport, KITAS and norma penghasilan neto.

Four ways to export e-Faktur Keluaran
-------------------------------------
The FK/OF layout is reachable from four places, all driven by one row builder
(``custom.coretax.fk.builder``) so they can never drift apart:

- **Invoice form** — an ``Export e-Faktur (FK)`` button on a posted customer
  invoice, yielding ``faktur_keluaran_<nomor faktur>.xlsx``.
- **Invoice list** — select any number of invoices, then *Actions ▸ Export
  e-Faktur Keluaran (FK/OF)*. One workbook holds every selection in date order,
  named after the tax period when they share one.
- **Reporting ▸ Export e-Faktur Keluaran (FK)** — a date range plus optional
  customer and sales-journal filters, with a live count of what will be included.
- **Reporting ▸ Export File Import Coretax** — the original whole-masa-pajak
  wizard, alongside the bupot and retur templates.

Only ``out_invoice`` is exported. A credit note is not an FK record; it belongs
to Faktur Pengganti or Retur Masukan, which have their own paths. Anything not
posted is refused by name rather than silently dropped — a tax file that quietly
omits an invoice is worse than one that will not render.

``MASA_PAJAK``/``TAHUN_PAJAK`` are derived per invoice from ``invoice_date``, so
a selection straddling two periods still stamps each FK row correctly.

Down payments
-------------
A sale part-billed in advance is two **independent** fakturs: one issued for the
down payment when it is received, and a settlement faktur for what is left to
pay. Odoo models the settlement as the full price plus a negative down-payment
line; exporting that line as an OF item produced negative quantities and amounts,
which the Coretax importer rejects.

The deduction is therefore netted off the item rows — unit price, gross and tax
base alike — rather than reported in the FK record's ``UANG_MUKA_*`` block. So a
300 juta sale prepaid 50% settles on a **150 juta** faktur whose ``JUMLAH_DPP``
and ``JUMLAH_PPN`` equal the invoice's own ``amount_untaxed`` and ``amount_tax``,
the two fakturs together still add up to the contract, and the settlement faktur
carries no reference to the earlier one: ``NOMOR_FAKTUR_UM_SEBELUMNYA`` and every
``UANG_MUKA_*`` column stay empty. A settlement whose deduction swallows the
whole invoice bills nothing at all, and is refused by name.

Nama Barang/Jasa
----------------
The OF ``NAMA`` cell is the invoice line's own description, flattened to one line
— not ``product_id.name``. ARKA appends the event, its venue and the show date to
each line description, and that block is what the tax team reconciles the faktur
against; taking the product name dropped it. When the description carries no
event but the invoice header does (a faktur raised by hand), the header's event
and venue are appended instead. The header fields are read through ``_fields``,
so the module stays independent of the tenant module that adds them.

Discounts, rounding, and the FK↔OF tie
--------------------------------------
Coretax validates the *written* cells, not the floats behind them, and it checks
two things this module therefore guarantees exactly:

``HARGA_TOTAL - DISKON == DPP`` on every OF row. ``DISKON`` used to be written
as a flat zero on the theory that the discount was already netted into
``price_subtotal`` — true, but it left the three columns not tying on any
discounted line. The gross is now reconstructed from the line's discount
percentage (not from ``price_unit * quantity``, which is wrong when a
price-included tax is in play) and ``DISKON`` is derived last, from the DPP
actually written.

**The FK totals equal the sum of the OF column beneath them.** Rounding each
line independently and separately rounding their sum produces two numbers that
disagree by a rupiah or two. So each OF line but the last is rounded ``DOWN`` to
the currency's rounding and the last line absorbs the whole residual — which is
also what the client's reference workbook does: three equal thirds of 3.740.000
come out 1.246.666 / 1.246.666 / **1.246.668**, not 1.246.667 twice. Applied to
``DPP``, ``DPP_LAIN`` and ``PPN``.

Jenis Barang Jasa
-----------------
The FK ``OF`` rows classify each item as ``Jasa`` or ``Barang``. A down-payment
line carries no product of its own — core builds it from a "fake" SO line — so
classifying on ``line.product_id`` alone reports every down payment as
``Barang``, even one paid against a pure services order. ``_item_jenis()``
therefore falls back to the products of the originating sales order, and answers
``Jasa`` only when every product billed is a service. Ordinary lines, which do
carry a product, are unaffected. The fallback is guarded on ``sale_line_ids``
being present, so the module still works where ``sale`` is not installed.

Identity prerequisites
----------------------
The pemotong columns are read from ``res.company`` (NPWP via its partner,
``x_custom_nitku_suffix``, ``x_custom_npwp_penandatangan``,
``x_custom_coretax_user_id``); the counterparty columns from ``res.partner``
(``x_custom_npwp``, ``x_custom_nitku``, ``x_custom_tin``, …). Both are added by
``custom_tax_id``. Each wizard refuses to render when the pemotong identity is
incomplete rather than emitting a file DJP will bounce — but only for the fields
that layout actually carries: ``NPWP Penandatangan`` is a bupot column, so
e-Faktur Keluaran and Retur Masukan are not blocked on it.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Accounting/Localizations",
    "version": "19.0.1.9.0",
    "license": "LGPL-3",
    "depends": [
        "custom_tax_id",
        "custom_coretax",
        "account",
    ],
    "capability_tags": ["indonesian-tax", "coretax", "efaktur", "bupot", "export"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/coretax_template_export_views.xml",
        "wizards/coretax_fk_export_views.xml",
        "views/account_move_views.xml",
        "data/coretax_fk_server_actions.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
