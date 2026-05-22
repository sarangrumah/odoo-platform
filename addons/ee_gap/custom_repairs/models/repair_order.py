# -*- coding: utf-8 -*-
"""Extensions to `repair.order` for warranty matrix, SLA, MRP, WhatsApp,
cost analysis, quality check, and returns flow."""

from __future__ import annotations

import logging
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class RepairOrder(models.Model):
    _inherit = "repair.order"

    # ---------- Warranty fields ----------
    x_warranty_status = fields.Selection(
        [
            ("in_warranty", "In Warranty"),
            ("out_of_warranty", "Out of Warranty"),
            ("extended", "Extended Warranty"),
            ("na", "Not Applicable"),
        ],
        string="Warranty Status",
        compute="_compute_warranty_status",
        store=True,
        readonly=False,
        tracking=True,
    )
    x_warranty_until = fields.Date(
        string="Warranty Until",
        compute="_compute_warranty_status",
        store=True,
        readonly=False,
    )
    x_serial_number = fields.Char(string="Serial Number", tracking=True)
    x_purchase_date = fields.Date(string="Purchase Date", tracking=True)

    # ---------- SLA fields ----------
    x_promised_completion_date = fields.Date(
        string="Promised Completion Date",
        tracking=True,
    )
    x_actual_completion_date = fields.Datetime(
        string="Actual Completion Date",
        readonly=True,
    )
    x_sla_status = fields.Selection(
        [
            ("on_track", "On Track"),
            ("at_risk", "At Risk"),
            ("breached", "Breached"),
            ("done", "Done"),
        ],
        string="SLA Status",
        compute="_compute_sla_status",
        store=True,
    )

    # ---------- Customer comm ----------
    x_customer_notified = fields.Boolean(
        string="Customer Notified",
        default=False,
        tracking=True,
    )
    x_id_complaint = fields.Text(
        string="Customer Complaint (ID)",
        help="Customer complaint in Bahasa Indonesia",
    )

    # ---------- Cost analysis ----------
    x_labor_hours = fields.Float(string="Labor Hours", default=0.0)
    x_labor_rate = fields.Float(
        string="Labor Rate (per hour)",
        default=lambda self: self._default_labor_rate(),
    )
    x_material_cost = fields.Float(
        string="Material Cost",
        compute="_compute_total_repair_cost",
        store=True,
    )
    x_labor_cost = fields.Float(
        string="Labor Cost",
        compute="_compute_total_repair_cost",
        store=True,
    )
    x_total_repair_cost = fields.Float(
        string="Total Repair Cost",
        compute="_compute_total_repair_cost",
        store=True,
    )

    # ---------- Returns ----------
    x_returned = fields.Boolean(
        string="Customer Returned",
        default=False,
        tracking=True,
        readonly=True,
        copy=False,
    )
    x_return_date = fields.Datetime(
        string="Return Date",
        readonly=True,
        copy=False,
    )
    x_return_reason = fields.Text(string="Return Reason")

    # ---------- MRP link ----------
    x_mrp_production_id = fields.Many2one(
        "mrp.production",
        string="Work Order (Manufacturing)",
        readonly=True,
        copy=False,
    )

    # ---------- Quality check link ----------
    x_quality_check_ids = fields.One2many(
        "quality.check",
        compute="_compute_quality_check_ids",
        string="Quality Checks",
    )
    x_quality_check_count = fields.Integer(
        compute="_compute_quality_check_ids",
    )

    # ====================================================================
    # Defaults
    # ====================================================================

    @api.model
    def _default_labor_rate(self):
        ICP = self.env["ir.config_parameter"].sudo()
        try:
            return float(ICP.get_param("custom_repairs.labor_rate", "100000"))
        except (TypeError, ValueError):
            return 100000.0

    # ====================================================================
    # Warranty status compute (matrix lookup)
    # ====================================================================

    @api.depends("x_serial_number", "x_purchase_date", "product_id")
    def _compute_warranty_status(self):
        Matrix = self.env["custom.repairs.warranty.matrix"].sudo()
        today = fields.Date.context_today(self)
        for rec in self:
            product = rec.product_id
            if not (rec.x_serial_number and rec.x_purchase_date and product):
                # Keep existing manual values when prerequisites missing.
                if not rec.x_warranty_status:
                    rec.x_warranty_status = "na"
                if rec.x_warranty_until is False:
                    rec.x_warranty_until = False
                continue
            entry = Matrix.search(
                [("product_id", "=", product.id), ("active", "=", True)],
                limit=1,
            )
            if not entry:
                rec.x_warranty_status = "na"
                rec.x_warranty_until = False
                continue
            until = rec.x_purchase_date + relativedelta(months=int(entry.warranty_months or 0))
            rec.x_warranty_until = until
            rec.x_warranty_status = "in_warranty" if today <= until else "out_of_warranty"

    # ====================================================================
    # SLA compute
    # ====================================================================

    @api.depends("x_promised_completion_date", "state", "x_actual_completion_date")
    def _compute_sla_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state == "done" or rec.x_actual_completion_date:
                rec.x_sla_status = "done"
                continue
            if not rec.x_promised_completion_date:
                rec.x_sla_status = "on_track"
                continue
            promised = rec.x_promised_completion_date
            if today > promised:
                rec.x_sla_status = "breached"
            elif (promised - today) <= timedelta(days=1):
                rec.x_sla_status = "at_risk"
            else:
                rec.x_sla_status = "on_track"

    # ====================================================================
    # Cost compute
    # ====================================================================

    def _material_cost_field_candidates(self):
        """Field names on repair material lines that may hold unit/total cost.

        Different Odoo versions / installs expose different field names
        (price_unit, price_subtotal, x_material_cost, etc.). We try each
        gracefully.
        """
        return ("price_subtotal", "price_total", "price_unit")

    def _material_line_records(self):
        """Return material-line records for the repair.

        Odoo 19 uses `move_ids` (stock.move) on repair.order. Older variants
        used `operations` / `parts_lines`. We probe what exists.
        """
        self.ensure_one()
        for candidate in ("move_ids", "operations", "parts_lines"):
            if candidate in self._fields:
                return self[candidate]
        return self.env["stock.move"].browse()

    @api.depends("x_labor_hours", "x_labor_rate")
    def _compute_total_repair_cost(self):
        for rec in self:
            material = 0.0
            try:
                lines = rec._material_line_records()
                for line in lines:
                    qty = getattr(line, "product_uom_qty", 0.0) or getattr(line, "quantity", 0.0) or 0.0
                    unit_cost = 0.0
                    product = getattr(line, "product_id", False)
                    if product and getattr(product, "standard_price", None) is not None:
                        unit_cost = product.standard_price or 0.0
                    if not unit_cost:
                        for fname in rec._material_cost_field_candidates():
                            if fname in line._fields:
                                val = line[fname] or 0.0
                                if val:
                                    unit_cost = val if fname == "price_unit" else 0.0
                                    if fname != "price_unit":
                                        # field already represents subtotal
                                        material += val
                                        unit_cost = 0.0
                                    break
                    if unit_cost:
                        material += unit_cost * qty
            except Exception as exc:  # pragma: no cover (defensive)
                _logger.debug("repair cost material compute fallback: %s", exc)
                material = 0.0
            labor = (rec.x_labor_hours or 0.0) * (rec.x_labor_rate or 0.0)
            rec.x_material_cost = material
            rec.x_labor_cost = labor
            rec.x_total_repair_cost = material + labor

    # ====================================================================
    # Quality check link
    # ====================================================================

    def _compute_quality_check_ids(self):
        has_quality = "quality.check" in self.env
        for rec in self:
            if not has_quality:
                rec.x_quality_check_ids = False
                rec.x_quality_check_count = 0
                continue
            QC = self.env["quality.check"].sudo()
            checks = (
                QC.search(
                    [
                        ("name", "like", rec.name or rec.display_name or ""),
                    ]
                )
                if (rec.name or rec.display_name)
                else QC.browse()
            )
            rec.x_quality_check_ids = checks
            rec.x_quality_check_count = len(checks)

    # ====================================================================
    # Write override: capture actual completion + trigger quality check
    # ====================================================================

    def write(self, vals):
        new_state = vals.get("state")
        if new_state == "done":
            vals.setdefault("x_actual_completion_date", fields.Datetime.now())
        res = super().write(vals)
        if new_state == "done":
            for rec in self:
                rec._maybe_launch_quality_check()
        if new_state == "confirmed":
            for rec in self:
                rec._maybe_create_mrp_workorder()
        return res

    # ====================================================================
    # MRP auto-create work-order
    # ====================================================================

    def _has_material_requirements(self):
        self.ensure_one()
        lines = self._material_line_records()
        for line in lines:
            qty = getattr(line, "product_uom_qty", 0.0) or getattr(line, "quantity", 0.0) or 0.0
            if qty and qty > 0:
                return True
        return False

    def _maybe_create_mrp_workorder(self):
        """Create a stub mrp.production when spare parts are required.

        Best-effort: silently skip when `mrp` is not installed or required
        fields cannot be resolved.
        """
        self.ensure_one()
        if self.x_mrp_production_id:
            return
        if "mrp.production" not in self.env:
            return
        if not self._has_material_requirements():
            return
        MrpProduction = self.env["mrp.production"].sudo()
        product = self.product_id
        if not product:
            return
        try:
            production = MrpProduction.create(
                {
                    "product_id": product.id,
                    "product_qty": 1.0,
                    "product_uom_id": product.uom_id.id if product.uom_id else False,
                    "origin": self.name or self.display_name or "",
                }
            )
        except Exception as exc:  # pragma: no cover (defensive)
            _logger.info("custom_repairs: mrp.production stub create skipped (%s)", exc)
            return
        self.x_mrp_production_id = production.id
        _logger.info(
            "custom_repairs: created mrp.production %s for repair %s",
            production.id,
            self.display_name,
        )

    # ====================================================================
    # WhatsApp status update
    # ====================================================================

    def action_send_status_whatsapp(self):
        """Queue a WhatsApp status update to the customer in Indonesian."""
        Wa = self.env["whatsapp.message"]
        Account = self.env["whatsapp.account"]
        state_labels = dict(self._fields["state"].selection)
        for rec in self:
            partner = rec.partner_id
            phone = (partner.mobile or partner.phone) if partner else False
            if not partner or not phone:
                _logger.info(
                    "custom_repairs: skip WhatsApp for %s (no phone on partner)",
                    rec.display_name,
                )
                continue
            account = Account.search([("active", "=", True)], limit=1)
            if not account:
                _logger.info(
                    "custom_repairs: no active whatsapp.account; skipping %s",
                    rec.display_name,
                )
                continue
            customer_name = partner.name or _("Pelanggan")
            ref = rec.name or rec.display_name or ""
            state_label = state_labels.get(rec.state, rec.state or "")
            date_str = (
                fields.Date.to_string(rec.x_promised_completion_date)
                if rec.x_promised_completion_date
                else _("belum dijadwalkan")
            )
            body = _("Halo %(customer_name)s, status perbaikan %(ref)s: %(state)s. Estimasi selesai: %(date)s") % {
                "customer_name": customer_name,
                "ref": ref,
                "state": state_label,
                "date": date_str,
            }
            Wa.create(
                {
                    "account_id": account.id,
                    "to_phone": phone,
                    "to_partner_id": partner.id,
                    "body": body,
                    "state": "draft",
                }
            )
            rec.x_customer_notified = True
            _logger.info(
                "custom_repairs: queued WhatsApp status for %s -> %s",
                rec.display_name,
                phone,
            )
        return True

    # ====================================================================
    # Quality check on completion
    # ====================================================================

    def _maybe_launch_quality_check(self):
        """Conditionally create a quality.check on done if module present."""
        self.ensure_one()
        if "quality.check" not in self.env or "quality.point" not in self.env:
            return False
        QPoint = self.env["quality.point"].sudo()
        QCheck = self.env["quality.check"].sudo()
        domain = []
        if self.product_id:
            domain = [("product_id", "=", self.product_id.id)]
        point = QPoint.search(domain, limit=1) if domain else QPoint.search([], limit=1)
        if not point:
            return False
        try:
            check = QCheck.create(
                {
                    "point_id": point.id,
                    "note": _("Auto-launched for repair %s") % (self.display_name or ""),
                }
            )
        except Exception as exc:  # pragma: no cover (defensive)
            _logger.info("custom_repairs: quality.check create skipped (%s)", exc)
            return False
        _logger.info(
            "custom_repairs: launched quality.check %s for repair %s",
            check.id,
            self.display_name,
        )
        return check

    # ====================================================================
    # Returns flow
    # ====================================================================

    def action_set_returned(self):
        """Mark the repair as customer-returned."""
        for rec in self:
            rec.write(
                {
                    "x_returned": True,
                    "x_return_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Repair marked as customer-returned."),
            )
        return True
