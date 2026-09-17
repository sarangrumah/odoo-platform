# -*- coding: utf-8 -*-
"""The four DJP / Mitra Pajakku layouts must match the client's own templates.

Sheet rows #34 and #35. These are import files: the receiving system reads by
position, so a column added, dropped or reordered makes the file useless in a
way no amount of correct arithmetic rescues. The column tuples are transcribed
verbatim from ``docs/projects/levis/tax-templates/``; these tests pin the shape
they produce so a well-meant tidy-up cannot silently break an upload.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.custom_coretax_export.wizards.coretax_template_export import (
    DETAIL_FAKTUR_CORETAX_COLUMNS,
    FAKTUR_CORETAX_COLUMNS,
    RM_COLUMNS,
    RM_OF_COLUMNS,
)
from odoo.addons.custom_coretax_export.models.coretax_fk_builder import (
    FK_COLUMNS,
    OF_COLUMNS,
)


@tagged("post_install", "-at_install")
class TestTemplateShapes(TransactionCase):
    def test_column_counts_match_the_published_templates(self):
        """Counts taken from the four files the client sent on 17-Sep-2026."""
        self.assertEqual(len(FK_COLUMNS), 35, "Mitra Pajakku FK row")
        self.assertEqual(len(OF_COLUMNS), 16, "Mitra Pajakku OF row")
        self.assertEqual(len(FAKTUR_CORETAX_COLUMNS), 18, "Coretax Faktur sheet")
        self.assertEqual(len(DETAIL_FAKTUR_CORETAX_COLUMNS), 14, "Coretax DetailFaktur sheet")
        self.assertEqual(len(RM_COLUMNS), 24, "Mitra Pajakku RM row")
        self.assertEqual(len(RM_OF_COLUMNS), 23, "Mitra Pajakku retur OF row")

    def test_coretax_faktur_starts_and_ends_where_the_template_does(self):
        self.assertEqual(FAKTUR_CORETAX_COLUMNS[0], "Baris")
        self.assertEqual(FAKTUR_CORETAX_COLUMNS[-1], "ID TKU Pembeli")
        self.assertEqual(DETAIL_FAKTUR_CORETAX_COLUMNS[0], "Baris")
        self.assertEqual(DETAIL_FAKTUR_CORETAX_COLUMNS[-1], "PPnBM")

    def test_retur_pajakku_keeps_its_duplicated_names(self):
        """The OF header repeats four names on purpose.

        Columns 9-16 carry the *faktur* figures and 17-23 the *retur* ones, and
        the importer reads by position. Deduplicating them would look tidier
        and break every upload.
        """
        self.assertEqual(RM_OF_COLUMNS.count("RETUR_DISKON"), 2)
        self.assertEqual(RM_OF_COLUMNS.count("RETUR_DPP"), 2)
        self.assertEqual(RM_OF_COLUMNS.count("RETUR_DPP_LAIN"), 2)
        self.assertEqual(RM_OF_COLUMNS.count("RETUR_PPN"), 2)

    def test_digunggung_buyer_fields_follow_the_djp_instruction(self):
        """The Coretax template's own "Keterangan" sheet dictates these.

        "NPWP/NIK Pembeli ... isikan dengan 0000000000000000 jika Jenis ID
        Pembeli selain TIN" and "ID TKU Pembeli ... jika selain TIN isikan
        dengan 000000". A retail seller has no buyer to name, so these are not
        placeholders we invented.
        """
        from odoo.addons.custom_coretax_export.wizards import coretax_template_export as mod

        self.assertEqual(mod.DIGUNGGUNG_NPWP_PEMBELI, "0000000000000000")
        self.assertEqual(len(mod.DIGUNGGUNG_NPWP_PEMBELI), 16)
        self.assertEqual(mod.DIGUNGGUNG_ID_TKU_PEMBELI, "000000")
        self.assertEqual(mod.DIGUNGGUNG_JENIS_ID, "Other ID")
        # 04 = DPP Nilai Lain, which is what the PMK 131 restatement produces.
        self.assertEqual(mod.DIGUNGGUNG_KODE_TRANSAKSI, "04")
        self.assertEqual(mod.DIGUNGGUNG_SATUAN, "UM.0018")

    def test_every_template_has_a_builder(self):
        """A Selection value with no builder raises "belum diimplementasikan"
        only once a user has already filled the form in."""
        wizard = self.env["custom.coretax.template.export.wizard"]
        offered = {code for code, _label in wizard._fields["template"].selection}
        self.assertEqual(offered - set(wizard._BUILDERS), set())
        for code, (method, _sheet, _stem) in wizard._BUILDERS.items():
            self.assertTrue(hasattr(wizard, method), "%s -> %s missing" % (code, method))

    def test_multi_sheet_templates_are_marked_by_a_null_sheet_name(self):
        """``sheet_name is None`` is how ``action_export`` knows the builder
        returns sheet tuples rather than one header/row pair."""
        wizard = self.env["custom.coretax.template.export.wizard"]
        self.assertIsNone(wizard._BUILDERS["fk_coretax"][1])
        self.assertIsNone(wizard._BUILDERS["retur"][1])
        self.assertEqual(wizard._BUILDERS["fk"][1], "Import FK")
        self.assertEqual(wizard._BUILDERS["retur_pajakku"][1], "Import RM")
