# -*- coding: utf-8 -*-
"""Feature #17 — the same SKU on two lines of one purchase order.

The failure this guards against is not a broken order, it is a *plausible* one:
four lines, all valid, all asking for size 25, because the product column was
copied down in the upload sheet. Receiving then books size 25 four times over,
since the receipt takes its products from the order.
"""

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPoDupSkuGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Vendor Dup SKU"})

        size = cls.env["product.attribute"].create(
            {
                "name": "Size",
                "create_variant": "always",
                "value_ids": [Command.create({"name": name}) for name in ("25", "26", "27", "28")],
            }
        )
        cls.template = cls.env["product.template"].create(
            {
                "name": "Kids Jeans",
                "is_storable": True,
                "attribute_line_ids": [
                    Command.create({"attribute_id": size.id, "value_ids": [Command.set(size.value_ids.ids)]})
                ],
            }
        )
        cls.variants = cls.template.product_variant_ids.sorted("id")
        for index, variant in enumerate(cls.variants):
            variant.default_code = "KJ0000%s" % (25 + index)
        cls.size_25 = cls.variants[0]
        cls.size_26 = cls.variants[1]
        cls.plain = cls.env["product.product"].create({"name": "Hang Tag", "is_storable": True})

    # ------------------------------------------------------------------
    def _order(self, products):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "name": product.display_name,
                            "product_qty": 1,
                            "price_unit": 250000.0,
                        }
                    )
                    for product in products
                ],
            }
        )

    # ------------------------------------------------------------------
    def test_01_repeated_sku_opens_the_wizard(self):
        order = self._order([self.size_25] * 4)
        action = order.button_confirm()

        self.assertEqual(action.get("res_model"), "levis.po.dup.sku.wizard")
        # the web client maps over ``views``; an action without it dies in doAction
        self.assertTrue(action.get("views"))
        self.assertEqual(order.state, "draft", "the order must not confirm behind the dialog")

        wizard = self.env["levis.po.dup.sku.wizard"].browse(action["res_id"])
        self.assertEqual(len(wizard.line_ids), 1)
        line = wizard.line_ids
        self.assertEqual(line.product_id, self.size_25)
        self.assertEqual(line.occurrences, 4)
        self.assertEqual(line.product_qty, 4)
        self.assertIn("Size: 25", line.variant_label)
        # the sentence that gives the mistake away
        self.assertIn("Size: 26", line.sibling_label)
        self.assertIn("Size: 28", line.sibling_label)

    def test_02_confirmation_records_who_and_why(self):
        order = self._order([self.size_25, self.size_25])
        wizard = self.env["levis.po.dup.sku.wizard"].browse(order.button_confirm()["res_id"])
        wizard.reason = "dua tanggal kirim"
        wizard.action_confirm()

        self.assertEqual(order.state, "purchase")
        self.assertTrue(order.l10n_dup_sku_ack)
        self.assertEqual(order.l10n_dup_sku_reason, "dua tanggal kirim")
        self.assertTrue(
            any("dua tanggal kirim" in (m.body or "") for m in order.message_ids),
            "the reason must survive in the chatter, not only in the field",
        )

    def test_03_blank_reason_is_refused(self):
        order = self._order([self.size_25, self.size_25])
        wizard = self.env["levis.po.dup.sku.wizard"].browse(order.button_confirm()["res_id"])
        wizard.reason = "   "
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_04_distinct_sizes_confirm_untouched(self):
        order = self._order([self.size_25, self.size_26, self.plain])
        order.button_confirm()
        self.assertEqual(order.state, "purchase")
        self.assertFalse(order.l10n_dup_sku_ack)

    def test_05_back_to_draft_drops_the_acknowledgement(self):
        order = self._order([self.size_25, self.size_25])
        wizard = self.env["levis.po.dup.sku.wizard"].browse(order.button_confirm()["res_id"])
        wizard.reason = "sengaja"
        wizard.action_confirm()
        self.assertTrue(order.l10n_dup_sku_ack)

        order.button_draft()
        self.assertFalse(order.l10n_dup_sku_ack)
        self.assertFalse(order.l10n_dup_sku_reason)
        # and the gate is armed again
        self.assertEqual(order.button_confirm().get("res_model"), "levis.po.dup.sku.wizard")

    def test_06_changing_a_line_drops_the_acknowledgement(self):
        order = self._order([self.size_25, self.size_25])
        order.write({"l10n_dup_sku_ack": True, "l10n_dup_sku_reason": "lama"})
        order.order_line[0].product_qty = 3
        self.assertFalse(order.l10n_dup_sku_ack)
        self.assertFalse(order.l10n_dup_sku_reason)

    def test_07_batch_confirm_stops_instead_of_half_confirming(self):
        clean = self._order([self.size_25, self.size_26])
        dirty = self._order([self.size_25, self.size_25])
        with self.assertRaises(UserError):
            (clean | dirty).button_confirm()
        self.assertEqual(clean.state, "draft")
        self.assertEqual(dirty.state, "draft")
