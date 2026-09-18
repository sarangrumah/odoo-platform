# -*- coding: utf-8 -*-
"""Operating-Unit stamping on the POS session closing entry (feature #9).

A POS session belongs to exactly one store (``config_id.warehouse_id``), so every
line of its closing entry belongs to that store's Operating Unit. Core builds
those lines without any analytic distribution, which left the whole POS stream
outside the per-OU reporting.

Every line core produces is stamped: the sale lines (Gross Sales), the tax lines
(VAT Out) and the receivable lines (per-tender receivable, or the POS Suspense
Clearing account in the retail-import decouple flow). Finance reads the OU
dimension off the whole entry, not just its P&L half, so a VAT or suspense line
without a distribution shows up as an unallocated hole when the entry is sliced
per store.

The distribution is merged through the same helper the purchase side uses, so the
OU is appended to its own analytic plan rather than replacing any distribution
core may have derived from the product.
"""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

# Sheet #16: COGS must ride the daily sales journal, per store, per day.
# Empty means OFF — this touches the entry the retail import posts every day,
# so it does not switch itself on.
SESSION_COGS_START_PARAM = "custom_levis_localization.cogs_session_start"


class PosSession(models.Model):
    _inherit = "pos.session"

    def _levis_ou_analytic(self):
        """Operating-Unit analytic of this session's store, if any."""
        self.ensure_one()
        return self.config_id.warehouse_id.l10n_ou_analytic_id

    def _levis_stamp_ou(self, vals):
        """Merge this session's Operating Unit into one closing-entry line's vals."""
        ou = self._levis_ou_analytic()
        if not ou or not vals:
            return vals
        vals["l10n_ou_analytic_id"] = ou.id
        # Set the distribution explicitly rather than leaning on the
        # ``l10n_ou_analytic_id`` trigger: ``analytic_distribution`` is a stored
        # computed field with readonly=False, so a value supplied at create time
        # wins and the result stays deterministic. It also reaches lines whose
        # ``display_type`` ('tax', 'payment_term') the m2o trigger skips.
        vals["analytic_distribution"] = self.env["purchase.order.line"]._levis_merge_ou_distribution(
            vals.get("analytic_distribution"), ou.id
        )
        return vals

    def _get_sale_vals(self, key, sale_vals):
        return self._levis_stamp_ou(super()._get_sale_vals(key, sale_vals))

    def _get_tax_vals(self, key, amount, amount_converted, base_amount_converted):
        return self._levis_stamp_ou(super()._get_tax_vals(key, amount, amount_converted, base_amount_converted))

    def _get_combine_receivable_vals(self, payment_method, amount, amount_converted):
        return self._levis_stamp_ou(super()._get_combine_receivable_vals(payment_method, amount, amount_converted))

    def _get_split_receivable_vals(self, payment, amount, amount_converted):
        return self._levis_stamp_ou(super()._get_split_receivable_vals(payment, amount, amount_converted))

    # ------------------------------------------------------------------
    # Feature 27 — COGS inside the session's own closing entry (sheet #16)
    # ------------------------------------------------------------------
    # The client reopened #16 twice: *"COGS yang di-compute oleh Odoo in total
    # sesuai dengan Report Sales Detail Juni-Agustus, namun line GL COGS belum
    # melekat ke masing-masing jurnal Sales"*. The totals were never the
    # problem; the attachment was.
    #
    # A session is one store on one day, so its closing entry is exactly the
    # document the COGS belongs on. ``custom_retail_import_pos`` already proves
    # the insertion point: ``_create_account_move`` runs while ``move_id`` is
    # still draft and under ``check_move_validity=False``, so a balanced pair
    # can be appended and ``_check_balanced`` still passes afterwards.
    #
    # 🔴 Three things make this safe rather than clever:
    #
    # 1. **A cutover date is mandatory.** June-August 2026 were already booked
    #    by ``COGS/2026/0001..0003``, and charging them again is the one
    #    unrecoverable mistake here. The parameter is empty by default, so the
    #    hook does nothing until somebody names a date.
    # 2. **Every charged unit is written to ``levis.cogs.charge``.** That ledger,
    #    not the journal, is what stops the monthly run and the receipt catch-up
    #    from charging the same unit again — see Feature 23.
    # 3. **Failure never blocks the close.** The retail import closes sessions in
    #    bulk; a COGS problem must not hold up the day's sales. The block logs
    #    and gets out of the way, exactly as ``stock_move.py`` does for receipts.
    def _levis_session_cogs_start(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(SESSION_COGS_START_PARAM, "")
        return fields.Date.to_date(raw.strip()) if raw and raw.strip() else None

    def _levis_session_cogs_vals(self):
        """``(line vals, charge vals)`` for this session's COGS, or ``([], [])``.

        Grouped by product category, because one session must not grow hundreds
        of journal lines. Products whose cost is still unknown are skipped in
        silence and left to the receipt catch-up — booking zero would put a
        meaningless line on the entry and, worse, write a charge row claiming
        the unit had been costed.
        """
        self.ensure_one()
        start = self._levis_session_cogs_start()
        if not start:
            return [], []
        company = self.company_id or self.env.company
        sale_date = fields.Date.to_date(self.stop_at or self.start_at) or fields.Date.context_today(self)
        if sale_date < start:
            return [], []

        warehouse = self.config_id.warehouse_id
        if not warehouse:
            return [], []

        quantities = {}
        for line in self.order_ids.filtered(lambda o: o.state in ("paid", "done", "invoiced")).mapped("lines"):
            product = line.product_id
            if not product or not product.is_storable:
                continue
            quantities[product] = quantities.get(product, 0.0) + (line.qty or 0.0)
        if not quantities:
            return [], []

        Charge = self.env["levis.cogs.charge"]
        period_date = Charge._month_start(sale_date)
        already = Charge._charged_quantities(company, warehouse, period_date, products=None)
        distribution = None
        ou = self._levis_ou_analytic()
        if ou:
            distribution = self.env["purchase.order.line"]._levis_merge_ou_distribution(None, ou.id)

        currency = company.currency_id
        buckets = {}
        charges = []
        for product, qty in quantities.items():
            remaining = qty - already.get(product, 0.0)
            if currency.is_zero(remaining) or remaining <= 0:
                continue
            cost = product.with_company(company).standard_price
            if not cost:
                continue  # the receipt catch-up owns this unit
            categ = product.categ_id.with_company(company)
            expense = categ.property_account_expense_categ_id
            valuation = categ.property_stock_valuation_account_id
            if not expense or not valuation:
                _logger.warning(
                    "levis: session %s — category %s has no COGS/inventory account, %s units not charged",
                    self.id,
                    categ.display_name,
                    remaining,
                )
                continue
            amount = currency.round(remaining * cost)
            if currency.is_zero(amount):
                continue
            bucket = buckets.setdefault((expense.id, valuation.id), 0.0)
            buckets[(expense.id, valuation.id)] = bucket + amount
            charges.append(
                {
                    "company_id": company.id,
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "period_date": period_date,
                    "quantity": remaining,
                    "amount": amount,
                    "source": "session",
                }
            )

        line_vals = []
        label = self.env._("COGS %s", self.name or self.config_id.name)
        for (expense_id, valuation_id), amount in buckets.items():
            for account_id, debit, credit in ((expense_id, amount, 0.0), (valuation_id, 0.0, amount)):
                vals = {
                    "move_id": self.move_id.id,
                    "name": label,
                    "account_id": account_id,
                    "debit": debit,
                    "credit": credit,
                }
                if distribution:
                    vals["analytic_distribution"] = dict(distribution)
                line_vals.append(vals)
        return line_vals, charges

    def _create_account_move(self, *args, **kwargs):
        data = super()._create_account_move(*args, **kwargs)
        for session in self:
            try:
                line_vals, charges = session._levis_session_cogs_vals()
                if not line_vals:
                    continue
                self.env["account.move.line"].with_context(check_move_validity=False).create(line_vals)
                if charges:
                    self.env["levis.cogs.charge"].create(
                        [dict(charge, move_id=session.move_id.id) for charge in charges]
                    )
                _logger.info(
                    "levis: session %s booked COGS on %s — %s line(s), %s charge row(s)",
                    session.id,
                    session.move_id.name or session.move_id.id,
                    len(line_vals),
                    len(charges),
                )
            except Exception:  # noqa: BLE001
                # The retail import closes sessions in bulk; the day's sales must
                # not be held up by a COGS problem.
                _logger.exception("levis: COGS on session %s failed; the session is unaffected", session.id)
        return data
