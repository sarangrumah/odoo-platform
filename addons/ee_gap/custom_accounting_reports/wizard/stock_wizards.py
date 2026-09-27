# -*- coding: utf-8 -*-
"""Wizards for the six stock registers (sheet #26, #27, #28, #59, #64, #69, #70).

One base, six thin subclasses. The base carries the filters every stock report
needs — window, company, warehouse, product, category — and each subclass adds
only what is genuinely its own.

``show_stock`` gates the whole set the same way ``custom.report.purchase``
gates its goods-receipt basis: on a database without ``stock`` these wizards
still open and simply render empty, rather than making this addon depend on a
warehouse it may not have.
"""

from datetime import date

from odoo import api, fields, models


class StockReportWizardBase(models.AbstractModel):
    _name = "custom.report.stock.wizard.base"
    _inherit = "custom.report.wizard.mixin"
    _description = "Stock Report Wizard Base"

    date_from = fields.Date(required=True, default=lambda self: date.today().replace(day=1))
    date_to = fields.Date(required=True, default=lambda self: date.today())
    company_ids = fields.Many2many("res.company", default=lambda self: self.env.companies)
    warehouse_ids = fields.Many2many("stock.warehouse", string="Warehouse")
    product_ids = fields.Many2many("product.product", string="Item")
    categ_ids = fields.Many2many("product.category", string="Product Category")
    show_stock = fields.Boolean(compute="_compute_show_stock")

    @api.depends_context("uid")
    def _compute_show_stock(self):
        available = self.env["custom.report.stock.mixin"]._stock_available()
        for wizard in self:
            wizard.show_stock = available

    def _build_filters(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": self.company_ids.ids or self.env.companies.ids,
            "warehouse_ids": self.warehouse_ids.ids,
            "product_ids": self.product_ids.ids,
            "categ_ids": self.categ_ids.ids,
        }

    def _filename_stem(self):
        return self._report_code or self._name

    def action_print(self):
        self.ensure_one()
        data = {
            "report_code": self._report_code,
            "doc_model": self._name,
            "options": {
                **self._build_filters(),
                "date_from": self.date_from.isoformat(),
                "date_to": self.date_to.isoformat(),
            },
        }
        return self.env.ref("custom_accounting_reports.action_report_custom_financial").report_action(self, data=data)

    def action_export_xlsx(self):
        self.ensure_one()
        options = {
            **self._build_filters(),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }
        filename = "%s_%s_%s.xlsx" % (self._filename_stem(), self.date_from, self.date_to)
        model = self.env["report.custom_accounting_reports.report_dispatch"]._report_model(self._report_code)
        return model._xlsx_action(options, filename)


class StockMovementWizard(models.TransientModel):
    _name = "custom.report.stock.movement.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Movement Inventory Detail Wizard"
    _report_code = "stock_movement"

    def _filename_stem(self):
        return "Movement_Inventory_Detail"


class InventorySummaryWizard(models.TransientModel):
    _name = "custom.report.inventory.summary.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Summary Inventory Wizard"
    _report_code = "inventory_summary"

    group_by = fields.Selection(
        [("none", "No grouping"), ("warehouse", "By Warehouse"), ("category", "By Product Category")],
        string="Group By",
        default="warehouse",
        required=True,
    )

    def _build_filters(self):
        return {**super()._build_filters(), "group_by": self.group_by}

    def _filename_stem(self):
        return "Summary_Inventory"


class InventoryWarehouseWizard(models.TransientModel):
    _name = "custom.report.inventory.warehouse.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Inventory per Warehouse Wizard"
    _report_code = "inventory_warehouse"

    # This report is a position, not a period: only the as-of date is asked
    # for, and date_from is pinned so the engine's window stays valid.
    date_from = fields.Date(required=True, default=lambda self: date(1970, 1, 1))
    date_to = fields.Date(string="As Of", required=True, default=lambda self: date.today())
    group_by = fields.Selection(
        [("warehouse", "By Warehouse"), ("category", "By Product Category")],
        string="Group By",
        default="warehouse",
        required=True,
    )

    def _build_filters(self):
        return {**super()._build_filters(), "group_by": self.group_by}

    def _filename_stem(self):
        return "Inventory_per_Warehouse"


class PurchaseReturnWizard(models.TransientModel):
    _name = "custom.report.purchase.return.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Purchase Return Report Wizard"
    _report_code = "purchase_return"

    partner_ids = fields.Many2many("res.partner", string="Vendors")
    group_by = fields.Selection(
        [("none", "No grouping"), ("vendor", "By Vendor"), ("warehouse", "By Warehouse"), ("month", "By Month")],
        string="Group By",
        default="none",
        required=True,
    )

    def _build_filters(self):
        return {**super()._build_filters(), "partner_ids": self.partner_ids.ids, "group_by": self.group_by}

    def _filename_stem(self):
        return "Purchase_Return_Report"


class StockTransferWizard(models.TransientModel):
    _name = "custom.report.stock.transfer.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Internal Transfer Stock Wizard"
    _report_code = "stock_transfer"

    group_by = fields.Selection(
        [("none", "No grouping"), ("warehouse", "By Warehouse"), ("month", "By Month")],
        string="Group By",
        default="none",
        required=True,
    )

    def _build_filters(self):
        return {**super()._build_filters(), "group_by": self.group_by}

    def _filename_stem(self):
        return "Internal_Transfer_Stock"


class StockAdjustmentWizard(models.TransientModel):
    _name = "custom.report.stock.adjustment.wizard"
    _inherit = "custom.report.stock.wizard.base"
    _description = "Adjustment & Scrap Stock Wizard"
    _report_code = "stock_adjustment"

    adjustment_kind = fields.Selection(
        [("all", "Adjustment + Scrap"), ("adjustment", "Adjustment only"), ("scrap", "Scrap only")],
        string="Tipe",
        default="all",
        required=True,
    )
    group_by = fields.Selection(
        [("none", "No grouping"), ("warehouse", "By Warehouse"), ("kind", "By Tipe"), ("month", "By Month")],
        string="Group By",
        default="none",
        required=True,
    )

    def _build_filters(self):
        return {
            **super()._build_filters(),
            "adjustment_kind": self.adjustment_kind,
            "group_by": self.group_by,
        }

    def _filename_stem(self):
        return "Adjustment_Scrap_Stock"
