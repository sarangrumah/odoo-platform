# -*- coding: utf-8 -*-
"""What a Levi's statement line should be offered to match against.

The generic scorer in ``custom_account_reconcile`` looks for a journal item whose
residual equals the statement amount. On this tenant that almost never happens,
for two reasons that have nothing to do with data quality:

* **A card settlement arrives net.** The acquirer bills the customer 4 722 112,
  keeps 32 756 and transfers 4 689 356; the POS receivable is booked at the
  gross. So the amount to look for is not ``amount`` but ``amount + MDR``, and
  the MDR is printed on the very same narrative.
* **A cash deposit is one transfer for several days.** Nothing in the ledger has
  that total; it is a sum of daily cash receivables and must be assembled.

Both need the store first, and the store is not in the amount — it comes from the
merchant id via ``levis.bank.mid.map``, already resolved onto the line by
``custom_levis_localization``. Once the Operating Unit is known the pool is
small and honest: that store's open tender receivables, around that trading day.

When the line is not a Levi's settlement — an unmapped merchant, a bank charge,
a feed with no narrative grammar — this falls straight through to the generic
scorer. A guess is never manufactured out of a narrative that was not understood.
"""

from datetime import timedelta

from odoo import models

# How far either side of the assumed trading day the receivable may sit. A
# settlement early in the month pays for sales made in the previous one, and the
# 1 484 July lines that carry no transaction date have to be placed by lag alone.
_DAY_WINDOW_BEFORE = 12
_DAY_WINDOW_AFTER = 3

_LEVIS_KINDS = ("settlement", "cash_deposit")


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    # ------------------------------------------------------------------
    # Levi's view of the line
    # ------------------------------------------------------------------
    def _levis_clearing_config(self):
        """The tenant's clearing accounts, or empty when not configured."""
        self.ensure_one()
        Config = self.env.get("levis.clearing.config")
        if Config is None:
            return self.env["levis.clearing.config"].browse()
        return Config.sudo().search([("company_id", "=", self.company_id.id)], limit=1)

    def _levis_is_tender_line(self):
        """True when this line is a POS settlement we know the store of."""
        self.ensure_one()
        return bool(self.levis_narrative_kind in _LEVIS_KINDS and self.levis_ou_analytic_id and self.amount > 0)

    def _levis_match_target(self):
        """The amount the selected journal items should add up to.

        Gross for a card settlement (the fee is booked separately), the deposit
        itself for cash. Falls back to the statement amount whenever the
        narrative was not read — an unparsed MDR is never assumed to be zero.
        """
        self.ensure_one()
        if self.levis_narrative_kind == "settlement" and self.levis_gross:
            return self.levis_gross
        return abs(self.amount)

    def _levis_tender_accounts(self):
        """Receivable accounts a POS session splits its tenders into."""
        self.ensure_one()
        config = self._levis_clearing_config()
        accounts = config.pos_receivable_account_ids
        # Block B of the monthly clearing: once a store's tender receivable for
        # the day is exhausted, a settlement may be collecting a prior-month
        # trade receivable instead. Offering it is fine; picking it is the
        # operator's call.
        if config.ar_account_id:
            accounts |= config.ar_account_id
        return accounts

    def _levis_day_window(self):
        """``(from, to)`` trading days this settlement may draw on.

        The upper end is never later than the day the money moved: a sale made
        after the bank paid for it cannot be what the bank paid for. See
        ``_levis_match_date_cutoff``.
        """
        self.ensure_one()
        config = self._levis_clearing_config()
        primary = self.levis_trans_date or self.date
        if not self.levis_trans_date and config:
            primary -= timedelta(days=config.settlement_lag_days or 0)
        date_to = primary + timedelta(days=_DAY_WINDOW_AFTER)
        cutoff = self._levis_match_date_cutoff()
        if cutoff and date_to > cutoff:
            date_to = cutoff
        return primary - timedelta(days=_DAY_WINDOW_BEFORE), date_to

    # ------------------------------------------------------------------
    # Nothing dated after the money moved
    # ------------------------------------------------------------------
    def _levis_match_date_cutoff(self):
        """The latest journal-item date this line may be offered.

        A settlement pays for takings that already happened. Offering a sale, a
        payment or an invoice dated *after* the bank moved the money invites the
        operator to clear a receivable with money that was received before it
        existed — the reconciliation looks tidy and the period it belongs to is
        wrong. So the bank's own transaction date is a ceiling, and it holds for
        every route into the matcher: the tender window, "Search More", and the
        generic scorer for lines this module does not recognise.
        """
        self.ensure_one()
        return self.date

    def _get_default_amls_matching_domain(self, allow_draft=False):
        domain = super()._get_default_amls_matching_domain(allow_draft=allow_draft)
        cutoff = self._levis_match_date_cutoff()
        # Applied here rather than in each caller: every candidate search in this
        # module and in ``custom_account_reconcile`` builds on this domain, so a
        # single leaf covers relax mode and the non-tender fallback too.
        return domain + [("date", "<=", cutoff)] if cutoff else domain

    def _levis_candidate_domain(self, relax=False):
        """Open tender receivables of this line's store, around its trading day."""
        self.ensure_one()
        accounts = self._levis_tender_accounts()
        if not accounts:
            return None
        domain = self._get_default_amls_matching_domain() + [
            ("account_id", "in", accounts.ids),
            ("amount_residual", ">", 0),
        ]
        if not relax:
            date_from, date_to = self._levis_day_window()
            domain += [("date", ">=", date_from), ("date", "<=", date_to)]
        return domain

    def _levis_same_ou(self, aml):
        """True when ``aml`` carries this line's Operating Unit.

        The analytic distribution is the authority — that is what the POS close
        and the monthly clearing write and what the P&L slices on. The explicit
        ``l10n_ou_analytic_id`` pick is honoured too, for hand-made entries.
        """
        self.ensure_one()
        wanted = self.levis_ou_analytic_id.id
        if not wanted:
            return False
        if str(wanted) in (aml.analytic_distribution or {}):
            return True
        return "l10n_ou_analytic_id" in aml._fields and aml.l10n_ou_analytic_id.id == wanted

    # ------------------------------------------------------------------
    # Candidate search
    # ------------------------------------------------------------------
    def _get_match_candidates(self, limit=30, relax=False):
        self.ensure_one()
        if not self._levis_is_tender_line():
            return super()._get_match_candidates(limit=limit, relax=relax)

        domain = self._levis_candidate_domain(relax=relax)
        if domain is None:
            # Configured for nothing to match against: say so by falling back
            # rather than returning an empty list that reads as "no candidates".
            return super()._get_match_candidates(limit=limit, relax=relax)

        amls = self.env["account.move.line"].search(domain, limit=limit * 20, order="date desc, id desc")
        own_ou = amls.filtered(self._levis_same_ou)
        # Another store's receivable is not a candidate. The whole point of the
        # MID mapping is that money is attributed by merchant id, never by amount
        # coincidence; an empty pool for this store is a finding to see, not a
        # gap to fill from the outlet next door. "Search More" is the deliberate
        # exception — an operator who asked for the wider net gets it.
        pool = amls if (relax and not own_ou) else own_ou

        target = self._levis_match_target()
        currency = self.company_id.currency_id
        primary_day = self.levis_trans_date
        config = self._levis_clearing_config()
        tender_accounts = config.pos_receivable_account_ids
        # Ships at zero, so ranking is unchanged until a tenant sets it. It can
        # only lift a near-miss into view; it never sizes or books anything.
        tolerance = config._match_tolerance(target) if config else 0.0
        matcher = self.env["levis.clearing.matcher"]

        def score(aml):
            return matcher._score_candidate(aml, target, primary_day, tender_accounts, currency, tolerance)

        return pool.sorted(key=score, reverse=True)[:limit]

    def _get_auto_match_candidate(self):
        """Auto-match must still see the gross, not the amount that landed."""
        self.ensure_one()
        if not self._levis_is_tender_line():
            return super()._get_auto_match_candidate()
        currency = self.company_id.currency_id
        target = self._levis_match_target()
        # A cash deposit is a sum of several days by nature; there is no single
        # unambiguous item, so it is left to the wizard's suggestion.
        if self.levis_narrative_kind != "settlement":
            return self.env["account.move.line"].browse()
        exact = self._get_match_candidates(limit=10).filtered(
            lambda aml: not currency.compare_amounts(aml.amount_residual, target)
        )
        return exact if len(exact) == 1 else exact.browse()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def action_open_match_wizard(self):
        """Open the matching screen as a page, not a modal.

        The generic wizard was built for "one invoice, one payment", which fits
        in a dialog. A Levi's settlement does not: the operator has to read the
        store, the gross, the fee and the trading day, then compare a dozen
        candidate rows that each carry their own store, day and residual. In a
        modal those columns collapse into an unreadable smear, and the decision
        being made is whose money this is.

        So it gets the full width, with the statement list still in the
        breadcrumb behind it.
        """
        self.ensure_one()
        action = super().action_open_match_wizard()
        action["target"] = "current"
        action["views"] = [(self.env.ref("custom_levis_bank_reconcile.view_bank_reconcile_wizard_page").id, "form")]
        context = dict(action.get("context") or {})
        # The wizard is a transient: the action must carry a record, or the page
        # opens on a blank one and default_get never sees the statement line.
        wizard = self.env["custom.bank.reconcile.wizard"].with_context(**context).create({})
        action["res_id"] = wizard.id
        action["context"] = context
        return action
