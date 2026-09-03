# -*- coding: utf-8 -*-
"""Periodic Cost of Goods Sold, split per Operating Unit.

Levi's sells before it buys: the POS backlog is imported months ahead of the
purchase data, so at the moment a sale is recorded no unit cost exists yet.
Odoo 19 cannot repair that afterwards — ``stock.move.value`` is a plain stored
column written once in ``_action_done``, and the ``_run_fifo_vacuum`` that used
to revalue past outgoing moves is gone. An outgoing move made against empty
stock is valued ``quantity * standard_price`` (i.e. zero) and stays zero
forever. Recognising COGS at the sale is therefore not an option here.

So COGS is recognised **periodically**, the way a periodic-inventory shop does
it: once the purchases for a period are in and each product carries a cost,
this model multiplies the quantity sold by that cost, aggregates it per
(Operating Unit, product category) and books

    Dr COGS-<category>          (P&L, carries the OU analytic)
        Cr Inventories-<category>

as a DRAFT ``account.move`` for the accountant to review — the same contract as
``levis.inventory.reconciliation``, which trues the inventory asset up to the
real on-hand value. The two are complements: this one moves cost out of
inventory into P&L per store, that one absorbs whatever drift is left.

No stock moves are involved, so the X20 on-hand snapshot the retail import
relies on is untouched.

What this run books is written to ``levis.cogs.charge``, the ledger of cost
already recognised per (product, store, sale month), and what the receipt-driven
catch-up (``cogs_catchup.py``) already charged is subtracted before booking. The
two mechanisms therefore compose: whichever learns the cost first recognises it,
and the other stays quiet.

Unit cost is ``product.standard_price`` read in the company's context, which is
what ``product._update_standard_price()`` refreshes on every goods receipt.
Products still without a cost are counted and reported rather than silently
contributing zero — an understated COGS that nobody notices is worse than a
visible gap.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

# POS orders that represent a real, settled sale. Draft/cancelled carry no cost.
_SOLD_STATES = ("paid", "done", "invoiced")


class LevisCogsRun(models.Model):
    _name = "levis.cogs.run"
    _description = "Periodic COGS per Operating Unit"
    _order = "date_to desc, id desc"

    name = fields.Char(default="/", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many("levis.cogs.run.line", "run_id", copy=False)
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("computed", "Computed"), ("generated", "Generated")],
        default="draft",
        copy=False,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    total_cogs = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    zero_cost_qty = fields.Float(
        compute="_compute_totals",
        digits="Product Unit of Measure",
        string="Quantity Without Cost",
        help="Units sold whose product still has no cost. They contribute "
        "nothing to the COGS below, so the figure is understated by whatever "
        "these are worth. Load the purchases for those products and recompute.",
    )

    @api.depends("line_ids.amount", "line_ids.zero_cost_qty")
    def _compute_totals(self):
        for run in self:
            run.total_cogs = sum(run.line_ids.mapped("amount"))
            run.zero_cost_qty = sum(run.line_ids.mapped("zero_cost_qty"))

    @api.constrains("date_from", "date_to")
    def _check_period(self):
        for run in self:
            if run.date_to < run.date_from:
                raise UserError(_("The end date precedes the start date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("levis.cogs.run") or "/"
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------
    def _sold_quantities(self, warehouse):
        """Quantity sold per product at ``warehouse`` during the period.

        Refund lines carry a negative ``qty``, so they net the COGS down on
        their own. Returns ``{product: qty}``.
        """
        self.ensure_one()
        return self.env["levis.cogs.charge"]._sold_quantities(self.company_id, warehouse, self.date_from, self.date_to)

    def _detail(self):
        """Units awaiting COGS, per (sale month, warehouse, product).

        Sales already charged by a receipt catch-up (``levis.cogs.charge``) are
        subtracted here — without that, a month in which a late goods receipt
        revealed a cost would be charged twice, once by the catch-up and once
        by this run. The ledger is kept per sale MONTH, so a run covering only
        part of a month subtracts that whole month's catch-up: partial-month
        runs are not how this is operated, and over-subtracting is the safe
        direction (cost deferred, never doubled).

        Returns a list of dicts, the raw material for both the aggregated run
        lines and the ledger rows written when the entry is generated.
        """
        self.ensure_one()
        Charge = self.env["levis.cogs.charge"]
        company = self.company_id
        rows = []
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", company.id)])
        for period_date in Charge._months_between(self.date_from, self.date_to):
            month_start = max(period_date, self.date_from)
            month_end = min(Charge._month_end(period_date), self.date_to)
            for warehouse in warehouses:
                sold = Charge._sold_quantities(company, warehouse, month_start, month_end)
                if not sold:
                    continue
                charged = Charge._charged_quantities(company, warehouse, period_date)
                for product, qty in sold.items():
                    # Services and the non-merchandise items the retail import
                    # passes through (paper bags and the like) never sat in
                    # inventory, so they have no cost to release.
                    if not product.is_storable:
                        continue
                    remaining = qty - charged.get(product, 0.0)
                    if company.currency_id.is_zero(remaining):
                        continue
                    cost = product.with_company(company).standard_price
                    rows.append(
                        {
                            "period_date": period_date,
                            "warehouse": warehouse,
                            "product": product,
                            "quantity": remaining,
                            "cost": cost,
                            "amount": remaining * cost if cost else 0.0,
                        }
                    )
        return rows

    def _cogs_by_warehouse_category(self, detail=None):
        """Aggregate the detail into ``{(warehouse, category): bucket}``.

        A bucket is ``{"qty", "amount", "zero_cost_qty"}``. Products still
        without a cost are counted in ``zero_cost_qty`` rather than silently
        contributing zero — an understated COGS that nobody notices is worse
        than a visible gap.
        """
        self.ensure_one()
        company = self.company_id
        result = {}
        for row in detail if detail is not None else self._detail():
            categ = row["product"].categ_id.with_company(company)
            key = (row["warehouse"], categ)
            bucket = result.setdefault(key, {"qty": 0.0, "amount": 0.0, "zero_cost_qty": 0.0})
            bucket["qty"] += row["quantity"]
            if not row["cost"]:
                bucket["zero_cost_qty"] += row["quantity"]
                continue
            bucket["amount"] += row["amount"]
        return result

    def _cogs_by_category(self, warehouse):
        """One warehouse's slice of :meth:`_cogs_by_warehouse_category`."""
        self.ensure_one()
        return {categ: bucket for (wh, categ), bucket in self._cogs_by_warehouse_category().items() if wh == warehouse}

    def action_compute(self):
        for run in self:
            if run.move_id:
                raise UserError(_("A journal entry was already generated for %s.", run.name))
            run.line_ids.unlink()
            lines = []
            buckets = run._cogs_by_warehouse_category()
            for (warehouse, categ), bucket in sorted(buckets.items(), key=lambda item: (item[0][0].id, item[0][1].id)):
                ou = warehouse.l10n_ou_analytic_id
                lines.append(
                    (
                        0,
                        0,
                        {
                            "warehouse_id": warehouse.id,
                            "analytic_account_id": ou.id if ou else False,
                            "product_categ_id": categ.id,
                            "expense_account_id": categ.property_account_expense_categ_id.id,
                            "valuation_account_id": categ.property_stock_valuation_account_id.id,
                            "quantity": bucket["qty"],
                            "zero_cost_qty": bucket["zero_cost_qty"],
                            "amount": bucket["amount"],
                        },
                    )
                )
            run.line_ids = lines
            run.state = "computed"
        return True

    # ------------------------------------------------------------------
    # Journal generation
    # ------------------------------------------------------------------
    def action_generate_move(self):
        self.ensure_one()
        if self.move_id:
            raise UserError(_("A journal entry was already generated."))
        if self.state == "draft":
            self.action_compute()
        currency = self.company_id.currency_id
        label = _("COGS %s", self.name)
        move_lines = []
        for line in self.line_ids:
            if float_is_zero(line.amount, precision_rounding=currency.rounding):
                continue
            if not (line.expense_account_id and line.valuation_account_id):
                raise UserError(
                    _(
                        "Category %(categ)s has no COGS and/or inventory account. Set "
                        "them on the product category before generating the entry.",
                        categ=line.product_categ_id.display_name,
                    )
                )
            # The OU rides on BOTH legs, exactly as the goods-receipt journal
            # does (stock_move._levis_book_valuation_entry), so inventory stays
            # sliceable per store and not just the P&L.
            analytic = {str(line.analytic_account_id.id): 100.0} if line.analytic_account_id else False
            amount = line.amount
            move_lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": line.expense_account_id.id,
                        "name": label,
                        "debit": amount if amount > 0 else 0.0,
                        "credit": -amount if amount < 0 else 0.0,
                        "analytic_distribution": analytic,
                    },
                )
            )
            move_lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": line.valuation_account_id.id,
                        "name": label,
                        "debit": -amount if amount < 0 else 0.0,
                        "credit": amount if amount > 0 else 0.0,
                        "analytic_distribution": analytic,
                    },
                )
            )
        if not move_lines:
            raise UserError(
                _(
                    "Nothing to book — no costed sales in this period. If sales exist, "
                    "their products still carry no cost; load the purchases first."
                )
            )
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal_id.id,
                "company_id": self.company_id.id,
                "date": self.date_to,
                "ref": label,
                "line_ids": move_lines,
            }
        )
        self.move_id = move.id
        self.state = "generated"
        self._record_charges()
        return True

    def _record_charges(self):
        """Write what this run charged into ``levis.cogs.charge``.

        Recomputed rather than derived from the (category-level) run lines: the
        ledger is per product and per sale month, which is the grain a later
        receipt catch-up needs in order not to charge the same unit again.
        """
        self.ensure_one()
        company = self.company_id
        rows = [row for row in self._detail() if row["cost"] and not company.currency_id.is_zero(row["amount"])]
        self.env["levis.cogs.charge"].create(
            [
                {
                    "company_id": company.id,
                    "product_id": row["product"].id,
                    "warehouse_id": row["warehouse"].id,
                    "period_date": row["period_date"],
                    "quantity": row["quantity"],
                    "amount": company.currency_id.round(row["amount"]),
                    "source": "run",
                    "run_id": self.id,
                    "move_id": self.move_id.id,
                }
                for row in rows
            ]
        )

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }


class LevisCogsRunLine(models.Model):
    _name = "levis.cogs.run.line"
    _description = "Periodic COGS Line"
    _order = "warehouse_id, product_categ_id"

    run_id = fields.Many2one("levis.cogs.run", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="run_id.company_id", store=True)
    currency_id = fields.Many2one(related="run_id.currency_id")
    warehouse_id = fields.Many2one("stock.warehouse", required=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit")
    product_categ_id = fields.Many2one("product.category", required=True)
    expense_account_id = fields.Many2one("account.account", string="COGS Account")
    valuation_account_id = fields.Many2one("account.account", string="Inventory Account")
    quantity = fields.Float(digits="Product Unit of Measure")
    zero_cost_qty = fields.Float(digits="Product Unit of Measure", string="Qty Without Cost")
    amount = fields.Monetary(currency_field="currency_id", string="COGS")
