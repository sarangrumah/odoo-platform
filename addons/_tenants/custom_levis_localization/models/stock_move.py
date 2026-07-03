# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.constrains("purchase_line_id", "picking_id")
    def _check_levis_receipt_line_from_po(self):
        # Requirement: on a PO-linked goods receipt only lines that originate
        # from the purchase order (i.e. carry a purchase_line_id) may be
        # received. Any manually added line -- even for a product that is
        # already on the PO -- is rejected the moment it is saved.
        for move in self:
            picking = move.picking_id
            if not picking or picking.picking_type_code != "incoming":
                continue
            if move.purchase_line_id:
                # Line originates from a PO line -> allowed.
                continue
            orders = picking._levis_purchase_orders()
            if not orders:
                # Receipt not tied to any purchase order -> no restriction.
                continue
            raise ValidationError(
                _(
                    "Line '%(product)s' was not created from purchase order "
                    "%(orders)s and cannot be added to this receipt.\n"
                    "Only lines that come from the purchase order may be "
                    "received here.",
                    product=move.product_id.display_name,
                    orders=", ".join(orders.mapped("name")) or "-",
                )
            )

    def _is_levis_goods_receipt(self):
        """A vendor goods receipt: stock entering from a supplier location.

        This deliberately excludes internal transfers, manufacturing receipts
        and customer returns — only true vendor receipts skip GL posting.
        """
        self.ensure_one()
        return self.location_id.usage == "supplier"

    # Config switch (ir.config_parameter) that decides whether vendor goods
    # receipts skip the GL posting. Default OFF -> Automated valuation posts the
    # GR journal natively (Dr Inventory / Cr Stock-Input/GRIR). Set to "1" to
    # restore the periodic behaviour (no GR journal + Inventory Reconciliation).
    _SUPPRESS_GR_PARAM = "custom_levis_localization.suppress_gr_journal"

    def _levis_suppress_gr_journal(self):
        param = self.env["ir.config_parameter"].sudo().get_param(self._SUPPRESS_GR_PARAM, "0")
        return str(param).strip().lower() not in ("0", "false", "", "none")

    def _should_create_account_move(self):
        # Requirement 3 (now opt-in): suppress the inventory journal on Goods
        # Receipt confirm ONLY when the periodic switch is enabled. When it is
        # off (default), Automated valuation posts the GR journal normally; the
        # stock valuation layer is produced by stock_account either way.
        self.ensure_one()
        if self._levis_suppress_gr_journal() and self._is_levis_goods_receipt():
            return False
        return super()._should_create_account_move()

    # ------------------------------------------------------------------
    # GR journal — posted the platform way (valuation + stock-variation)
    # ------------------------------------------------------------------
    # This build has NO standard stock input/output interim account fields, so
    # core real-time valuation posts nothing on a receipt. Inventory GL is wired
    # only through property_stock_valuation_account_id + account_stock_variation_id
    # (the same pair the Inventory Reconciliation tool books). So when the GR
    # journal is wanted (suppress switch OFF, the default), post it directly:
    #   Dr Stock Valuation account / Cr Stock Variation (GR/IR) account
    # for the received inventory value (net of recoverable tax = move.value).
    _GR_JOURNAL_REF = "GR-VAL:%s"  # per stock.move, used for idempotency

    def _action_done(self, cancel_backorder=False):
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        done_moves._levis_post_gr_journal()
        return done_moves

    def _levis_post_gr_journal(self):
        AccountMove = self.env["account.move"]
        for move in self:
            if move.state != "done" or not move._is_levis_goods_receipt():
                continue
            if move._levis_suppress_gr_journal():
                continue
            company = move.company_id
            categ = move.product_id.categ_id.with_company(company)
            if categ.property_valuation != "real_time":
                continue
            val_acc = categ.property_stock_valuation_account_id
            var_acc = categ.account_stock_variation_id
            journal = categ.property_stock_journal or company.account_stock_journal_id
            if not (val_acc and var_acc and journal):
                continue
            amount = move.value  # incoming inventory value (net of recoverable tax)
            currency = company.currency_id
            if not amount or currency.is_zero(amount):
                continue
            ref = self._GR_JOURNAL_REF % move.id
            if AccountMove.search_count(
                [("ref", "=", ref), ("company_id", "=", company.id)]
            ):
                continue  # already posted for this move
            label = _("Goods Receipt %(picking)s", picking=move.picking_id.name or "")
            AccountMove.create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "company_id": company.id,
                    "date": fields.Date.context_today(move),
                    "ref": ref,
                    "line_ids": [
                        (0, 0, {
                            "account_id": val_acc.id, "name": label,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": -amount if amount < 0 else 0.0,
                        }),
                        (0, 0, {
                            "account_id": var_acc.id, "name": label,
                            "debit": -amount if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0,
                        }),
                    ],
                }
            ).action_post()
