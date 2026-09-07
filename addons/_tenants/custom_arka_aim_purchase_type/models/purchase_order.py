# -*- coding: utf-8 -*-
"""Trade / Non-Trade purchase stream on ``purchase.order``.

The stream is picked on the order and drives its number. The tenant already
numbers purchase orders ``PO/<CO>/YYYY/MM/NNN`` from a per-company, monthly
resetting ``ir.sequence`` (``custom_arka_aim_numbering``); this splits that into
two counters, ``PO/T/<CO>/...`` and ``PO/NT/<CO>/...``, seeded by the post-init
hook with the same ``x_monthly_reset`` mechanism.

Numbering falls back to core whenever the stream sequence is missing -- which is
every company without an ``x_doc_code``, i.e. every non-ARKA-AIM database.
"""

from datetime import datetime

from odoo import _, api, fields, models

TRADE_SEQ = "arka_aim.purchase_order_trade"
NONTRADE_SEQ = "arka_aim.purchase_order_nontrade"


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    l10n_purchase_type = fields.Selection(
        [("trade", "Trade"), ("non_trade", "Non-Trade")],
        string="Purchase Type",
        default="trade",
        required=True,
        tracking=True,
        help="Trade = merchandise bought to be sold on (inventory, trade payable, "
        "trade GR/IR). Non-Trade = operational / capex spend (expense or fixed "
        "asset, non-trade payable, non-trade GR/IR). Drives the PO number and the "
        "account routing on the vendor bill.",
    )

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------
    def _arka_next_po_number(self, purchase_type, seq_date=None):
        """Next PO number for ``purchase_type``, or ``False`` to keep core numbering.

        The monthly reset itself is the sequence's own business: the tenant's
        ``ir.sequence`` override creates a one-month ``ir.sequence.date_range``
        for ``x_monthly_reset`` sequences, so drawing the number is enough.
        """
        code = TRADE_SEQ if purchase_type == "trade" else NONTRADE_SEQ
        company = self.company_id or self.env.company
        seq = (
            self.env["ir.sequence"]
            .sudo()
            .search(
                [("code", "=", code), ("company_id", "in", [company.id, False])],
                # company-specific row first; ``company_id`` ascending puts NULL
                # last in PostgreSQL, which is exactly the precedence we want.
                order="company_id",
                limit=1,
            )
        )
        if not seq:
            return False
        dt = seq_date or fields.Date.today()
        if isinstance(dt, datetime):
            dt = dt.date()
        return seq.next_by_id(sequence_date=dt)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) not in (False, "New", "/", _("New")):
                continue
            company_id = vals.get("company_id") or self.default_get(["company_id"]).get("company_id")
            ptype = (
                vals.get("l10n_purchase_type")
                or self.default_get(["l10n_purchase_type"]).get("l10n_purchase_type")
                or "trade"
            )
            seq_date = None
            if vals.get("date_order"):
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals["date_order"]))
            number = self.with_company(company_id)._arka_next_po_number(ptype, seq_date)
            if number:
                vals["name"] = number
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Vendor bill carries the stream (read by account.move.line routing)
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["l10n_purchase_type"] = self.l10n_purchase_type
        return vals
