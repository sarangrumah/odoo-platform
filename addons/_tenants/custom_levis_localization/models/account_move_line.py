# -*- coding: utf-8 -*-
"""Payable-account routing for the Trade / Non-Trade split (feature #9).

The vendor bill's payable (payment-term) line account is computed by core
``account.move.line._compute_account_id``. For Levi's, the payable must follow
the purchase stream carried on the bill (``account.move.l10n_purchase_type``):
Trade Payables vs Non-Trade payable. The accounts come from the per-company
``levis.purchase.account.map`` so no hard ids leak into code.
"""

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Base ``_compute_account_id`` carries no @api.depends — it is a
    # precompute-at-create field. ``move_id.l10n_purchase_type`` is already set on
    # the bill at create time (via ``purchase.order._prepare_invoice``), so the
    # precompute pass sees it. We keep the same (dependency-free) semantics and
    # just remap the payable after ``super()``.
    def _compute_account_id(self):
        super()._compute_account_id()
        AccountMap = self.env["levis.purchase.account.map"]
        # GR/IR routing only applies while the goods-receipt accrual is posted
        # per receipt (suppress switch OFF, the default). In periodic mode the
        # accrual is trued up by Inventory Reconciliation, not per bill, so the
        # bill keeps its native/expense account. The switch is the same
        # ir.config_parameter read by stock.move._levis_suppress_gr_journal.
        suppress = self.env["ir.config_parameter"].sudo().get_param(
            "custom_levis_localization.suppress_gr_journal", "0"
        )
        gr_accrual_active = str(suppress).strip().lower() in ("0", "false", "", "none")
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
                # Route the AP control account per stream (trade vs non-trade).
                if mapping.payable_account_id:
                    line.account_id = mapping.payable_account_id.id
            elif line.display_type == "product":
                # Storable, real-time products booked a GR/IR accrual on receipt
                #   Dr Stock Valuation / Cr Stock Variation (GR/IR)
                # (see stock_move.py::_levis_book_valuation_entry). The vendor
                # bill must debit that SAME GR/IR account so the accrual nets to
                # zero — Dr GR/IR clearing / Cr AP — instead of posting COGS/
                # expense directly against AP (the reported bug). Mirror the
                # receipt's account choice exactly: mapping.grir_account_id when
                # set (non-trade), else the category's stock-variation account
                # (trade keeps its per-category GR/IR).
                grir_acc = self.browse()
                # Gate on the SAME condition as the receipt-side GR journal
                # (stock_move.py::_levis_book_valuation_entry): the product's
                # category is real-time. NOT on ``is_storable`` — the imported
                # Levi's catalog is entirely ``type='consu', is_storable=False``
                # yet still real-time valued, so an ``is_storable`` gate never
                # fired and the accrual never netted (bill hit COGS instead of
                # GR/IR). Services carry no stock move / GR accrual, so exclude.
                if gr_accrual_active and line.product_id.type == "consu":
                    categ = line.product_id.categ_id.with_company(move.company_id)
                    if categ.property_valuation == "real_time":
                        grir_acc = mapping.grir_account_id or categ.account_stock_variation_id
                if grir_acc:
                    line.account_id = grir_acc.id
                elif not line.account_id and mapping.expense_account_id:
                    # Non-trade opex products frequently have no expense account
                    # on their master, which would block bill posting. Fall back
                    # to the stream's default expense account — but ONLY when the
                    # line has no account yet, so a configured product/category
                    # account always wins.
                    line.account_id = mapping.expense_account_id.id
