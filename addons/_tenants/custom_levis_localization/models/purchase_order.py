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

Also here: the duplicate-SKU gate on ``button_confirm``. A garment size IS its own
variant, and a PO sheet whose product column was copied down orders the same size
several times over -- which is then received, in good faith, as four pieces of size
25 when the box holds 25/26/27/28. Nothing downstream can catch it: the receipt
inherits its products from the PO (``stock_move._check_levis_receipt_line_from_po``),
so by then the wrong size is already the truth. See
``wizard/levis_po_dup_sku_wizard.py``.
"""

from collections import Counter
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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

    l10n_dup_sku_ack = fields.Boolean(
        string="Duplicate SKU Acknowledged",
        copy=False,
        tracking=True,
        help="Set when somebody confirmed, in writing, that the repeated SKU on this "
        "order is deliberate. Cleared again whenever the order goes back to draft or "
        "a line changes product.",
    )
    l10n_dup_sku_reason = fields.Char(
        string="Duplicate SKU Reason",
        copy=False,
        help="Why the same SKU legitimately appears more than once on this order.",
    )

    # ------------------------------------------------------------------
    # Duplicate-SKU gate (one size ordered twice is nearly always a copied cell)
    # ------------------------------------------------------------------
    def _levis_duplicate_sku_products(self):
        """Products that appear on more than one line of this order.

        Returned in line order so the wizard reads the same way as the order the
        buyer is looking at.
        """
        self.ensure_one()
        lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
        # ``mapped`` de-duplicates a recordset, so count over the raw line ids.
        counts = Counter(line.product_id.id for line in lines)
        dup_ids = [pid for pid, n in counts.items() if n > 1]
        if not dup_ids:
            return self.env["product.product"].browse()
        seen, ordered = set(), []
        for line in lines:
            pid = line.product_id.id
            if pid in dup_ids and pid not in seen:
                seen.add(pid)
                ordered.append(pid)
        return self.env["product.product"].browse(ordered)

    def _levis_open_dup_sku_wizard(self):
        """Full-screen confirmation listing the repeats and the sizes NOT ordered."""
        self.ensure_one()
        wizard = self.env["levis.po.dup.sku.wizard"]._levis_build_for_order(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("SKU ganda pada pesanan ini"),
            "res_model": "levis.po.dup.sku.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            # ``views`` is not optional: the web client maps over it, and an action
            # dict without it fails in doAction long before the dialog is drawn.
            "views": [(False, "form")],
            "target": "new",
        }

    def button_confirm(self):
        pending = self.filtered(
            lambda o: o.state in ("draft", "sent") and not o.l10n_dup_sku_ack and o._levis_duplicate_sku_products()
        )
        if pending:
            if len(self) > 1:
                # A batch confirm cannot stop on one order and continue with the rest
                # without half-confirming the selection, so it stops on all of them.
                raise UserError(
                    _(
                        "Pesanan berikut memuat SKU yang sama lebih dari satu kali dan "
                        "harus dikonfirmasi satu per satu:\n%(orders)s",
                        orders="\n".join("- %s" % name for name in pending.mapped("name")),
                    )
                )
            return pending._levis_open_dup_sku_wizard()
        return super().button_confirm()

    def button_draft(self):
        res = super().button_draft()
        # The acknowledgement covered the lines as they were; back in draft they are
        # about to change, so it has to be earned again.
        self.filtered("l10n_dup_sku_ack").write({"l10n_dup_sku_ack": False, "l10n_dup_sku_reason": False})
        return res

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
    # Keep the duplicate-SKU acknowledgement honest
    # ------------------------------------------------------------------
    _DUP_ACK_TRIGGERS = ("product_id", "product_qty")

    def _levis_clear_dup_sku_ack(self):
        """Drop the acknowledgement on any draft order whose lines just moved.

        Skipped while the confirmation wizard is driving ``button_confirm``: core
        touches the lines on its way to ``purchase`` state, and the acknowledgement
        it is acting on must survive that.
        """
        if self.env.context.get("levis_dup_sku_confirming"):
            return
        orders = self.order_id.filtered(lambda o: o.l10n_dup_sku_ack and o.state in ("draft", "sent"))
        if orders:
            orders.write({"l10n_dup_sku_ack": False, "l10n_dup_sku_reason": False})

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._levis_clear_dup_sku_ack()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in self._DUP_ACK_TRIGGERS):
            self._levis_clear_dup_sku_ack()
        return res

    def unlink(self):
        orders = self.order_id
        res = super().unlink()
        if self.env.context.get("levis_dup_sku_confirming"):
            return res
        orders.filtered(lambda o: o.l10n_dup_sku_ack and o.state in ("draft", "sent")).write(
            {"l10n_dup_sku_ack": False, "l10n_dup_sku_reason": False}
        )
        return res

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
