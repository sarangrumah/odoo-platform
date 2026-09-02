# -*- coding: utf-8 -*-
"""What the buyer wrote on the PO has to reach the selling company."""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestIcPoMirror(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_from = cls.env["res.company"].create({"name": "IC Buyer Co"})
        cls.company_to = cls.env["res.company"].create({"name": "IC Seller Co"})
        cls.env.user.company_ids = [(4, cls.company_from.id), (4, cls.company_to.id)]

        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company_to.id)], limit=1)
        cls.service = cls.env["product.product"].create({"name": "Drone Show Package", "type": "service"})
        cls.rule = cls.env["account.intercompany.rule"].create(
            {
                "name": "Buyer -> Seller",
                "company_from_id": cls.company_from.id,
                "company_to_id": cls.company_to.id,
                "mirror_purchase_order": True,
                "target_warehouse_id": cls.warehouse.id,
            }
        )

    def _po(self, note=False, extra_lines=None):
        lines = [
            (
                0,
                0,
                {
                    "product_id": self.service.id,
                    "name": "Sewa Drone Show 1500 Unit",
                    "product_qty": 1.0,
                    "price_unit": 800000000.0,
                },
            )
        ]
        lines += extra_lines or []
        vals = {
            "partner_id": self.company_to.partner_id.id,
            "company_id": self.company_from.id,
            "order_line": lines,
        }
        if note:
            vals["note"] = note
        return self.env["purchase.order"].with_company(self.company_from).create(vals)

    def _mirror_of(self, po):
        po.with_company(self.company_from).button_confirm()
        po.invalidate_recordset()
        return po.x_custom_ic_mirror_so_id

    # ------------------------------------------------------------------
    # Header note
    # ------------------------------------------------------------------
    def test_header_note_reaches_the_seller(self):
        po = self._po(note="<p>MERDEKA RUN - MONAS</p>")
        so = self._mirror_of(po)
        self.assertTrue(so, "PO confirm should have produced a mirror SO")
        self.assertIn("MERDEKA RUN - MONAS", so.note or "")

    def test_absent_note_is_not_invented(self):
        so = self._mirror_of(self._po())
        self.assertFalse(so.note)

    # ------------------------------------------------------------------
    # Line description
    # ------------------------------------------------------------------
    def test_line_description_is_carried(self):
        po = self._po()
        so = self._mirror_of(po)
        line = so.order_line.filtered(lambda line: not line.display_type)
        self.assertEqual(line.name, "Sewa Drone Show 1500 Unit")

    # ------------------------------------------------------------------
    # Section / note lines
    # ------------------------------------------------------------------
    def test_section_and_note_lines_stay_display_lines(self):
        po = self._po(
            extra_lines=[
                (
                    0,
                    0,
                    {
                        "display_type": "line_section",
                        "name": "Perangkat Pendukung",
                        "product_qty": 0.0,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "display_type": "line_note",
                        "name": "Bayar sebelum acara.",
                        "product_qty": 0.0,
                    },
                ),
            ]
        )
        so = self._mirror_of(po)
        display = so.order_line.filtered(lambda line: line.display_type)
        self.assertEqual(len(display), 2)
        self.assertEqual(set(display.mapped("display_type")), {"line_section", "line_note"})
        self.assertIn("Perangkat Pendukung", display.mapped("name"))
        # A display line must never become a product line the buyer never wrote.
        self.assertFalse(any(display.mapped("product_id")))

    def test_display_lines_do_not_count_as_mirrorable_content(self):
        """A PO of nothing but notes has nothing to sell — it must still raise.

        The mirror swallows the error and reports it on the chatter, so the
        symptom is "no SO created", not an exception.
        """
        self.rule.spawn_rental_loan = True
        po = (
            self.env["purchase.order"]
            .with_company(self.company_from)
            .create(
                {
                    "partner_id": self.company_to.partner_id.id,
                    "company_id": self.company_from.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "display_type": "line_note",
                                "name": "Catatan saja.",
                                "product_qty": 0.0,
                            },
                        ),
                    ],
                }
            )
        )
        self.assertFalse(self._mirror_of(po))
