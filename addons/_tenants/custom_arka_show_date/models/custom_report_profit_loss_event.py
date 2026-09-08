# -*- coding: utf-8 -*-
"""Profit & Loss split per Event (the analytic reading).

The sibling *per Show* report keys its columns on ``account.move.x_custom_show_date``,
which is a date: two shows on the same night collapse into one column, and a
cost with no source document has nowhere to go. This variant keys on the
analytic account instead — one per event, named "<event> - <location> -
<dd.mm.yy>" and created by ``custom.arka.event.mixin`` — so:

* two events on the same date stay apart;
* anything an operator can tag with an analytic account (an allocation, an
  overhead journal entry) can be booked to an event, not just documents that
  carry a show date;
* because the event analytic account is created WITHOUT a company, selecting
  both sister companies gives ARKA's revenue and AIM's cost for one show in a
  single column — the cross-company P&L per event.

The machinery is inherited wholesale from the *branch* (Operating Unit) variant
in ``custom_accounting_reports``: it already pivots per analytic account and
already reads the ``analytic_distribution`` JSONB. Only the plan the columns
come from is different, so all this class does is point ``_branch_plan()`` at
the Event plan and rename the residual column.

Screen + XLSX only, like the other pivoted variants — dynamic columns do not
fit a static PDF.
"""

from odoo import models

from .arka_event_mixin import EVENT_PLAN_XMLID


class CustomReportProfitLossEvent(models.AbstractModel):
    _name = "custom.report.profit.loss.event"
    _inherit = "custom.report.profit.loss.branch"
    _description = "Custom Profit & Loss per Event"

    _report_code = "profit_loss_event"
    _report_title = "Profit & Loss per Event"

    def _branch_plan(self):
        """The Event plan, not the tenant's Operating Unit plan."""
        return self.env.ref(EVENT_PLAN_XMLID, raise_if_not_found=False) or self.env["account.analytic.plan"].browse()

    def _head_office_analytic(self):
        """No head office here: the residual column is everything untagged."""
        return None

    def _branch_columns(self):
        columns = super()._branch_columns()
        # The parent labels the residual column "Head Quarter". Here it holds
        # every line not attached to an event, which is the attribution gap
        # Finance is looking for — say so.
        if columns and columns[0][0] == self.HQ_KEY:
            columns[0] = (self.HQ_KEY, "Unassigned", None)
        return columns
