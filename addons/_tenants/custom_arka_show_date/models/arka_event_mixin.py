# -*- coding: utf-8 -*-
"""One event, one analytic account — shared by the sale, purchase and GL side.

ARKA sells a drone show to a customer and buys the show itself from its sister
company AIM. Both legs, plus every vendor bill the two companies raise for the
same night, belong to ONE event. This mixin is what makes "the same event"
mean the same record everywhere:

* ``_custom_event_label()`` builds the event's human name by concatenating the
  event name, its location and the show date::

      Soekarno Cup - Stadion Gelora Bung Tomo Surabaya - 24.08.26

* ``_custom_event_analytic_account()`` resolves that label to a single
  ``account.analytic.account`` in the "Event" plan, creating it on first use.
  Matching is done on a normalised key (``x_custom_event_key``), not on the
  name, because the name is a translatable jsonb column and users retype
  spacing and capitalisation ("MERDEKA RUN - MONAS" vs "Merdeka Run - Monas").

The analytic account is deliberately created with ``company_id = False``.
A per-company account would split one show into two — ARKA's revenue in one
column, AIM's cost in another — and the whole point of the exercise is a P&L
that nets them. Shared analytic accounts are the only cross-company key Odoo
offers.

The mixin carries NO fields: ``x_custom_event_name`` /
``x_custom_event_location`` / ``x_custom_show_date`` are declared on each
inheriting model, because their attributes genuinely differ (the sale order
tracks and copies them, the journal entry does not).
"""

from odoo import _, models
from odoo.exceptions import UserError

EVENT_PLAN_XMLID = "custom_arka_show_date.analytic_plan_arka_event"


def custom_event_key(label):
    """Normalise an event label into its match key.

    Whitespace is collapsed and the case folded away, so the same show typed
    three different ways still lands on one analytic account.
    """
    return " ".join((label or "").split()).upper()


class CustomArkaEventMixin(models.AbstractModel):
    _name = "custom.arka.event.mixin"
    _description = "ARKA event identity (label, analytic account, distribution)"

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def _custom_event_tracking_enabled(self):
        """Gate for the analytic side, separate from the show-date gate.

        ``x_custom_show_date_enabled`` makes the show date REQUIRED on sales
        orders and re-anchors customer-invoice due dates — turning it on for
        AIM would block every AIM order that has no show. Event tracking has
        neither side effect, so it gets its own flag and can be enabled on both
        companies.
        """
        self.ensure_one()
        return bool(self.company_id.x_custom_event_tracking_enabled)

    def _custom_event_values(self):
        """``(name, location, show_date)`` — overridable where they live elsewhere."""
        self.ensure_one()
        return (
            self.x_custom_event_name,
            self.x_custom_event_location,
            self.x_custom_show_date,
        )

    def _custom_event_label(self):
        """ "<event> - <location> - <dd.mm.yy>", skipping whatever is empty.

        Returns "" when nothing at all has been captured, which every caller
        reads as "this document is not attached to an event".
        """
        self.ensure_one()
        name, location, show_date = self._custom_event_values()
        parts = [part.strip() for part in (name, location) if part and part.strip()]
        if show_date:
            # dd.mm.yy — the format the client writes in their own samples, and
            # the one already used in the order-line event block.
            parts.append(show_date.strftime("%d.%m.%y"))
        return " - ".join(parts)

    # ------------------------------------------------------------------
    # Analytic account
    # ------------------------------------------------------------------
    def _custom_event_analytic_account(self, create=True):
        """The one analytic account for this document's event.

        Returns an empty recordset when the document carries no event data, or
        when the Event plan is missing (a half-installed module must not break
        order confirmation).
        """
        self.ensure_one()
        label = self._custom_event_label()
        if not label:
            return self.env["account.analytic.account"]
        key = custom_event_key(label)
        Account = self.env["account.analytic.account"].sudo()
        # active_test=False: an archived event is still that event. Creating a
        # second one would hit the unique key anyway.
        account = Account.with_context(active_test=False).search([("x_custom_event_key", "=", key)], limit=1)
        if account:
            if not account.active:
                account.active = True
            # Self-healing: accounts created before 1.9.0 have no show date, and
            # the overhead allocation selects the events of a period by it.
            _name, _location, show_date = self._custom_event_values()
            if show_date and not account.x_custom_event_show_date:
                account.x_custom_event_show_date = show_date
            return account
        if not create:
            return Account.browse()
        plan = self.env.ref(EVENT_PLAN_XMLID, raise_if_not_found=False)
        if not plan:
            return Account.browse()
        return Account.create(
            {
                "name": label,
                "plan_id": plan.id,
                # Shared on purpose: ARKA's revenue and AIM's cost for one show
                # have to meet on the same analytic account.
                "company_id": False,
                "x_custom_event_key": key,
                "x_custom_event_show_date": self._custom_event_values()[2],
            }
        )

    def _custom_event_analytic_distribution(self, create=True):
        """``{"<analytic account id>": 100.0}`` or False when there is no event."""
        self.ensure_one()
        account = self._custom_event_analytic_account(create=create)
        return {str(account.id): 100.0} if account else False

    # ------------------------------------------------------------------
    # Stamping
    # ------------------------------------------------------------------
    def _custom_event_taggable_lines(self):
        """Lines that should carry the event distribution.

        Every inheriting model implements this: what counts as a costed line
        differs (sale/purchase order lines exclude display lines, a journal
        entry keeps only ``display_type == 'product'``).
        """
        raise NotImplementedError

    def _custom_event_apply_analytic(self, force=False):
        """Write the event distribution onto this document's lines.

        Lines that already carry a distribution are left alone unless ``force``
        — an operator who split a cost across two events by hand must not have
        that work overwritten by the next confirm.

        Returns the distribution written, or False when nothing was done.
        """
        self.ensure_one()
        if not self._custom_event_tracking_enabled():
            return False
        distribution = self._custom_event_analytic_distribution()
        if not distribution:
            return False
        lines = self._custom_event_taggable_lines()
        if not force:
            lines = lines.filtered(lambda line: not line.analytic_distribution)
        if lines:
            lines.analytic_distribution = distribution
        return distribution

    def action_custom_event_apply_analytic(self):
        """Button: tag this document with its event, from the form."""
        for record in self:
            if not record._custom_event_tracking_enabled():
                raise UserError(
                    _(
                        "Event tracking is not enabled on %s. Tick it in Settings ▸ Companies ▸ Event Tracking first.",
                        record.company_id.display_name,
                    )
                )
            if not record._custom_event_label():
                raise UserError(_("Fill in the Event, its location or the Show Date first."))
            record._custom_event_apply_analytic()
        return True
