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
            elif line.display_type == "product" and not line.account_id:
                # Non-trade opex products frequently have no expense account on
                # their master, which would block bill posting. Fall back to the
                # stream's default expense account — but ONLY when the line has no
                # account yet, so a configured product/category account always wins.
                if mapping.expense_account_id:
                    line.account_id = mapping.expense_account_id.id
