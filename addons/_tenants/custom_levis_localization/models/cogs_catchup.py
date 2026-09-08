# -*- coding: utf-8 -*-
"""COGS catch-up: recognise cost the moment a goods receipt reveals it.

Levi's sells before it buys. At the moment a unit leaves the store the product
often carries no cost at all, and Odoo 19 can no longer repair that afterwards
(see ``cogs_run.py`` for why: ``stock.move.value`` is written once and the FIFO
vacuum is gone). ``levis.cogs.run`` answers this once a month. This model
answers it *as it happens*: when a goods receipt establishes a cost for a
product, whatever was already sold of that product — and never charged to COGS —
is recognised right away.

The contract, deliberately narrow:

* **Only the products on the receipt.** A product that is not being received is
  left alone, however much of it was sold.
* **Only the current month by default.** June and July 2026 were charged by hand
  and by ``COGS/2026/0001`` *without* leaving ledger rows behind, so a catch-up
  that reached back into them would book the cost a second time. The window
  starts at the first day of the booking month unless
  ``custom_levis_localization.cogs_catchup_start`` widens it.
* **The whole outstanding quantity, at the newly-known cost.** Ten sold and four
  received still charges ten: the cost is known now, and a trickle of tail
  entries per later receipt helps nobody.
* **Cost = the purchase price net of tax**, taken from the receipt's own PO line
  (``stock.move.purchase_line_id``) and converted to company currency; the
  product's ``standard_price`` is the fallback. This is the basis the June/July
  reconciliation proved right — ``standard_price`` alone missed Rp 252 m in July.
* **Booked in the month of the sale while that month is open; in the current
  month once it is closed.** "Closed" is the latest of the fiscal-year lock
  date, the hard lock date and the company's own *COGS Reported Through* date —
  the last of which exists because Levi's policy is that a period already
  reported to the client does not move, lock date or not.
* **Draft entries, grouped per booking date**, so the accountant reviews one
  entry per day rather than one per receipt.

Every charge is written to ``levis.cogs.charge``, the ledger of cost already
recognised per (product, store, sale month). ``levis.cogs.run`` subtracts that
ledger before it books, so the monthly run and this catch-up can never charge
the same unit twice — that ledger, not the journal entry, is the real output.
"""

import logging
from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# POS orders that represent a real, settled sale — same set as levis.cogs.run.
_SOLD_STATES = ("paid", "done", "invoiced")

# Widens the catch-up window backwards. A date; empty means "the booking month".
PARAM_START = "custom_levis_localization.cogs_catchup_start"
# Code of the journal the catch-up entries go to. Empty -> the stock journal.
PARAM_JOURNAL = "custom_levis_localization.cogs_catchup_journal_code"

# Arbitrary but FIXED first key of the per-company advisory lock taken while the
# ledger is read and written.
_ADVISORY_LOCK_KEY = 1926051


class LevisCogsCharge(models.Model):
    """Cost already recognised for (product, store, sale month).

    Written by both the catch-up and the periodic run; read by both before they
    book. Rows are cheap and never updated in place, so the table doubles as the
    audit trail of *when* the cost of a given month's sales was recognised.
    """

    _name = "levis.cogs.charge"
    _description = "COGS Already Recognised"
    _order = "period_date desc, id desc"

    company_id = fields.Many2one("res.company", required=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, index=True)
    period_date = fields.Date(
        required=True,
        index=True,
        string="Sale Month",
        help="First day of the month the units were SOLD in — not the month the entry was booked in.",
    )
    quantity = fields.Float(digits="Product Unit of Measure")
    amount = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id")
    source = fields.Selection([("catchup", "Receipt Catch-up"), ("run", "Periodic Run")], required=True)
    catchup_id = fields.Many2one("levis.cogs.catchup", ondelete="set null", index=True)
    run_id = fields.Many2one("levis.cogs.run", ondelete="set null", index=True)
    move_id = fields.Many2one("account.move", ondelete="set null")

    # ------------------------------------------------------------------
    # Period helpers
    # ------------------------------------------------------------------
    @api.model
    def _month_start(self, date):
        return date.replace(day=1)

    @api.model
    def _month_end(self, date):
        return date.replace(day=1) + relativedelta(months=1, days=-1)

    @api.model
    def _months_between(self, date_from, date_to):
        """First day of every month touched by ``[date_from, date_to]``."""
        months = []
        cursor = self._month_start(date_from)
        while cursor <= date_to:
            months.append(cursor)
            cursor += relativedelta(months=1)
        return months

    @api.model
    def _closed_through(self, company):
        """Last date whose numbers must not move any more.

        The company's own *COGS Reported Through* sits alongside the lock dates
        because a period can be reported to the client long before anyone gets
        round to locking it, and Levi's policy is that reported numbers are
        final. Lock *exceptions* are deliberately ignored: they exist to let a
        specific correction through, not to reopen a month for new cost.
        """
        candidates = [
            company.fiscalyear_lock_date,
            getattr(company, "hard_lock_date", False),
            company.l10n_cogs_reported_through,
        ]
        candidates = [d for d in candidates if d]
        return max(candidates) if candidates else False

    @api.model
    def _book_date(self, company, period_date):
        """Where the cost of ``period_date``'s sales may be booked."""
        today = fields.Date.context_today(self)
        month_end = self._month_end(period_date)
        closed_through = self._closed_through(company)
        if closed_through and month_end <= closed_through:
            # The sale month is shut: recognise the cost in the open present.
            # A lock date sitting in the future would block even that, so step
            # past it rather than hand the accountant an unpostable entry.
            return max(today, closed_through + relativedelta(days=1))
        # The month is open — book at its end, but never in the future: the
        # current month's own catch-up belongs on today's date.
        return min(month_end, today)

    # ------------------------------------------------------------------
    # Quantities
    # ------------------------------------------------------------------
    @api.model
    def _pos_configs(self, warehouse):
        return self.env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", warehouse.id)])

    @api.model
    def _sold_quantities(self, company, warehouse, date_from, date_to, products=None):
        """Quantity sold per product at ``warehouse`` between two dates.

        Refund lines carry a negative ``qty`` and net the sale down on their own.
        ``date_order`` is a Datetime, so the bounds are widened to cover the last
        day instead of stopping at its midnight.
        """
        configs = self._pos_configs(warehouse)
        if not configs or (products is not None and not products):
            return {}
        domain = [
            ("order_id.session_id.config_id", "in", configs.ids),
            ("order_id.state", "in", _SOLD_STATES),
            ("order_id.company_id", "=", company.id),
            ("order_id.date_order", ">=", datetime.combine(date_from, time.min)),
            ("order_id.date_order", "<=", datetime.combine(date_to, time.max)),
        ]
        if products is not None:
            domain.append(("product_id", "in", products.ids))
        grouped = self.env["pos.order.line"]._read_group(domain, ["product_id"], ["qty:sum"])
        return {product: qty for product, qty in grouped if qty}

    @api.model
    def _charged_quantities(self, company, warehouse, period_date, products=None):
        """Quantity of ``period_date``'s sales already charged to COGS."""
        domain = [
            ("company_id", "=", company.id),
            ("warehouse_id", "=", warehouse.id),
            ("period_date", "=", period_date),
        ]
        if products is not None:
            if not products:
                return {}
            domain.append(("product_id", "in", products.ids))
        grouped = self._read_group(domain, ["product_id"], ["quantity:sum"])
        return {product: qty for product, qty in grouped if qty}

    @api.model
    def _outstanding(self, company, warehouse, period_date, products=None, date_to=None):
        """Units sold in ``period_date``'s month that carry no COGS yet.

        ``{product: qty}``, positive quantities only — a product whose returns
        outrun its sales has nothing left to charge, and pushing the negative
        into a journal here would credit COGS the accountant never debited.
        """
        month_end = self._month_end(period_date)
        upper = min(month_end, date_to) if date_to else month_end
        if upper < period_date:
            return {}
        sold = self._sold_quantities(company, warehouse, period_date, upper, products=products)
        if not sold:
            return {}
        charged = self._charged_quantities(company, warehouse, period_date, products=products)
        outstanding = {}
        for product, qty in sold.items():
            rest = qty - charged.get(product, 0.0)
            if company.currency_id.compare_amounts(rest, 0.0) > 0:
                outstanding[product] = rest
        return outstanding


class LevisCogsCatchup(models.Model):
    _name = "levis.cogs.catchup"
    _description = "COGS Catch-up from Goods Receipt"
    _order = "book_date desc, id desc"

    name = fields.Char(default="/", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    book_date = fields.Date(required=True, readonly=True, string="Booking Date")
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    line_ids = fields.One2many("levis.cogs.catchup.line", "catchup_id", readonly=True)
    charge_ids = fields.One2many("levis.cogs.charge", "catchup_id", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    total_cogs = fields.Monetary(compute="_compute_total", currency_field="currency_id", store=True)

    @api.depends("line_ids.amount")
    def _compute_total(self):
        for record in self:
            record.total_cogs = sum(record.line_ids.mapped("amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("levis.cogs.catchup") or "/"
        return super().create(vals_list)

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------
    # Entry point (called from stock.move._action_done)
    # ------------------------------------------------------------------
    @api.model
    def _catch_up(self, company, product_costs, origin=None):
        """Recognise the outstanding COGS of ``product_costs``' products.

        ``product_costs`` maps ``product.product`` -> unit cost in company
        currency. Returns the ``levis.cogs.catchup`` records touched.
        """
        Charge = self.env["levis.cogs.charge"]
        currency = company.currency_id
        # Two receipts validated at the same moment would each read the same
        # outstanding quantity and charge it — the retail import validates
        # pickings from parallel queue jobs, so this is not theoretical. One
        # transaction-scoped advisory lock per company serialises the read of
        # the ledger and the write that answers it.
        # (a literal key, not hash(): Python string hashing is salted per process)
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", (_ADVISORY_LOCK_KEY, company.id))
        products = self.env["product.product"].browse(
            [p.id for p, cost in product_costs.items() if p.is_storable and cost and not currency.is_zero(cost)]
        )
        if not products:
            return self.browse()

        today = fields.Date.context_today(self)
        start = self._window_start(today)
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", company.id)])
        # {(book_date, sale month, warehouse, category): {"qty", "amount"}} —
        # the sale month is part of the key, not a payload, because two closed
        # months both book on today's date and must still stay apart on the
        # lines.
        buckets = {}
        charges = []
        for period_date in Charge._months_between(start, today):
            book_date = Charge._book_date(company, period_date)
            for warehouse in warehouses:
                outstanding = Charge._outstanding(company, warehouse, period_date, products=products, date_to=today)
                for product, qty in outstanding.items():
                    cost = product_costs[product]
                    amount = currency.round(qty * cost)
                    if currency.is_zero(amount):
                        continue
                    categ = product.categ_id.with_company(company)
                    bucket = buckets.setdefault((book_date, period_date, warehouse, categ), {"qty": 0.0, "amount": 0.0})
                    bucket["qty"] += qty
                    bucket["amount"] += amount
                    charges.append(
                        {
                            "company_id": company.id,
                            "product_id": product.id,
                            "warehouse_id": warehouse.id,
                            "period_date": period_date,
                            "quantity": qty,
                            "amount": amount,
                            "source": "catchup",
                        }
                    )
        if not buckets:
            return self.browse()

        touched = self.browse()
        for book_date in sorted({key[0] for key in buckets}):
            day_buckets = {key: value for key, value in buckets.items() if key[0] == book_date}
            catchup = self._get_or_create(company, book_date)
            catchup._add_buckets(day_buckets, origin=origin)
            touched |= catchup
            for charge in charges:
                if Charge._book_date(company, charge["period_date"]) != book_date:
                    continue
                charge["catchup_id"] = catchup.id
                charge["move_id"] = catchup.move_id.id
        Charge.create(charges)
        return touched

    @api.model
    def _window_start(self, today):
        """First sale month the catch-up may reach back to."""
        raw = (self.env["ir.config_parameter"].sudo().get_param(PARAM_START) or "").strip()
        if raw:
            try:
                return fields.Date.to_date(raw)
            except (ValueError, TypeError):
                _logger.warning("Ignoring unparseable %s=%r", PARAM_START, raw)
        return today.replace(day=1)

    @api.model
    def _get_or_create(self, company, book_date):
        """One catch-up per booking date — while its entry is still draft.

        Once the accountant posts the day's entry a new one is started rather
        than reopening theirs.
        """
        existing = self.search(
            [
                ("company_id", "=", company.id),
                ("book_date", "=", book_date),
                ("move_id.state", "=", "draft"),
            ],
            limit=1,
        )
        if existing:
            return existing
        return self.create({"company_id": company.id, "book_date": book_date})

    @api.model
    def _journal(self, company):
        code = (self.env["ir.config_parameter"].sudo().get_param(PARAM_JOURNAL) or "").strip()
        Journal = self.env["account.journal"]
        if code:
            journal = Journal.search([("company_id", "=", company.id), ("code", "=", code)], limit=1)
            if journal:
                return journal
            _logger.warning("No journal with code %r in %s; falling back", code, company.display_name)
        return company.account_stock_journal_id or Journal.search(
            [("company_id", "=", company.id), ("type", "=", "general")], limit=1
        )

    def _add_buckets(self, buckets, origin=None):
        """Add the aggregated cost to this catch-up and to its draft entry."""
        self.ensure_one()
        company = self.company_id
        journal = self._journal(company)
        if not journal:
            raise UserError(_("No journal available for the COGS catch-up in %s.", company.display_name))
        lines = []
        move_lines = []
        for (_book_date, period_date, warehouse, categ), bucket in sorted(
            buckets.items(), key=lambda item: (item[0][1], item[0][2].id, item[0][3].id)
        ):
            expense = categ.property_account_expense_categ_id
            valuation = categ.property_stock_valuation_account_id
            if not (expense and valuation):
                raise UserError(
                    _(
                        "Category %(categ)s has no COGS and/or inventory account, so "
                        "the cost of what was already sold cannot be recognised.",
                        categ=categ.display_name,
                    )
                )
            ou = warehouse.l10n_ou_analytic_id
            analytic = {str(ou.id): 100.0} if ou else False
            label = _(
                "COGS catch-up %(month)s%(origin)s",
                month=period_date.strftime("%m/%Y"),
                origin=" — %s" % origin if origin else "",
            )
            amount = bucket["amount"]
            lines.append(
                (
                    0,
                    0,
                    {
                        "period_date": period_date,
                        "warehouse_id": warehouse.id,
                        "analytic_account_id": ou.id if ou else False,
                        "product_categ_id": categ.id,
                        "expense_account_id": expense.id,
                        "valuation_account_id": valuation.id,
                        "quantity": bucket["qty"],
                        "amount": amount,
                    },
                )
            )
            # The Operating Unit rides on BOTH legs, exactly as the goods-receipt
            # journal and the periodic run do, so inventory stays sliceable per
            # store and not just the P&L.
            move_lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": expense.id,
                        "name": label,
                        "debit": amount,
                        "credit": 0.0,
                        "analytic_distribution": analytic,
                    },
                )
            )
            move_lines.append(
                (
                    0,
                    0,
                    {
                        "account_id": valuation.id,
                        "name": label,
                        "debit": 0.0,
                        "credit": amount,
                        "analytic_distribution": analytic,
                    },
                )
            )
        if not move_lines:
            return
        self.line_ids = lines
        if self.move_id:
            self.move_id.write({"line_ids": move_lines})
        else:
            self.move_id = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "company_id": company.id,
                    "date": self.book_date,
                    "ref": _("COGS catch-up %s", self.name),
                    "line_ids": move_lines,
                }
            )
        self.charge_ids.filtered(lambda c: not c.move_id).move_id = self.move_id


class LevisCogsCatchupLine(models.Model):
    _name = "levis.cogs.catchup.line"
    _description = "COGS Catch-up Line"
    _order = "period_date, warehouse_id, product_categ_id"

    catchup_id = fields.Many2one("levis.cogs.catchup", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="catchup_id.company_id", store=True)
    currency_id = fields.Many2one(related="catchup_id.currency_id")
    period_date = fields.Date(string="Sale Month", required=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit")
    product_categ_id = fields.Many2one("product.category", required=True)
    expense_account_id = fields.Many2one("account.account", string="COGS Account")
    valuation_account_id = fields.Many2one("account.account", string="Inventory Account")
    quantity = fields.Float(digits="Product Unit of Measure")
    amount = fields.Monetary(currency_field="currency_id", string="COGS")
