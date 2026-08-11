# -*- coding: utf-8 -*-
"""The matching wizard, told what a Levi's settlement is.

Three things change, all of them about what the operator is *shown*:

* the store is on every candidate row, because a tender receivable is only the
  right one if it belongs to the outlet whose merchant id the bank printed;
* a card settlement is measured against its gross, and the fee the acquirer kept
  arrives pre-filled on the MDR expense account with that store's Operating Unit
  — the remainder that used to be a mystery is now a named number;
* a cash deposit can be filled in automatically, largest day first, and the fill
  stops at the deposit. It never proposes more cash than the bank received.

The reconciliation itself is untouched: still ``_reconcile_with_amls``.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class BankReconcileWizard(models.TransientModel):
    _inherit = "custom.bank.reconcile.wizard"

    levis_narrative_kind = fields.Selection(related="st_line_id.levis_narrative_kind", string="Narrative Type")
    levis_channel = fields.Selection(related="st_line_id.levis_channel", string="Tender Channel")
    levis_mid = fields.Char(related="st_line_id.levis_mid", string="Merchant / Terminal")
    levis_ou_analytic_id = fields.Many2one(related="st_line_id.levis_ou_analytic_id", string="Operating Unit")
    levis_trans_date = fields.Date(related="st_line_id.levis_trans_date", string="Trading Day")
    levis_gross = fields.Monetary(
        related="st_line_id.levis_gross", string="Gross (Narrative)", currency_field="currency_id"
    )
    levis_mdr = fields.Monetary(related="st_line_id.levis_mdr", string="MDR (Narrative)", currency_field="currency_id")
    levis_is_tender = fields.Boolean(compute="_compute_levis_is_tender")
    levis_target = fields.Monetary(
        compute="_compute_levis_is_tender",
        currency_field="currency_id",
        string="To Match",
        help="What the selected journal items should add up to: the gross for a "
        "card settlement (its fee is booked separately), the deposit itself for cash.",
    )
    levis_gap = fields.Monetary(
        compute="_compute_levis_gap",
        currency_field="currency_id",
        string="Still Unmatched",
        help="Target minus what is selected. Zero means the settlement is fully "
        "accounted for once the MDR below is booked.",
    )

    @api.depends("st_line_id")
    def _compute_levis_is_tender(self):
        for wiz in self:
            st_line = wiz.st_line_id
            wiz.levis_is_tender = bool(st_line) and st_line._levis_is_tender_line()
            wiz.levis_target = st_line._levis_match_target() if st_line else 0.0

    @api.depends("candidate_ids.selected", "levis_target")
    def _compute_levis_gap(self):
        for wiz in self:
            selected = sum(wiz.candidate_ids.filtered("selected").mapped("amount_residual"))
            wiz.levis_gap = (wiz.levis_target or 0.0) - selected

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        st_line = self.env["account.bank.statement.line"].browse(
            res.get("st_line_id") or self.env.context.get("default_st_line_id")
        )
        if not (st_line and st_line._levis_is_tender_line()):
            return res
        # The fee is not a write-off in the usual sense — it is a known expense
        # the acquirer already deducted — but mechanically it is the same leg, so
        # it rides the same channel with its own account and label.
        config = st_line._levis_clearing_config()
        if st_line.levis_narrative_kind == "settlement" and st_line.levis_mdr and config.mdr_account_id:
            res["writeoff"] = True
            res["writeoff_account_id"] = config.mdr_account_id.id
            res["writeoff_label"] = _(
                "MDR %(channel)s %(store)s",
                channel=st_line.levis_channel or "",
                store=st_line.levis_ou_analytic_id.display_name or "",
            )
        return res

    @api.model
    def _candidate_commands(self, st_line, relax):
        """Preselect against the gross, not against the money that landed."""
        if not st_line._levis_is_tender_line():
            return super()._candidate_commands(st_line, relax)
        comp_cur = st_line.company_id.currency_id
        target = st_line._levis_match_target()
        commands = []
        preselected = False
        for aml in st_line._get_match_candidates(relax=relax):
            exact = not comp_cur.compare_amounts(abs(aml.amount_residual), target)
            select = exact and not preselected
            preselected = preselected or select
            commands.append((0, 0, {"aml_id": aml.id, "selected": select}))
        return commands

    # ------------------------------------------------------------------
    # Cash suggestion
    # ------------------------------------------------------------------
    def action_levis_suggest(self):
        """Fill the selection up to — never past — the statement amount.

        One cash deposit covers several trading days, so there is no single item
        to find; the days have to be assembled. Largest day first, skipping any
        that no longer fits in what is left — so the deposit is explained by as
        few whole days as possible instead of by a scattering of partials.

        Whatever is left over stays open on suspense on purpose: an unexplained
        shortfall must remain visible, and Finance decides what it was.
        """
        self.ensure_one()
        if not self.levis_is_tender:
            raise UserError(
                _(
                    "This line is not a recognised POS settlement (%s), so there is "
                    "nothing to suggest from. Match it manually or map its merchant "
                    "id first.",
                    dict(self.st_line_id._fields["levis_narrative_kind"]._description_selection(self.env)).get(
                        self.st_line_id.levis_narrative_kind
                    )
                    or _("unreadable narrative"),
                )
            )
        currency = self.company_id.currency_id
        budget = self.levis_target
        chosen = self.env["custom.bank.reconcile.wizard.line"].browse()
        for line in self.candidate_ids.sorted(lambda c: c.amount_residual, reverse=True):
            residual = line.amount_residual
            if residual <= 0 or currency.compare_amounts(residual, budget) > 0:
                continue
            chosen |= line
            budget -= residual
            if currency.is_zero(budget):
                break
        if not chosen:
            raise UserError(
                _(
                    "No open item of %(store)s fits within %(amount)s. Use Search "
                    "More to widen the period, or match manually.",
                    store=self.levis_ou_analytic_id.display_name or _("this store"),
                    amount=formatLang(self.env, self.levis_target, currency_obj=currency),
                )
            )
        self.candidate_ids.selected = False
        chosen.selected = True
        # Nothing to return: the page reloads the record in place. Re-opening it
        # as an action would stack another breadcrumb for every click.
        return None

    def action_search_more(self):
        """Refresh the candidates without leaving the page."""
        self.ensure_one()
        super().action_search_more()
        return None

    # ------------------------------------------------------------------
    # Reconcile
    # ------------------------------------------------------------------
    def action_reconcile(self):
        """Same mechanics, with the store stamped on the fee leg."""
        self.ensure_one()
        if not (self.levis_is_tender and self.writeoff and self.levis_ou_analytic_id):
            return super().action_reconcile()
        amls = self.candidate_ids.filtered("selected").mapped("aml_id")
        if not amls:
            raise UserError(_("Select at least one journal item to settle."))
        if not self.writeoff_account_id:
            raise UserError(_("Pick an account for the remainder (the MDR fee)."))
        # The fee account may only absorb the fee the acquirer actually printed.
        # Anything else landing there is a shortfall wearing a plausible name —
        # the very thing the monthly clearing reports instead of absorbing.
        config = self.st_line_id._levis_clearing_config()
        currency = self.company_id.currency_id
        if self.writeoff_account_id == config.mdr_account_id and currency.compare_amounts(
            self.remainder, self.levis_mdr
        ):
            raise UserError(
                _(
                    "The selection leaves %(remainder)s, but the bank printed an MDR "
                    "of %(mdr)s — a difference of %(gap)s. Adjust the selected items, "
                    "or book the remainder somewhere it can be seen instead of on the "
                    "MDR expense account.",
                    remainder=formatLang(self.env, self.remainder, currency_obj=currency),
                    mdr=formatLang(self.env, self.levis_mdr, currency_obj=currency),
                    gap=formatLang(self.env, self.remainder - self.levis_mdr, currency_obj=currency),
                )
            )
        self.st_line_id._reconcile_with_amls(
            amls,
            writeoff_vals={
                "account_id": self.writeoff_account_id.id,
                "name": self.writeoff_label or _("MDR"),
                "analytic_distribution": {str(self.levis_ou_analytic_id.id): 100.0},
            },
        )
        return {"type": "ir.actions.act_window_close"}


class BankReconcileWizardLine(models.TransientModel):
    _inherit = "custom.bank.reconcile.wizard.line"

    levis_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        compute="_compute_levis_ou_analytic_id",
        help="Store this tender receivable was booked for. It must be the store "
        "the bank's merchant id names, or the money is being attributed to the "
        "wrong outlet.",
    )
    levis_ou_matches = fields.Boolean(compute="_compute_levis_ou_analytic_id")

    @api.depends("aml_id", "wizard_id.levis_ou_analytic_id")
    def _compute_levis_ou_analytic_id(self):
        for line in self:
            aml = line.aml_id
            analytic_id = next(iter(aml.analytic_distribution or {}), None)
            if not analytic_id and "l10n_ou_analytic_id" in aml._fields:
                analytic_id = aml.l10n_ou_analytic_id.id
            line.levis_ou_analytic_id = int(analytic_id) if analytic_id else False
            wanted = line.wizard_id.levis_ou_analytic_id
            line.levis_ou_matches = bool(wanted) and line.levis_ou_analytic_id == wanted
