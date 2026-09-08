# -*- coding: utf-8 -*-
"""Charge the cost of a show out of inventory when its revenue is recognised.

Why there is anything to charge out
-----------------------------------
ARKA buys a drone show's operating cost -- Legal & Compliance, Accommodation,
Logistics, Documentation, Consumption -- on purchase orders, and since
``custom_arka_aim_purchase_type`` 19.0.1.1.0 the goods receipt books it::

    Dr Inventory-Others        Cr GR/IR clearing

That is right for the moment the goods arrive, and wrong the moment the show is
over: the cost of a show that has already been performed and invoiced is not an
asset. Left alone, the inventory account would grow by every show ARKA ever
runs and the P&L per Event would report revenue against no cost at all.

When it fires
-------------
When the event's revenue is recognised — the accounting choice the client made,
so cost meets revenue in the same period. In practice that is the customer
invoice posting, because at ARKA a down payment is booked to a liability account
and recognises nothing (see ``custom_arka_aim_purchase_type`` and the tenant's
down-payment wiring), so the first entry that credits an income account for an
event IS its revenue.

The hook sits on ``account.move._post`` and looks at the events a move touches,
which covers the two cases with one rule — *an event whose revenue is recognised
carries no inventory*:

* the customer invoice posts -> everything accrued for that show so far is
  charged out;
* a goods receipt posts LATE, after the invoice -> its own posting re-checks the
  event, finds the revenue already recognised, and charges the late cost out
  immediately instead of stranding it.

What it posts
-------------
Per company and per inventory account carrying a balance for the event::

    Dr Cost of Goods Sold      Cr Inventory-Others

in the stock journal, dated on the move that triggered it (so the cost lands in
the period of the revenue), carrying the event's analytic distribution on both
legs so the Profit & Loss per Event sees it.

No state is kept, and that is deliberate. Every run recomputes what is still
sitting on the inventory accounts for that event, and the entry it posts credits
those same accounts with the same analytic — so the remaining balance falls to
zero by construction. Re-running charges nothing twice, a cost that arrives
later is picked up in full, and a reversal simply reappears as a balance to
charge out again. There is no register to drift.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Expense account CODES, tried in order, per company. Used when the categories
# behind an inventory account do not agree on one expense account of their own
# (on ARKA-AIM most carry none). prd_arkaaim runs the Erajaya chart, trn_arkaaim
# the plain Indonesian one. Overridable per database with the ir.config_parameter
# below, as a comma-separated list.
EXPENSE_CODE_PARAM = "custom_arka_show_date.event_chargeout_expense_codes"
DEFAULT_EXPENSE_CODES = ("6199000000", "51000010")

# Set on the context while the charge-out posts its own entry, so posting that
# entry cannot re-enter the hook.
CHARGEOUT_CTX = "custom_arka_event_chargeout"


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    # ------------------------------------------------------------------
    # Reading the ledger
    # ------------------------------------------------------------------
    def _custom_event_amounts(self, company, account_ids=None, account_type=None):
        """``{account_id: balance}`` carried by this event, weighted by percentage.

        One of ``account_ids`` / ``account_type`` selects the accounts. The
        weighting matters: an analytic distribution of ``{Soekarno: 60, Merdeka:
        40}`` puts only 60% of the line on this event, and the charge-out must
        move exactly what the event was charged, no more.
        """
        self.ensure_one()
        if not (account_ids or account_type):
            return {}
        where = "acc.id IN %s" if account_ids else "acc.account_type LIKE %s"
        selector = (tuple(account_ids) or (0,)) if account_ids else account_type
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT aml.account_id,
                   COALESCE(SUM(aml.balance * kv.value::numeric / 100.0), 0.0)
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             CROSS JOIN LATERAL jsonb_each_text(aml.analytic_distribution) AS kv(key, value)
             CROSS JOIN LATERAL unnest(string_to_array(kv.key, ',')) AS part(analytic_id)
             WHERE aml.company_id = %s
               AND aml.parent_state = 'posted'
               AND part.analytic_id ~ '^[0-9]+$'
               AND part.analytic_id::int = %s
               AND """
            + where
            + """
             GROUP BY 1
            """,
            (company.id, self.id, selector),
        )
        return {row[0]: float(row[1]) for row in self.env.cr.fetchall()}

    def _custom_event_revenue_recognised(self, company):
        """True once this event has booked revenue in ``company``.

        Income accounts are credited, so a recognised event shows a NEGATIVE
        balance; the sign is flipped here to read as revenue. A credit note that
        wipes the invoice out takes the event back to nothing recognised, which
        is the honest answer — its cost belongs back in inventory until it is
        re-invoiced.
        """
        self.ensure_one()
        amounts = self._custom_event_amounts(company, account_type="income%")
        revenue = -sum(amounts.values())
        return company.currency_id.compare_amounts(revenue, 0.0) > 0

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    @api.model
    def _custom_event_inventory_accounts(self, company):
        """``{inventory account: expense account}`` for ``company``.

        Model-level on purpose: the mapping is a property of the company's
        configuration, not of any one event, and the reporting script has to be
        able to show it on a database that has no event yet.

        The inventory accounts are exactly the valuation accounts of the
        real-time categories — the accounts the goods receipt debits — so the
        same ``real_time`` switch that turns the GR journal on turns this on,
        category by category, with nothing else to configure.

        The expense account is the categories' own, when the categories sharing
        an inventory account agree on one. They usually do not (on ARKA-AIM most
        carry none at all), so the fallback is the first code of
        ``EXPENSE_CODE_PARAM`` present in the company's chart.
        """
        categories = self.env["product.category"].sudo().search([])
        pairs = {}
        for categ in categories:
            categ = categ.with_company(company)
            if categ.property_valuation != "real_time":
                continue
            inventory = categ.property_stock_valuation_account_id
            if not inventory:
                continue
            pairs.setdefault(inventory, set()).add(categ.property_account_expense_categ_id)
        fallback = self._custom_event_expense_fallback(company)
        result = {}
        for inventory, expenses in pairs.items():
            expenses.discard(self.env["account.account"].browse())
            expense = expenses.pop() if len(expenses) == 1 else self.env["account.account"].browse()
            result[inventory] = expense or fallback
        return result

    @api.model
    def _custom_event_expense_fallback(self, company):
        """First configured expense code present in ``company``'s chart."""
        param = self.env["ir.config_parameter"].sudo().get_param(EXPENSE_CODE_PARAM, "")
        codes = [code.strip() for code in param.split(",") if code.strip()] or list(DEFAULT_EXPENSE_CODES)
        Account = self.env["account.account"].sudo()
        for code in codes:
            account = Account.with_company(company).search(
                [("code", "=", code), ("company_ids", "in", company.id)], limit=1
            )
            if account:
                return account
        return Account.browse()

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------
    def _custom_event_chargeout(self, company, date=None, dry_run=False):
        """Move this event's remaining inventory balance to expense.

        Returns the entry posted, or an empty recordset when there was nothing
        to charge (the usual case: an event already flat, or one whose revenue
        is not recognised yet). ``dry_run`` returns the ``{inventory: amount}``
        it would move instead, for the reporting script.
        """
        self.ensure_one()
        currency = company.currency_id
        pairs = self.env["account.analytic.account"]._custom_event_inventory_accounts(company)
        if not pairs:
            return {} if dry_run else self.env["account.move"].browse()
        balances = self._custom_event_amounts(company, account_ids=[acc.id for acc in pairs])
        moves = {
            inventory: balances.get(inventory.id, 0.0)
            for inventory in pairs
            if not currency.is_zero(balances.get(inventory.id, 0.0))
        }
        # A negative balance means more has been charged out than was ever
        # accrued -- a corrected receipt, a reversal. Charging that "back in"
        # would invent an asset, so only a positive balance is moved.
        moves = {inv: amount for inv, amount in moves.items() if amount > 0}
        if dry_run:
            return moves
        if not moves:
            return self.env["account.move"].browse()

        journal = company.account_stock_journal_id or self.env["account.journal"].sudo().search(
            [("company_id", "=", company.id), ("type", "=", "general")], limit=1
        )
        if not journal:
            _logger.info("ARKA event charge-out: company %s has no journal, event %s skipped", company.id, self.id)
            return self.env["account.move"].browse()

        label = _("Show cost %(event)s", event=self.name or "")
        analytic = {str(self.id): 100.0}
        line_ids = []
        for inventory, amount in moves.items():
            expense = pairs[inventory]
            if not expense:
                _logger.info(
                    "ARKA event charge-out: no expense account for inventory %s in company %s, event %s skipped",
                    inventory.id,
                    company.id,
                    self.id,
                )
                return self.env["account.move"].browse()
            amount = currency.round(amount)
            common = {"name": label, "analytic_distribution": analytic}
            line_ids.append((0, 0, dict(common, account_id=expense.id, debit=amount, credit=0.0)))
            line_ids.append((0, 0, dict(common, account_id=inventory.id, debit=0.0, credit=amount)))

        entry = (
            self.env["account.move"]
            .sudo()
            .with_context(**{CHARGEOUT_CTX: True})
            .create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "company_id": company.id,
                    "date": date or fields.Date.context_today(self),
                    "ref": "ARKA-SHOWCOST:%s" % self.id,
                    "line_ids": line_ids,
                }
            )
        )
        entry._post(soft=False)
        _logger.info(
            "ARKA event charge-out: event %s company %s -> entry %s (%s)",
            self.id,
            company.id,
            entry.id,
            sum(moves.values()),
        )
        return entry


class AccountMove(models.Model):
    _inherit = "account.move"

    def _custom_event_analytics(self):
        """Event analytic accounts this move's lines are distributed to."""
        plan = self.env.ref("custom_arka_show_date.analytic_plan_arka_event", raise_if_not_found=False)
        ids = set()
        for line in self.line_ids:
            for key in line.analytic_distribution or {}:
                for part in str(key).split(","):
                    if part.isdigit():
                        ids.add(int(part))
        accounts = self.env["account.analytic.account"].sudo().browse(sorted(ids)).exists()
        if plan:
            accounts = accounts.filtered(lambda a: a.plan_id == plan)
        return accounts

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._custom_event_chargeout_touched()
        return posted

    def _custom_event_chargeout_touched(self):
        """Flush the inventory of every event this batch of moves touched.

        Deliberately driven off the moves that just posted rather than off a
        cron: the trigger IS the posting, whether it was the invoice that
        recognised the revenue or a receipt that arrived after it.
        """
        if self.env.context.get(CHARGEOUT_CTX):
            return  # our own entry posting — do not re-enter
        for move in self:
            company = move.company_id
            if not company.x_custom_event_tracking_enabled:
                continue
            for event in move._custom_event_analytics():
                if not event._custom_event_revenue_recognised(company):
                    continue
                event._custom_event_chargeout(company, date=move.date)
