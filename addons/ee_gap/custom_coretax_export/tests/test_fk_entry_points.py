# -*- coding: utf-8 -*-
"""The four ways into the FK/OF export, and what each of them refuses.

The guards matter more than the happy path: a tax file that quietly omits a
draft invoice is worse than one that will not render at all, so every rejection
below must raise and name the offending record rather than filter it out.
"""

import base64

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install", "custom_coretax_export")
class TestCoretaxFkEntryPoints(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.partner_id.x_custom_npwp = "0012345678901000"
        cls.company.x_custom_nitku_suffix = "000000"
        cls.product = cls.env["product.product"].create({"name": "Barang FK", "type": "consu"})

    def _invoice(self, invoice_date="2026-08-03", move_type="out_invoice", post=True):
        invoice = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": move_type,
                    "partner_id": self.partner_a.id,
                    "invoice_date": invoice_date,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": 2,
                                "price_unit": 150000.0,
                            },
                        )
                    ],
                }
            )
        )
        if post:
            invoice.action_post()
        return invoice

    def _attachment(self, action):
        self.assertEqual(action["type"], "ir.actions.act_url")
        attachment_id = int(action["url"].split("/web/content/")[1].split("?")[0])
        return self.env["ir.attachment"].sudo().browse(attachment_id)

    # ------------------------------------------------------------- refusals

    def test_draft_raises_and_names_the_invoice(self):
        draft = self._invoice(post=False)
        with self.assertRaises(UserError) as caught:
            draft.action_coretax_fk_export()
        self.assertIn(draft.name or "", str(caught.exception))

    def test_mixed_posted_and_draft_raises(self):
        """Must refuse outright, not silently export only the posted one."""
        posted = self._invoice()
        draft = self._invoice(post=False)
        with self.assertRaises(UserError):
            (posted | draft).action_coretax_fk_export()

    def test_cancelled_raises(self):
        invoice = self._invoice()
        invoice.button_cancel()
        with self.assertRaises(UserError):
            invoice.action_coretax_fk_export()

    def test_vendor_bill_raises(self):
        bill = self._invoice(move_type="in_invoice")
        with self.assertRaises(UserError):
            bill.action_coretax_fk_export()

    def test_empty_selection_raises(self):
        with self.assertRaises(UserError):
            self.env["account.move"].sudo().browse().action_coretax_fk_export()

    def test_multi_company_raises(self):
        other = self.setup_other_company()["company"]
        other.partner_id.x_custom_npwp = "0098765432101000"
        other.x_custom_nitku_suffix = "000000"
        mine = self._invoice()
        theirs = (
            self.env["account.move"]
            .sudo()
            .with_company(other)
            .create(
                {
                    "move_type": "out_invoice",
                    "company_id": other.id,
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-08-03",
                    "invoice_line_ids": [(0, 0, {"name": "X", "quantity": 1, "price_unit": 10.0})],
                }
            )
        )
        theirs.action_post()
        with self.assertRaises(UserError):
            (mine | theirs).action_coretax_fk_export()

    # --------------------------------------------------------- happy paths

    def test_form_button_returns_downloadable_workbook(self):
        invoice = self._invoice()
        attachment = self._attachment(invoice.action_coretax_fk_export())

        self.assertTrue(attachment.name.startswith("faktur_keluaran_"))
        self.assertTrue(attachment.name.endswith(".xlsx"))
        # A single invoice is also filed under the invoice itself.
        self.assertEqual(attachment.res_model, "account.move")
        self.assertEqual(attachment.res_id, invoice.id)
        self.assertTrue(base64.b64decode(attachment.datas).startswith(b"PK"))

    def test_list_action_exports_the_whole_selection(self):
        first = self._invoice(invoice_date="2026-08-03")
        second = self._invoice(invoice_date="2026-08-12")
        attachment = self._attachment((first | second).action_coretax_fk_export())

        # Same tax period -> named after it, not after a count.
        self.assertEqual(attachment.name, "faktur_keluaran_08_2026.xlsx")
        self.assertFalse(attachment.res_id)

    def test_filename_falls_back_to_count_across_periods(self):
        first = self._invoice(invoice_date="2026-03-15")
        second = self._invoice(invoice_date="2026-08-12")
        attachment = self._attachment((first | second).action_coretax_fk_export())
        self.assertEqual(attachment.name, "faktur_keluaran_2_faktur_20260812.xlsx")

    # ------------------------------------------------------ reporting wizard

    def _wizard(self, **values):
        base = {
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "company_id": self.company.id,
        }
        base.update(values)
        return self.env["custom.coretax.fk.export.wizard"].sudo().create(base)

    def test_wizard_date_range_selects_the_right_subset(self):
        inside = self._invoice(invoice_date="2026-08-12")
        self._invoice(invoice_date="2026-07-30")  # outside the range
        wizard = self._wizard()

        self.assertEqual(wizard.preview_count, 1)
        self.assertEqual(wizard._fk_moves(), inside)

        attachment = self._attachment(wizard.action_export())
        self.assertEqual(attachment.name, "faktur_keluaran_20260801_20260831.xlsx")

    def test_wizard_partner_filter(self):
        self._invoice(invoice_date="2026-08-12")
        wizard = self._wizard(partner_ids=[(6, 0, self.partner_b.ids)])
        self.assertEqual(wizard.preview_count, 0)

    def test_wizard_raises_when_nothing_matches(self):
        with self.assertRaises(UserError):
            self._wizard(date_from="2027-01-01", date_to="2027-01-31").action_export()

    def test_wizard_rejects_inverted_range(self):
        from odoo.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._wizard(date_from="2026-08-31", date_to="2026-08-01")

    # ------------------------------------------------------- the XML binding

    def test_server_action_is_bound_to_account_move(self):
        """Catches an XML typo at test time rather than at click time."""
        action = self.env.ref("custom_coretax_export.action_coretax_fk_export_moves")
        self.assertEqual(action.binding_model_id, self.env.ref("account.model_account_move"))
        self.assertIn("list", action.binding_view_types)
