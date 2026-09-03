# -*- coding: utf-8 -*-
"""Confirm, in writing, that a repeated SKU on a purchase order is deliberate.

A size is not an attribute of the thing ordered, it *is* the thing ordered: every
size is its own ``product.product`` with its own PROD SKU. So an order sheet whose
product column was copied down does not read as broken -- it reads as four perfectly
valid lines that all happen to ask for size 25. Receiving then books exactly what the
order says (the receipt inherits its products from the PO, see
``stock_move._check_levis_receipt_line_from_po``), and the mistake only surfaces when
the box is opened and holds 25, 26, 27 and 28.

``base_import`` runs no onchange, so a warning would never be seen. A hard constraint
would be wrong too: ordering the same SKU twice on one order is legitimate (two
delivery dates, two prices). What is missing is a moment where a person looks at the
repeat and says yes -- which is what this wizard is. It also puts the sizes the
template *does* have next to the repeat, because "26, 27, 28 exist and are not on this
order" is the sentence that makes the mistake obvious.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# The sibling list is a hint, not a catalogue; a jeans template can carry a hundred
# size/inseam combinations and a wall of them helps nobody.
SIBLING_LIMIT = 12


class LevisPoDupSkuWizard(models.TransientModel):
    _name = "levis.po.dup.sku.wizard"
    _description = "Duplicate SKU on Purchase Order — Confirmation"

    order_id = fields.Many2one("purchase.order", required=True, readonly=True, ondelete="cascade")
    order_name = fields.Char(related="order_id.name", string="Purchase Order", readonly=True)
    partner_id = fields.Many2one(related="order_id.partner_id", string="Vendor", readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    # Required in the view, not in the ORM: the wizard record is created *before*
    # the user has typed anything, so a required column would refuse to open it.
    reason = fields.Char(
        string="Alasan",
        help="Kenapa SKU yang sama memang harus muncul lebih dari satu kali. "
        "Tercatat di riwayat pesanan bersama nama Anda.",
    )
    line_ids = fields.One2many("levis.po.dup.sku.wizard.line", "wizard_id", readonly=True)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    @api.model
    def _levis_build_for_order(self, order):
        """Wizard + one line per repeated product of ``order``."""
        order.ensure_one()
        products = order._levis_duplicate_sku_products()
        if not products:
            raise UserError(_("Pesanan %s tidak memuat SKU ganda.", order.display_name))
        return self.create(
            {
                "order_id": order.id,
                "line_ids": [(0, 0, vals) for vals in self._levis_line_vals(order, products)],
            }
        )

    @api.model
    def _levis_line_vals(self, order, products):
        lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        ordered_products = lines.mapped("product_id")
        for product in products:
            repeats = lines.filtered(lambda l, p=product: l.product_id == p)
            yield {
                "product_id": product.id,
                "variant_label": self._levis_variant_label(product),
                "occurrences": len(repeats),
                "product_qty": sum(repeats.mapped("product_qty")),
                "price_unit": repeats[:1].price_unit,
                "sibling_label": self._levis_sibling_label(product, ordered_products),
            }

    @api.model
    def _levis_variant_label(self, product):
        """ "Size: 25 / Inseam: 30" — empty when the template has a single variant.

        Odoo drops single-value attributes from the combination, so a template with
        one size shows nothing here; that is correct, there is no size to confuse.
        """
        values = product.product_template_attribute_value_ids
        return " / ".join("%s: %s" % (v.attribute_id.name, v.name) for v in values)

    @api.model
    def _levis_sibling_label(self, product, ordered_products):
        """The template's other variants that this order does NOT contain."""
        siblings = product.product_tmpl_id.product_variant_ids - ordered_products
        siblings = siblings.filtered(lambda p: p.active)
        if not siblings:
            return ""
        labels = []
        for sibling in siblings[:SIBLING_LIMIT]:
            variant = self._levis_variant_label(sibling)
            labels.append("%s (%s)" % (variant, sibling.default_code) if variant else sibling.display_name)
        if len(siblings) > SIBLING_LIMIT:
            labels.append(_("… dan %s lainnya", len(siblings) - SIBLING_LIMIT))
        return ", ".join(labels)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Isi alasan kenapa SKU ganda ini memang benar."))
        order = self.order_id
        order.write({"l10n_dup_sku_ack": True, "l10n_dup_sku_reason": reason})
        order.message_post(body=self._levis_chatter_body(reason))
        # The context keeps ``purchase.order.line._levis_clear_dup_sku_ack`` from
        # wiping the acknowledgement while core walks the lines on confirm.
        return order.with_context(levis_dup_sku_confirming=True).button_confirm()

    def _levis_chatter_body(self, reason):
        self.ensure_one()
        rows = "".join(
            "<li>%s — %s baris, total %s</li>" % (line.product_id.display_name, line.occurrences, line.product_qty)
            for line in self.line_ids
        )
        return _(
            "<p><b>SKU ganda dikonfirmasi.</b></p><ul>%(rows)s</ul><p>Alasan: %(reason)s</p>",
            rows=rows,
            reason=reason,
        )


class LevisPoDupSkuWizardLine(models.TransientModel):
    _name = "levis.po.dup.sku.wizard.line"
    _description = "Duplicate SKU on Purchase Order — Line"
    _order = "id"

    wizard_id = fields.Many2one("levis.po.dup.sku.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Produk", readonly=True)
    default_code = fields.Char(related="product_id.default_code", string="SKU", readonly=True)
    variant_label = fields.Char(string="Varian", readonly=True)
    occurrences = fields.Integer(string="Jumlah Baris", readonly=True)
    product_qty = fields.Float(string="Total Qty", readonly=True)
    price_unit = fields.Float(string="Harga Satuan", readonly=True)
    sibling_label = fields.Char(string="Varian lain yang TIDAK dipesan", readonly=True)
