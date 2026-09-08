# -*- coding: utf-8 -*-
"""Goods-receipt (GR/IR) journal for the ARKA-AIM tenant.

Ports the Levi's behaviour (``custom_levis_localization/models/stock_move.py``):
validating a vendor goods receipt books the inventory accrual immediately, so the
value received sits on the balance sheet from the receipt date instead of only
appearing when the vendor bill arrives::

    Goods receipt   Dr Stock Valuation        Cr GR/IR clearing
    Vendor bill     Dr GR/IR clearing         Cr Accounts Payable
    -------------------------------------------------------------
    net effect      Dr Stock Valuation        Cr Accounts Payable

The bill side is already wired in ``account_move_line.py``; this file supplies
the receipt side. Both resolve the SAME GR/IR account through
``arka.purchase.account.map``, per company and per Trade / Non-Trade stream, so
the accrual always nets to zero.

Why the entry is posted by hand rather than by core valuation
-------------------------------------------------------------
Odoo 19 books the receipt journal from ``stock.location.valuation_account_id``
(see ``stock_account/models/stock_move.py::_get_account_move_line_vals``): the
supplier location carries the counterpart account. The Vendors location is
SHARED across companies (``company_id`` is empty) and carries a single account,
while ARKA-AIM runs two companies with separate charts and needs a different
GR/IR per purchase stream on top of that. One shared field cannot express that,
so the entry is built here instead, exactly like the Levi's tenant does.

Switch: ``ir.config_parameter`` ``custom_arka_aim_purchase_type.suppress_gr_journal``
("0" default = post the GR journal, "1" = periodic, post nothing). Posting is
also gated on the product category being ``real_time`` valued -- the same gate
the bill routing uses -- so a periodic category is untouched.
"""

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    _SUPPRESS_GR_PARAM = "custom_arka_aim_purchase_type.suppress_gr_journal"
    _GR_JOURNAL_REF = "ARKA-GR-VAL:%s"  # goods receipt, per stock.move (idempotency)
    _RET_JOURNAL_REF = "ARKA-GR-RET-VAL:%s"  # vendor return, per stock.move

    # ------------------------------------------------------------------
    # Predicates
    # ------------------------------------------------------------------
    def _is_arka_goods_receipt(self):
        """A vendor goods receipt: stock entering from a supplier location.

        Internal transfers, production receipts and customer returns are
        deliberately excluded -- only a true vendor receipt raises a GR/IR
        accrual, because only it will later be relieved by a vendor bill.
        """
        self.ensure_one()
        return self.location_id.usage == "supplier"

    def _is_arka_vendor_return(self):
        """A vendor return: stock leaving the company back to a supplier."""
        self.ensure_one()
        return self.location_dest_id.usage == "supplier"

    def _arka_suppress_gr_journal(self):
        param = self.env["ir.config_parameter"].sudo().get_param(self._SUPPRESS_GR_PARAM, "0")
        return str(param).strip().lower() not in ("0", "false", "", "none")

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------
    def _action_done(self, cancel_backorder=False):
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        done_moves._arka_post_gr_journal()
        done_moves._arka_post_return_journal()
        return done_moves

    def _should_create_account_move(self):
        """Never let core value a vendor move we book ourselves.

        Core posts nothing today (no location carries a valuation account), but
        the day one is configured this guard is what keeps the receipt from
        being booked twice.
        """
        self.ensure_one()
        if not self._arka_suppress_gr_journal() and (self._is_arka_goods_receipt() or self._is_arka_vendor_return()):
            return False
        return super()._should_create_account_move()

    def _arka_post_gr_journal(self):
        for move in self:
            if move.state != "done" or not move._is_arka_goods_receipt():
                continue
            if move._arka_suppress_gr_journal():
                continue
            label = _("Goods Receipt %(picking)s", picking=move.picking_id.name or "")
            move._arka_book_grir_entry(
                ref=self._GR_JOURNAL_REF % move.id,
                label=label,
                incoming=True,
            )

    def _arka_post_return_journal(self):
        for move in self:
            if move.state != "done" or not move._is_arka_vendor_return():
                continue
            if move._arka_suppress_gr_journal():
                continue
            # The exact mirror of a receipt: inventory goes back out and the
            # GR/IR accrual is released, ready for the vendor credit note.
            label = _("Vendor Return %(picking)s", picking=move.picking_id.name or "")
            move._arka_book_grir_entry(
                ref=self._RET_JOURNAL_REF % move.id,
                label=label,
                incoming=False,
            )

    def _arka_grir_amount(self, incoming):
        """Value of the accrual this move raises or releases.

        A receipt is worth ``move.value``, which ``purchase_stock`` sets from the
        purchase price whatever the cost method -- the amount the vendor will
        bill.

        A return is deliberately NOT worth ``move.value``. An outgoing move is
        valued by the cost method, which under standard costing is the product's
        standard price and has nothing to do with what was accrued: returning
        goods received at Rp 250 each would release Rp 100 each and strand the
        difference in the clearing account forever. So a return is worth its
        share of the receipt it reverses, which nets the accrual to exactly zero
        on a full return.
        """
        self.ensure_one()
        if incoming:
            return self.value
        origin = self.origin_returned_move_id
        if origin and origin.quantity:
            return origin.value * (self.quantity / origin.quantity)
        # A vendor delivery that returns nothing in particular (no origin move)
        # falls back to its own value.
        return self.value

    def _arka_book_grir_entry(self, ref, label, incoming):
        """Post one GR/IR entry for this done move.

        ``incoming`` True  -> Dr Stock Valuation / Cr GR/IR (goods receipt);
        ``incoming`` False -> Dr GR/IR / Cr Stock Valuation (vendor return).

        No-op -- and idempotent -- when an entry already carries ``ref``, when
        the category is not real-time valued, when the valuation account, the
        GR/IR account or the journal is missing, or when the move has no value.
        """
        self.ensure_one()
        company = self.company_id
        categ = self.product_id.categ_id.with_company(company)
        if categ.property_valuation != "real_time":
            return
        val_acc = categ.property_stock_valuation_account_id
        # A return picking is not linked to the purchase order, so its stream is
        # read from the receipt it reverses -- the accrual must be released on
        # the very account that raised it.
        ptype = self.picking_id.l10n_purchase_type or self.origin_returned_move_id.picking_id.l10n_purchase_type
        grir_acc = self.env["arka.purchase.account.map"]._grir_account(company, ptype, categ)
        journal = categ.property_stock_journal or company.account_stock_journal_id
        if not (val_acc and grir_acc and journal):
            _logger.info(
                "ARKA GR/IR: move %s not booked -- valuation=%s grir=%s journal=%s",
                self.id,
                val_acc.id or False,
                grir_acc.id or False,
                journal.id or False,
            )
            return
        amount = self._arka_grir_amount(incoming)
        if not amount or company.currency_id.is_zero(amount):
            return
        AccountMove = self.env["account.move"].sudo()
        if AccountMove.search_count([("ref", "=", ref), ("company_id", "=", company.id)]):
            return  # already booked for this move
        debit_acc, credit_acc = (val_acc, grir_acc) if incoming else (grir_acc, val_acc)
        if amount < 0:
            # A negative valuation (e.g. a receipt corrected downwards) is the
            # same entry the other way round, never a negative debit.
            debit_acc, credit_acc = credit_acc, debit_acc
            amount = -amount
        # Carry the purchase line's analytic distribution (the event analytic at
        # ARKA-AIM) so the accrual is sliceable per event, exactly like the bill.
        analytic = (
            self.purchase_line_id.analytic_distribution
            or self.origin_returned_move_id.purchase_line_id.analytic_distribution
            or False
        )
        partner = self.picking_id.partner_id
        line_vals = {
            "name": label,
            "product_id": self.product_id.id,
            "partner_id": partner.id or False,
            "analytic_distribution": analytic,
        }
        entry = AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": company.id,
                "date": fields.Date.context_today(self),
                "ref": ref,
                "partner_id": partner.id or False,
                "line_ids": [
                    (0, 0, dict(line_vals, account_id=debit_acc.id, debit=amount, credit=0.0)),
                    (0, 0, dict(line_vals, account_id=credit_acc.id, debit=0.0, credit=amount)),
                ],
            }
        )
        entry._post(soft=False)
        return entry
