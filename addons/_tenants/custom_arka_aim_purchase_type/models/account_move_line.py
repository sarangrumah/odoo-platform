# -*- coding: utf-8 -*-
"""Account routing for the Trade / Non-Trade split.

Core computes the vendor bill's payable (payment-term) line account in
``account.move.line._compute_account_id``. Here the payable follows the stream
carried on the bill, and -- where a goods-receipt accrual was actually booked --
the product lines debit the same GR/IR clearing account the receipt credited, so
the accrual nets to zero instead of the bill hitting expense straight against AP.

Accounts come from ``arka.purchase.account.map``, so no ids leak into code.
"""

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # ``_compute_account_id`` carries no @api.depends in core -- it is a
    # precompute-at-create field. ``move_id.l10n_purchase_type`` is already set on
    # the bill at create time (``purchase.order._prepare_invoice``), so the
    # precompute pass sees it. Same dependency-free semantics here: remap after
    # ``super()``.
    def _compute_account_id(self):
        super()._compute_account_id()
        AccountMap = self.env["arka.purchase.account.map"]
        for line in self:
            move = line.move_id
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            ptype = move.l10n_purchase_type
            if not ptype:
                continue
            mapping = AccountMap._get_map(move.company_id, ptype)
            if not mapping:
                continue
            if line.display_type == "payment_term":
                if mapping.payable_account_id:
                    line.account_id = mapping.payable_account_id.id
            elif line.display_type == "product":
                grir_acc = line._arka_grir_account(mapping)
                if grir_acc:
                    line.account_id = grir_acc.id
                elif not line.account_id and mapping.expense_account_id:
                    # Opex products often carry no expense account on their master,
                    # which blocks bill posting outright. Fall back to the stream's
                    # default -- but only when the line has none, so a configured
                    # product/category account always wins.
                    line.account_id = mapping.expense_account_id.id

    def _arka_grir_account(self, mapping):
        """GR/IR clearing account this bill line must debit, if any.

        Only a line that has a matching goods-receipt accrual may be routed to
        GR/IR, or the clearing account would never be relieved. Three conditions:

        * the line comes from a purchase order -- a bill keyed in by hand never
          booked a receipt accrual, and re-routing it would also clobber the
          expense account the user picked;
        * the product is goods, not a service (a service moves no stock); and
        * its category is ``real_time`` valued, which is the exact condition under
          which the receipt posts Dr Stock Valuation / Cr Stock Variation.

        Every ARKA-AIM product category is periodic today, so this returns empty
        and bills keep their native account. It starts working by itself if a
        category is switched to real-time valuation.
        """
        self.ensure_one()
        if not self.purchase_line_id or self.product_id.type != "consu":
            return self.env["account.account"].browse()
        categ = self.product_id.categ_id.with_company(self.move_id.company_id)
        if categ.property_valuation != "real_time":
            return self.env["account.account"].browse()
        # Mirror the receipt's own account choice: the mapping's GR/IR when set
        # (Non-Trade), else the category's stock-variation account (Trade keeps
        # its per-category GR/IR).
        return mapping.grir_account_id or categ.account_stock_variation_id
