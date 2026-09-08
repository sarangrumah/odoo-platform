# -*- coding: utf-8 -*-
"""Spread overhead across the events of a period, by a stated rule.

What this is for
----------------
The event chain attributes what a document names: a sales order's revenue, a
purchase order's cost, a bill raised against that order. It cannot attribute
what no document ties to a show — in prd_arkaaim that is payroll, PPh, insurance
and the general journal, some 630 journal items that sit in the **Unassigned**
column of the Profit & Loss per Event and make every event look more profitable
than it was.

Splitting those is a management decision, not an accounting fact: whether August
payroll belongs to Soekarno Cup in proportion to revenue, to direct cost, or in
equal shares is a policy someone has to choose and be able to defend. So this
model does not hold a policy. It holds a **rule** the client writes down —
period, which journals and accounts count as overhead, and the basis — computes
the split, shows it before anything is written, and can put it back.

How the split reaches the report
--------------------------------
Not through a journal entry. ``analytic_distribution`` is a map of analytic
account to percentage, and the Profit & Loss per Event already weights by that
percentage, so one overhead line of Rp 100 juta can carry ``{Soekarno: 60,
Merdeka: 40}`` and show up as 60 and 40 juta in the two columns. No amount
moves, no account changes, nothing is re-posted: the allocation is a reading of
the same ledger, which is exactly what an allocation should be.

Rules it keeps
--------------
* **A line already attributed is never touched.** A distribution set by the
  event chain, by the backfill, or by hand is direct attribution — overhead is
  by definition what is left.
* **Only expense lines.** Allocating a bank or payable line to a show is
  meaningless; the source set is restricted to expense accounts.
* **Reversible, exactly.** Every line written carries
  ``x_custom_event_allocation_id``, so Reset puts back precisely what this run
  changed and nothing else. Re-run after changing the basis and the numbers
  simply move.
* **Posted entries only.** An allocation is a period-close activity; a draft
  bill that posts later is picked up by the next run.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .arka_event_mixin import EVENT_PLAN_XMLID


class CustomArkaEventAllocation(models.Model):
    _name = "custom.arka.event.allocation"
    _description = "Overhead allocation to events"
    _order = "date_to desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Overhead allocation"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, readonly=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    basis = fields.Selection(
        [
            ("revenue", "Share of event revenue"),
            ("direct_cost", "Share of directly attributed cost"),
            ("equal", "Equal share per event"),
            ("manual", "Percentages typed by hand"),
        ],
        required=True,
        default="revenue",
        help="How the overhead is divided between the events of the period. "
        "Revenue and direct cost read what the event chain has already "
        "attributed; equal ignores size; manual leaves it to you.",
    )
    journal_ids = fields.Many2many(
        "account.journal",
        string="Journals",
        help="Which journals hold the overhead. Leave empty for all of them.",
    )
    account_ids = fields.Many2many(
        "account.account",
        string="Accounts",
        help="Narrow the overhead further. Leave empty for every expense account.",
    )
    line_ids = fields.One2many("custom.arka.event.allocation.line", "allocation_id", string="Events")
    state = fields.Selection([("draft", "Draft"), ("applied", "Applied")], default="draft", readonly=True, copy=False)
    allocated_line_count = fields.Integer(compute="_compute_allocated", string="Lines allocated")
    allocated_amount = fields.Monetary(compute="_compute_allocated", string="Amount allocated")
    source_line_count = fields.Integer(compute="_compute_source", string="Overhead lines")
    source_amount = fields.Monetary(compute="_compute_source", string="Overhead amount")
    currency_id = fields.Many2one(related="company_id.currency_id")

    # ------------------------------------------------------------------
    # What counts as overhead
    # ------------------------------------------------------------------
    def _source_domain(self, include_own=True):
        """Posted expense lines of the period that nothing has attributed yet.

        ``include_own`` keeps this run's own lines in view, so Reset and a
        re-run see what they wrote; a second allocation never sees them as
        free.
        """
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("parent_state", "=", "posted"),
            ("display_type", "=", "product"),
            ("account_id.account_type", "like", "expense%"),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.account_ids:
            domain.append(("account_id", "in", self.account_ids.ids))
        saved_id = self._origin.id
        if include_own and saved_id:
            domain += [
                "|",
                ("analytic_distribution", "=", False),
                ("x_custom_event_allocation_id", "=", saved_id),
            ]
        else:
            domain.append(("analytic_distribution", "=", False))
        return domain

    def _source_lines(self, include_own=True):
        self.ensure_one()
        return self.env["account.move.line"].search(self._source_domain(include_own=include_own))

    @api.depends("date_from", "date_to", "journal_ids", "account_ids", "company_id", "state")
    def _compute_source(self):
        for allocation in self:
            lines = allocation._source_lines() if allocation.date_from and allocation.date_to else None
            allocation.source_line_count = len(lines) if lines is not None else 0
            allocation.source_amount = sum(lines.mapped("balance")) if lines is not None else 0.0

    @api.depends("state")
    def _compute_allocated(self):
        for allocation in self:
            # An unsaved record has a NewId, which is not something to search on.
            saved_id = allocation._origin.id
            lines = (
                self.env["account.move.line"].search([("x_custom_event_allocation_id", "=", saved_id)])
                if saved_id
                else self.env["account.move.line"]
            )
            allocation.allocated_line_count = len(lines)
            allocation.allocated_amount = sum(lines.mapped("balance"))

    # ------------------------------------------------------------------
    # Which events share it
    # ------------------------------------------------------------------
    def _events(self):
        """Events whose show falls inside the period."""
        self.ensure_one()
        plan = self.env.ref(EVENT_PLAN_XMLID, raise_if_not_found=False)
        if not plan:
            return self.env["account.analytic.account"]
        return self.env["account.analytic.account"].search(
            [
                ("plan_id", "=", plan.id),
                ("x_custom_event_show_date", ">=", self.date_from),
                ("x_custom_event_show_date", "<=", self.date_to),
            ],
            order="x_custom_event_show_date, id",
        )

    def _basis_amounts(self, events):
        """``{analytic_id: weight}`` — what the chosen basis measures per event.

        Both money bases read only what the event chain attributed directly:
        allocated lines are excluded, or an allocation would feed on its own
        output and the second run would differ from the first.
        """
        self.ensure_one()
        if self.basis == "equal":
            return {event.id: 1.0 for event in events}
        if self.basis == "manual":
            return {line.analytic_account_id.id: line.percentage for line in self.line_ids}

        account_type = "income%" if self.basis == "revenue" else "expense%"
        sign = -1.0 if self.basis == "revenue" else 1.0
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT part.analytic_id::int AS analytic_id,
                   COALESCE(SUM(aml.balance * kv.value::numeric / 100.0), 0.0) AS amount
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             CROSS JOIN LATERAL jsonb_each_text(aml.analytic_distribution) AS kv(key, value)
             CROSS JOIN LATERAL unnest(string_to_array(kv.key, ',')) AS part(analytic_id)
             WHERE aml.company_id = %s
               AND aml.date >= %s AND aml.date <= %s
               AND aml.parent_state = 'posted'
               AND acc.account_type LIKE %s
               AND aml.x_custom_event_allocation_id IS NULL
               AND part.analytic_id ~ '^[0-9]+$'
               AND part.analytic_id::int IN %s
             GROUP BY 1
            """,
            (self.company_id.id, self.date_from, self.date_to, account_type, tuple(events.ids) or (0,)),
        )
        amounts = {row[0]: sign * float(row[1]) for row in self.env.cr.fetchall()}
        # A negative weight (a credit note bigger than the sales it corrects)
        # cannot take a share of overhead; treat it as nothing.
        return {event.id: max(amounts.get(event.id, 0.0), 0.0) for event in events}

    @staticmethod
    def _percentages(weights):
        """Weights to percentages summing to exactly 100, largest remainder first.

        Two decimals, because that is what an analytic distribution stores. The
        naive round() leaves 99.99 or 100.01, and a percentage that does not sum
        to 100 silently loses or invents overhead.
        """
        total = sum(weights.values())
        if not total:
            return {}
        exact = {key: value * 100.0 / total for key, value in weights.items() if value}
        floored = {key: int(value * 100) for key, value in exact.items()}  # hundredths
        remainder = 10000 - sum(floored.values())
        for key in sorted(exact, key=lambda k: (exact[k] * 100) - floored[k], reverse=True):
            if remainder <= 0:
                break
            floored[key] += 1
            remainder -= 1
        return {key: value / 100.0 for key, value in floored.items() if value}

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_compute(self):
        """Work out each event's share and show it, without writing anything."""
        for allocation in self:
            if allocation.state != "draft":
                raise UserError(_("Reset %s before computing it again.", allocation.display_name))
            if allocation.date_from > allocation.date_to:
                raise UserError(_("The period ends before it starts."))
            events = allocation._events()
            if not events:
                raise UserError(
                    _(
                        "No event has a show date between %(start)s and %(end)s, so there is "
                        "nothing to spread the overhead over.",
                        start=allocation.date_from,
                        end=allocation.date_to,
                    )
                )
            if allocation.basis == "manual":
                # Keep what was typed; only normalise it so it adds up.
                weights = {line.analytic_account_id.id: line.percentage for line in allocation.line_ids}
                if not any(weights.values()):
                    raise UserError(_("Type a percentage for at least one event first."))
            else:
                weights = allocation._basis_amounts(events)
                if not any(weights.values()):
                    raise UserError(
                        _(
                            "The chosen basis measures zero for every event in this period — "
                            "nothing has been attributed to them yet. Pick 'Equal share per "
                            "event', or type the percentages by hand."
                        )
                    )
            percentages = allocation._percentages(weights)
            allocation.line_ids = [(5, 0, 0)] + [
                (
                    0,
                    0,
                    {
                        "analytic_account_id": analytic_id,
                        "percentage": percentage,
                        "basis_amount": weights.get(analytic_id, 0.0),
                    },
                )
                for analytic_id, percentage in percentages.items()
            ]
        return True

    def action_apply(self):
        """Write the computed split onto the overhead lines."""
        for allocation in self:
            if allocation.state != "draft":
                raise UserError(_("%s is already applied.", allocation.display_name))
            if not allocation.line_ids:
                raise UserError(_("Compute the split first."))
            distribution = {
                str(line.analytic_account_id.id): line.percentage for line in allocation.line_ids if line.percentage
            }
            if not distribution:
                raise UserError(_("Every event has a zero share; there is nothing to allocate."))
            lines = allocation._source_lines(include_own=False)
            if not lines:
                raise UserError(_("No unattributed expense line in this period matches the filters."))
            lines.write(
                {
                    "analytic_distribution": distribution,
                    "x_custom_event_allocation_id": allocation.id,
                }
            )
            allocation.state = "applied"
        return True

    def action_reset(self):
        """Take back exactly what this allocation wrote."""
        for allocation in self:
            lines = self.env["account.move.line"].search([("x_custom_event_allocation_id", "=", allocation.id)])
            if lines:
                lines.write({"analytic_distribution": False, "x_custom_event_allocation_id": False})
            allocation.state = "draft"
        return True

    def action_view_allocated_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocated journal items"),
            "res_model": "account.move.line",
            "domain": [("x_custom_event_allocation_id", "=", self.id)],
            "view_mode": "list,form",
        }


class CustomArkaEventAllocationLine(models.Model):
    _name = "custom.arka.event.allocation.line"
    _description = "Overhead allocation share of one event"
    _order = "percentage desc, id"

    allocation_id = fields.Many2one("custom.arka.event.allocation", required=True, ondelete="cascade")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Event", required=True)
    percentage = fields.Float(digits=(5, 2), help="Share of the overhead this event carries.")
    basis_amount = fields.Monetary(
        string="Basis", help="What the chosen basis measured for this event. Zero for an equal split."
    )
    currency_id = fields.Many2one(related="allocation_id.currency_id")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    x_custom_event_allocation_id = fields.Many2one(
        "custom.arka.event.allocation",
        string="Event Allocation",
        readonly=True,
        copy=False,
        index="btree_not_null",
        help="Set when this line's analytic distribution came from an overhead "
        "allocation rather than from a document. It is what makes the "
        "allocation reversible, and it keeps allocated cost out of the basis "
        "of the next allocation.",
    )
