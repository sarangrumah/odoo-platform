# -*- coding: utf-8 -*-
"""Feature #9 — Trade / Non-Trade purchases + Operating-Unit dimension.

On ``purchase.order``:

* ``l10n_purchase_type`` (trade / non-trade) drives a dedicated numbering
  sequence (``PO/T/EBR/YYYY/MM/#####`` vs ``PO/NT/EBR/YYYY/MM/#####``, monthly
  reset) and the account routing done downstream (payable + GR/IR).
* the vendor bill is routed to the store's own purchase journal and inherits the
  purchase type.

On ``purchase.order.line`` the store's Operating-Unit analytic account is merged
into ``analytic_distribution`` so it flows to the bill lines (core
``_related_analytic_distribution``) and the stock/anglo entries.
"""

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TRADE_SEQ = "purchase.order.levis.trade"
NONTRADE_SEQ = "purchase.order.levis.nontrade"

# Guard against the Quantity / Unit Price columns being swapped in a PO upload: a line
# ordering this many pieces at a unit price this small is a pasted price, not an order.
# Both thresholds are ir.config_parameter so a DB can retune them; either at 0 = guard off.
SWAP_QTY_PARAM = "custom_levis_localization.po_swap_guard_qty"
SWAP_PRICE_PARAM = "custom_levis_localization.po_swap_guard_price"
SWAP_QTY_DEFAULT = 10000.0
SWAP_PRICE_DEFAULT = 100.0


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    l10n_purchase_type = fields.Selection(
        [("trade", "Trade"), ("non_trade", "Non-Trade")],
        string="Purchase Type",
        default="trade",
        required=True,
        tracking=True,
        help="Trade = merchandise for resale (inventory, trade payable, trade "
        "GR/IR). Non-Trade = operational / opex (expense, non-trade payable, "
        "non-trade GR/IR). Drives the PO numbering and account mapping.",
    )

    l10n_ou_analytic_display = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        compute="_compute_l10n_ou_analytic_display",
        help="Operating-Unit analytic of the destination warehouse (Deliver To). "
        "This is what gets stamped on every PO line; pick the store's Receipt "
        "operation type in Deliver To to book the purchase on that store.",
    )

    # ------------------------------------------------------------------
    # Operating Unit (store) analytic
    # ------------------------------------------------------------------
    @api.depends("picking_type_id")
    def _compute_l10n_ou_analytic_display(self):
        for order in self:
            order.l10n_ou_analytic_display = order._levis_ou_analytic()

    def _levis_ou_analytic(self):
        """Operating-Unit analytic account of this PO's store, if any."""
        self.ensure_one()
        wh = self.picking_type_id.warehouse_id
        return wh.l10n_ou_analytic_id if wh else self.env["account.analytic.account"]

    # ------------------------------------------------------------------
    # Numbering: one monthly-reset sequence per purchase type
    # ------------------------------------------------------------------
    def _levis_next_po_number(self, purchase_type, seq_date=None):
        """Return the next PO number for ``purchase_type`` with a monthly reset.

        Native ``ir.sequence`` date ranges are yearly, so a monthly
        ``ir.sequence.date_range`` is ensured for the effective date before the
        counter is drawn — giving a per-month reset. Returns ``False`` when the
        tenant sequences are absent (non-Levi's DBs keep core numbering).
        """
        code = TRADE_SEQ if purchase_type == "trade" else NONTRADE_SEQ
        company = self.company_id or self.env.company
        seq = (
            self.env["ir.sequence"]
            .sudo()
            .search(
                [("code", "=", code), ("company_id", "in", [company.id, False])],
                order="company_id",
                limit=1,
            )
        )
        if not seq:
            return False
        dt = seq_date or fields.Date.today()
        if isinstance(dt, datetime):
            dt = dt.date()
        DateRange = self.env["ir.sequence.date_range"].sudo()
        rng = DateRange.search(
            [
                ("sequence_id", "=", seq.id),
                ("date_from", "<=", dt),
                ("date_to", ">=", dt),
            ],
            limit=1,
        )
        if not rng:
            first = dt.replace(day=1)
            last = first + relativedelta(months=1) - timedelta(days=1)
            DateRange.create({"sequence_id": seq.id, "date_from": first, "date_to": last})
        return seq.next_by_id(sequence_date=dt)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) not in (False, "New", "/", _("New")):
                continue
            company_id = vals.get("company_id") or self.default_get(["company_id"]).get("company_id")
            ptype = vals.get("l10n_purchase_type") or "trade"
            seq_date = None
            if vals.get("date_order"):
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals["date_order"]))
            number = self.with_company(company_id)._levis_next_po_number(ptype, seq_date)
            if number:
                vals["name"] = number
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Vendor bill: route to the store journal, carry the purchase type
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["l10n_purchase_type"] = self.l10n_purchase_type
        wh = self.picking_type_id.warehouse_id
        if wh and wh.l10n_purchase_journal_id:
            vals["journal_id"] = wh.l10n_purchase_journal_id.id
        return vals


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # ------------------------------------------------------------------
    # Quantity / Unit Price column swap in uploads
    # ------------------------------------------------------------------
    @api.constrains("product_qty", "price_unit")
    def _check_levis_qty_price_swap(self):
        """Reject a line whose Quantity is obviously the Unit Price and vice versa.

        PO sheets are uploaded through the native ``base_import``, where the column
        mapping is entirely the user's to get right. Getting it wrong is silent and
        expensive: 06-Aug-2026 saw 18 orders land with 124 million pieces "ordered"
        at Rp 1 apiece, which validated a receipt, moved stock and wrecked the FIFO
        cost of 200 products. An ``@api.onchange`` warning would not have helped —
        ``base_import`` never runs onchanges — so this is a constraint.
        """
        param = self.env["ir.config_parameter"].sudo()
        qty_max = float(param.get_param(SWAP_QTY_PARAM, SWAP_QTY_DEFAULT) or 0.0)
        price_min = float(param.get_param(SWAP_PRICE_PARAM, SWAP_PRICE_DEFAULT) or 0.0)
        if not qty_max or not price_min:
            return  # guard disabled for this database
        for line in self:
            if line.display_type or not line.product_id:
                continue
            if line.product_qty < qty_max or not (0 < line.price_unit < price_min):
                continue
            raise ValidationError(
                _(
                    "Baris '%(product)s' memesan %(qty)s unit dengan harga satuan "
                    "%(price)s — kolom Quantity dan Unit Price kemungkinan besar "
                    "tertukar pada file upload.\n\n"
                    "Periksa mapping kolom di file, lalu impor ulang. Bila jumlah ini "
                    "memang benar, naikkan ambang batas pada parameter sistem "
                    "%(param)s.",
                    product=line.product_id.display_name,
                    qty=line.product_qty,
                    price=line.price_unit,
                    param=SWAP_QTY_PARAM,
                )
            )

    # Preserve the base dependencies (product_id, order_id.partner_id) and add
    # the warehouse so the OU analytic re-stamps if the store changes. Re-declaring
    # @api.depends REPLACES the inherited set, so all triggers are listed here.
    @api.depends("product_id", "order_id.partner_id", "order_id.picking_type_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            if line.display_type:
                continue
            ou = line.order_id._levis_ou_analytic()
            if not ou:
                continue
            line.analytic_distribution = line._levis_merge_ou_distribution(line.analytic_distribution, ou.id)

    @staticmethod
    def _levis_merge_ou_distribution(distribution, ou_id):
        """Merge the Operating-Unit analytic ``ou_id`` into ``distribution``.

        analytic_distribution keys are comma-joined analytic-account ids (one per
        plan) mapping to a percentage. The OU lives in its own plan, so it is
        appended to every existing key; an empty distribution becomes
        ``{str(ou_id): 100}``.
        """
        ou = str(ou_id)
        if not distribution:
            return {ou: 100.0}
        merged = {}
        for key, pct in distribution.items():
            ids = key.split(",")
            if ou not in ids:
                ids.append(ou)
            merged[",".join(ids)] = pct
        return merged
