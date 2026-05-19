# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CustomFixedAsset(models.Model):
    _name = "custom.fixed.asset"
    _description = "Custom Fixed Asset"
    _inherit = ["mail.thread", "mail.activity.mixin", "pdp.audited.mixin"]
    _order = "code, id"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    group_id = fields.Many2one(
        comodel_name="custom.fixed.asset.group",
        string="Group",
        tracking=True,
    )
    location_id = fields.Many2one(
        comodel_name="custom.fixed.asset.location",
        string="Location",
        tracking=True,
    )
    custodian_id = fields.Many2one(
        comodel_name="res.users",
        string="Custodian",
        tracking=True,
    )
    note = fields.Html()

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------
    acquisition_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    acquisition_value = fields.Monetary(
        required=True,
        currency_field="currency_id",
        tracking=True,
    )
    salvage_value = fields.Monetary(
        default=0.0,
        currency_field="currency_id",
    )
    useful_life_months = fields.Integer(
        string="Useful Life (months)",
        required=True,
        default=60,
    )
    depreciation_method = fields.Selection(
        selection=[
            ("straight_line", "Straight line"),
            ("declining", "Declining balance"),
            ("none", "No depreciation"),
        ],
        default="straight_line",
        required=True,
    )
    declining_factor = fields.Float(
        string="Declining Factor",
        default=2.0,
        help="Factor applied to the straight-line rate when method = declining "
             "balance (e.g. 2.0 = double declining).",
    )

    # ------------------------------------------------------------------
    # Accounts (override of group defaults)
    # ------------------------------------------------------------------
    asset_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Asset Account",
    )
    depreciation_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Accumulated Depreciation Account",
    )
    expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Depreciation Expense Account",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Depreciation Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )

    # ------------------------------------------------------------------
    # Schedule + computed totals
    # ------------------------------------------------------------------
    depreciation_line_ids = fields.One2many(
        comodel_name="custom.fixed.asset.depreciation.line",
        inverse_name="asset_id",
        string="Depreciation Schedule",
        copy=False,
    )
    accumulated_depreciation = fields.Monetary(
        compute="_compute_depreciation_totals",
        currency_field="currency_id",
        store=False,
    )
    net_book_value = fields.Monetary(
        compute="_compute_depreciation_totals",
        currency_field="currency_id",
        store=False,
    )

    # ------------------------------------------------------------------
    # State / disposal
    # ------------------------------------------------------------------
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("disposed", "Disposed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    disposal_date = fields.Date(readonly=True, copy=False)
    disposal_value = fields.Monetary(
        currency_field="currency_id", readonly=True, copy=False,
    )
    disposal_gain_loss = fields.Monetary(
        currency_field="currency_id", readonly=True, copy=False,
    )
    disposal_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Disposal Journal Entry",
        readonly=True, copy=False,
    )

    _sql_constraints = [
        (
            "code_company_unique",
            "UNIQUE(code, company_id)",
            "Asset code must be unique within a company.",
        ),
    ]

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("useful_life_months")
    def _check_useful_life(self):
        for asset in self:
            if asset.depreciation_method != "none" and asset.useful_life_months < 1:
                raise ValidationError(_(
                    "Asset \"%(name)s\": useful life must be at least 1 month.",
                    name=asset.name,
                ))

    @api.constrains("salvage_value", "acquisition_value")
    def _check_salvage(self):
        for asset in self:
            if asset.salvage_value < 0:
                raise ValidationError(_(
                    "Asset \"%(name)s\": salvage value cannot be negative.",
                    name=asset.name,
                ))
            if asset.salvage_value > asset.acquisition_value:
                raise ValidationError(_(
                    "Asset \"%(name)s\": salvage value cannot exceed acquisition value.",
                    name=asset.name,
                ))

    @api.constrains("declining_factor", "depreciation_method")
    def _check_declining_factor(self):
        for asset in self:
            if asset.depreciation_method == "declining" and asset.declining_factor <= 0:
                raise ValidationError(_(
                    "Declining factor must be strictly positive."
                ))

    # ------------------------------------------------------------------
    # On-change: pull defaults from group
    # ------------------------------------------------------------------
    @api.onchange("group_id")
    def _onchange_group_id(self):
        for asset in self:
            if not asset.group_id:
                continue
            grp = asset.group_id
            if grp.default_useful_life_months and not asset.useful_life_months:
                asset.useful_life_months = grp.default_useful_life_months
            if grp.default_asset_account_id and not asset.asset_account_id:
                asset.asset_account_id = grp.default_asset_account_id
            if grp.default_depreciation_account_id and not asset.depreciation_account_id:
                asset.depreciation_account_id = grp.default_depreciation_account_id
            if grp.default_expense_account_id and not asset.expense_account_id:
                asset.expense_account_id = grp.default_expense_account_id
            if grp.default_journal_id and not asset.journal_id:
                asset.journal_id = grp.default_journal_id

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends(
        "depreciation_line_ids.amount",
        "depreciation_line_ids.posted",
        "acquisition_value",
    )
    def _compute_depreciation_totals(self):
        for asset in self:
            posted = asset.depreciation_line_ids.filtered("posted")
            accum = sum(posted.mapped("amount"))
            asset.accumulated_depreciation = accum
            asset.net_book_value = (asset.acquisition_value or 0.0) - accum

    # ------------------------------------------------------------------
    # Schedule generation
    # ------------------------------------------------------------------
    def _depreciable_base(self):
        self.ensure_one()
        return max(0.0, self.acquisition_value - (self.salvage_value or 0.0))

    def _build_schedule(self):
        """Regenerate the depreciation schedule. Already-posted lines are
        preserved; remaining unposted lines are recomputed from the asset's
        current parameters.
        """
        self.ensure_one()
        if self.depreciation_method == "none":
            return
        base = self._depreciable_base()
        months = self.useful_life_months
        if months <= 0 or base <= 0:
            return

        # Drop unposted lines so we can rebuild from current parameters.
        self.depreciation_line_ids.filtered(lambda l: not l.posted).unlink()
        posted_amount = sum(
            self.depreciation_line_ids.filtered("posted").mapped("amount")
        )
        remaining = max(0.0, base - posted_amount)
        if remaining <= 0:
            return

        start = self.acquisition_date or fields.Date.context_today(self)
        first_seq = (
            max(self.depreciation_line_ids.mapped("sequence")) + 1
            if self.depreciation_line_ids else 1
        )
        months_left = months - len(self.depreciation_line_ids.filtered("posted"))
        if months_left <= 0:
            return

        vals_list = []
        if self.depreciation_method == "straight_line":
            monthly = round(remaining / months_left, 2)
            running = 0.0
            for i in range(months_left):
                line_date = start + relativedelta(months=first_seq + i)
                if i == months_left - 1:
                    # Absorb rounding residual in the last line so total == base.
                    amount = round(remaining - running, 2)
                else:
                    amount = monthly
                    running += amount
                vals_list.append({
                    "asset_id": self.id,
                    "sequence": first_seq + i,
                    "date": line_date,
                    "amount": amount,
                })
        elif self.depreciation_method == "declining":
            # Declining balance: each month depreciate (factor / total_months)
            # of the remaining NBV. Switch to straight-line on the residual in
            # the final period to fully consume the base.
            rate = self.declining_factor / float(months)
            nbv = remaining
            running = 0.0
            for i in range(months_left):
                line_date = start + relativedelta(months=first_seq + i)
                if i == months_left - 1:
                    amount = round(remaining - running, 2)
                else:
                    amount = round(nbv * rate, 2)
                    if running + amount > remaining:
                        amount = round(remaining - running, 2)
                    nbv -= amount
                    running += amount
                vals_list.append({
                    "asset_id": self.id,
                    "sequence": first_seq + i,
                    "date": line_date,
                    "amount": amount,
                })

        if vals_list:
            self.env["custom.fixed.asset.depreciation.line"].create(vals_list)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def action_confirm(self):
        for asset in self:
            if asset.state != "draft":
                raise UserError(_("Only draft assets can be confirmed."))
            if asset.depreciation_method != "none":
                if not asset.expense_account_id or not asset.depreciation_account_id:
                    raise UserError(_(
                        "Asset \"%(name)s\": depreciation expense and accumulated "
                        "depreciation accounts must be set before confirming.",
                        name=asset.name,
                    ))
                if not asset.journal_id:
                    raise UserError(_(
                        "Asset \"%(name)s\": depreciation journal must be set.",
                        name=asset.name,
                    ))
                asset._build_schedule()
            asset.state = "running"

    def action_cancel(self):
        for asset in self:
            if asset.depreciation_line_ids.filtered("posted"):
                raise UserError(_(
                    "Cannot cancel asset \"%(name)s\": depreciation entries have "
                    "already been posted. Reverse them first.",
                    name=asset.name,
                ))
        self.filtered(lambda a: a.state in ("draft", "running")).write({
            "state": "cancelled",
        })

    def action_reset_draft(self):
        for asset in self:
            if asset.depreciation_line_ids.filtered("posted"):
                raise UserError(_(
                    "Asset \"%(name)s\" has posted depreciation; cannot reset.",
                    name=asset.name,
                ))
        self.depreciation_line_ids.unlink()
        self.write({"state": "draft"})

    def action_open_dispose_wizard(self):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only running assets can be disposed."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Dispose Asset"),
            "res_model": "custom.fixed.asset.disposal.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_id": self.id},
        }

    # ------------------------------------------------------------------
    # Posting due depreciation lines
    # ------------------------------------------------------------------
    def _post_due_depreciation(self, as_of=None):
        """Post all unposted depreciation lines whose date is <= ``as_of``.
        Creates one ``account.move`` per line: DR expense / CR accumulated.
        """
        as_of = as_of or fields.Date.context_today(self)
        AccountMove = self.env["account.move"]
        posted_count = 0
        for asset in self:
            if asset.state != "running":
                continue
            due = asset.depreciation_line_ids.filtered(
                lambda l: not l.posted and l.date <= as_of
            ).sorted("date")
            for line in due:
                move_vals = {
                    "date": line.date,
                    "journal_id": asset.journal_id.id,
                    "company_id": asset.company_id.id,
                    "ref": _("Depreciation %(code)s #%(seq)s",
                             code=asset.code, seq=line.sequence),
                    "line_ids": [
                        (0, 0, {
                            "name": _("Depreciation %(name)s",
                                      name=asset.name),
                            "account_id": asset.expense_account_id.id,
                            "debit": line.amount,
                            "credit": 0.0,
                        }),
                        (0, 0, {
                            "name": _("Accum. depreciation %(name)s",
                                      name=asset.name),
                            "account_id": asset.depreciation_account_id.id,
                            "debit": 0.0,
                            "credit": line.amount,
                        }),
                    ],
                }
                move = AccountMove.create(move_vals)
                move.action_post()
                line.write({"posted": True, "move_id": move.id})
                posted_count += 1
            # If schedule fully consumed -> nothing else to do; the asset
            # remains running until explicitly disposed.
        return posted_count

    @api.model
    def _cron_post_due_depreciation(self):
        """Monthly cron entry point. Posts every running asset whose
        schedule has reached its due date.
        """
        running = self.search([("state", "=", "running")])
        count = running._post_due_depreciation()
        _logger.info("custom.fixed.asset: posted %s depreciation lines", count)
        return count

    # ------------------------------------------------------------------
    # Create with sequence
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("custom.fixed.asset")
                vals["code"] = seq or _("New")
        return super().create(vals_list)
