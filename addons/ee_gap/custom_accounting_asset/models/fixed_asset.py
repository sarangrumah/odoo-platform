# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.tools import float_compare
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
        default=lambda self: self.env._("New"),
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
    posting_date = fields.Date(
        string="Posting Date",
        tracking=True,
        copy=False,
        help="Reference date used to schedule and date each depreciation entry. "
        "Falls back to the acquisition date when left empty.",
    )
    depreciation_date_mode = fields.Selection(
        selection=[
            ("specific", "Specific date (same day as posting date)"),
            ("next_month", "Specific date, next month"),
            ("end_following_month", "End of the following month"),
        ],
        string="Depreciation Date Rule",
        default="next_month",
        required=True,
        help="How each depreciation line date is derived from the posting date.",
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
    quantity = fields.Float(
        string="Quantity",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
        tracking=True,
        help="Number of physical units carried under this single asset number. A "
        "pooled asset (e.g. 5 waste bins bought together) keeps one code, one "
        "acquisition value and one schedule; retiring a broken unit reduces this "
        "quantity and the value along with it.",
    )
    original_quantity = fields.Float(
        string="Original Quantity",
        default=1.0,
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        help="Quantity at acquisition. Kept as the denominator for the register; never changed by a retirement.",
    )
    retired_quantity = fields.Float(
        string="Retired Quantity",
        compute="_compute_retired_quantity",
        digits="Product Unit of Measure",
    )
    is_quantity_asset = fields.Boolean(
        string="Pooled Asset",
        compute="_compute_quantity_flags",
        store=True,
        help="Set automatically when the asset carries more than one unit, or "
        "when units have already been retired from it.",
    )
    unit_acquisition_value = fields.Monetary(
        string="Value per Unit",
        compute="_compute_quantity_figures",
        currency_field="currency_id",
        help="Gross carrying amount (acquisition + revaluation) divided by the "
        "quantity still held. This is the amount removed when one unit is retired.",
    )
    unit_net_book_value = fields.Monetary(
        string="NBV per Unit",
        compute="_compute_quantity_figures",
        currency_field="currency_id",
    )
    retired_cost = fields.Monetary(
        string="Retired Cost",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
        help="Cumulative gross carrying amount taken out of the asset account by partial retirements.",
    )
    retired_accumulated_depreciation = fields.Monetary(
        string="Retired Accum. Depreciation",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Cumulative accumulated depreciation released by partial retirements. "
        "Subtracted from the posted schedule so the remaining pool keeps a correct "
        "accumulated depreciation and net book value.",
    )
    opening_accumulated_depreciation = fields.Monetary(
        string="Opening / Carried Accum. Depreciation",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
        help="Accumulated depreciation the asset carries WITHOUT a posted schedule "
        "line behind it: an opening balance loaded at cutover, or the depreciation "
        "absorbed from assets merged into this one. Added to the posted total.",
    )
    merged_into_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Merged Into",
        readonly=True,
        copy=False,
        index=True,
        help="Set on an asset that was absorbed into a pooled asset. The record is "
        "kept (its posted depreciation is history) but is no longer depreciated.",
    )
    merged_asset_ids = fields.One2many(
        comodel_name="custom.fixed.asset",
        inverse_name="merged_into_id",
        string="Merged Assets",
        readonly=True,
    )
    merged_count = fields.Integer(compute="_compute_merged_count")
    partial_disposal_ids = fields.One2many(
        comodel_name="custom.fixed.asset.partial.disposal",
        inverse_name="asset_id",
        string="Partial Retirements",
        copy=False,
    )
    partial_disposal_count = fields.Integer(
        compute="_compute_partial_disposal_count",
    )
    revaluation_value = fields.Monetary(
        string="Cumulative Revaluation",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
        help="Net cumulative revaluation booked to the asset account. Positive for "
        "upward revaluations, negative for downward ones.",
    )
    revaluation_surplus_balance = fields.Monetary(
        string="Revaluation Surplus Balance",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
        help="Credit balance of the revaluation surplus (equity) held for this asset. "
        "A downward revaluation offsets this before hitting P&L; the remainder is "
        "transferred to retained earnings on disposal.",
    )
    revaluation_loss_recognized = fields.Monetary(
        string="Revaluation Loss Recognized",
        default=0.0,
        currency_field="currency_id",
        readonly=True,
        copy=False,
        tracking=True,
        help="Cumulative downward revaluation expensed to P&L that a future upward "
        "revaluation reverses (as income) before crediting surplus.",
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
        help="Factor applied to the straight-line rate when method = declining balance (e.g. 2.0 = double declining).",
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
    # Revaluation history
    # ------------------------------------------------------------------
    revaluation_ids = fields.One2many(
        comodel_name="custom.fixed.asset.revaluation",
        inverse_name="asset_id",
        string="Revaluations",
        copy=False,
    )
    revaluation_count = fields.Integer(
        compute="_compute_revaluation_count",
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
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )
    disposal_gain_loss = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )
    disposal_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Disposal Journal Entry",
        readonly=True,
        copy=False,
    )

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "Asset code must be unique within a company.",
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("useful_life_months")
    def _check_useful_life(self):
        for asset in self:
            if asset.depreciation_method != "none" and asset.useful_life_months < 1:
                raise ValidationError(
                    _(
                        'Asset "%(name)s": useful life must be at least 1 month.',
                        name=asset.name,
                    )
                )

    @api.constrains("salvage_value", "acquisition_value")
    def _check_salvage(self):
        for asset in self:
            if asset.salvage_value < 0:
                raise ValidationError(
                    _(
                        'Asset "%(name)s": salvage value cannot be negative.',
                        name=asset.name,
                    )
                )
            if asset.salvage_value > asset.acquisition_value:
                raise ValidationError(
                    _(
                        'Asset "%(name)s": salvage value cannot exceed acquisition value.',
                        name=asset.name,
                    )
                )

    @api.constrains("quantity", "original_quantity")
    def _check_quantity(self):
        for asset in self:
            if asset.quantity <= 0:
                raise ValidationError(
                    _(
                        'Asset "%(name)s": quantity must be strictly positive. Retire '
                        "the whole pool through Dispose instead.",
                        name=asset.name,
                    )
                )
            if asset.original_quantity and asset.quantity > asset.original_quantity:
                raise ValidationError(
                    _(
                        'Asset "%(name)s": quantity (%(qty)s) cannot exceed the original '
                        "quantity (%(orig)s). Book an addition as a separate asset.",
                        name=asset.name,
                        qty=asset.quantity,
                        orig=asset.original_quantity,
                    )
                )

    @api.constrains("declining_factor", "depreciation_method")
    def _check_declining_factor(self):
        for asset in self:
            if asset.depreciation_method == "declining" and asset.declining_factor <= 0:
                raise ValidationError(_("Declining factor must be strictly positive."))

    # ------------------------------------------------------------------
    # On-change: pull defaults from group
    # ------------------------------------------------------------------
    @api.onchange("acquisition_date")
    def _onchange_acquisition_date(self):
        for asset in self:
            if asset.acquisition_date and not asset.posting_date:
                asset.posting_date = asset.acquisition_date

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
        "depreciation_line_ids.reversed",
        "acquisition_value",
        "revaluation_value",
        "retired_accumulated_depreciation",
        "opening_accumulated_depreciation",
    )
    def _compute_depreciation_totals(self):
        for asset in self:
            posted = asset.depreciation_line_ids.filtered("posted")
            # A partial retirement releases its share of the accumulated
            # depreciation in the GL; the posted lines themselves stay untouched
            # (they are history), so the released share is netted off here.
            accum = (
                sum(posted.mapped("amount"))
                + (asset.opening_accumulated_depreciation or 0.0)
                - (asset.retired_accumulated_depreciation or 0.0)
            )
            asset.accumulated_depreciation = accum
            asset.net_book_value = (asset.acquisition_value or 0.0) + (asset.revaluation_value or 0.0) - accum

    @api.depends("quantity", "original_quantity")
    def _compute_quantity_flags(self):
        """Only the stored flag, and only off the quantities.

        Depreciation totals move every time a line is posted; folding this into
        the money compute would rewrite the stored column for every asset on
        every monthly run. Odoo also warns when one compute mixes stored and
        non-stored fields, which is why ``retired_quantity`` has its own.
        """
        for asset in self:
            qty = asset.quantity or 0.0
            original = asset.original_quantity or qty
            asset.is_quantity_asset = original > 1.0 or qty > 1.0 or original > qty

    @api.depends("quantity", "original_quantity")
    def _compute_retired_quantity(self):
        for asset in self:
            qty = asset.quantity or 0.0
            original = asset.original_quantity or qty
            asset.retired_quantity = max(0.0, original - qty)

    @api.depends(
        "quantity",
        "acquisition_value",
        "revaluation_value",
        "accumulated_depreciation",
    )
    def _compute_quantity_figures(self):
        for asset in self:
            qty = asset.quantity or 0.0
            gross = (asset.acquisition_value or 0.0) + (asset.revaluation_value or 0.0)
            asset.unit_acquisition_value = gross / qty if qty else 0.0
            asset.unit_net_book_value = (asset.net_book_value or 0.0) / qty if qty else 0.0

    def _compute_merged_count(self):
        for asset in self:
            asset.merged_count = len(asset.merged_asset_ids)

    def _compute_partial_disposal_count(self):
        for asset in self:
            asset.partial_disposal_count = len(asset.partial_disposal_ids)

    def _compute_revaluation_count(self):
        for asset in self:
            asset.revaluation_count = len(asset.revaluation_ids)

    # ------------------------------------------------------------------
    # Schedule generation
    # ------------------------------------------------------------------
    def _depreciable_base(self):
        self.ensure_one()
        return max(
            0.0,
            self.acquisition_value + (self.revaluation_value or 0.0) - (self.salvage_value or 0.0),
        )

    def _depreciation_date_for(self, seq_number):
        """Return the date of the depreciation line with the given month ordinal,
        honouring ``depreciation_date_mode`` and anchored on ``posting_date``.
        """
        self.ensure_one()
        start = self.posting_date or self.acquisition_date or fields.Date.context_today(self)
        mode = self.depreciation_date_mode or "next_month"
        if mode == "specific":
            # Line 1 lands exactly on the posting date, then monthly increments.
            return start + relativedelta(months=seq_number - 1)
        if mode == "end_following_month":
            # Last day of the month that follows the anchor by ``seq_number`` months.
            return start + relativedelta(months=seq_number, day=31)
        # next_month (default) — one month after the anchor for line 1.
        return start + relativedelta(months=seq_number)

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

        # Drop unposted lines so we can rebuild from current parameters. Reversed
        # lines are kept for audit (posted=False but excluded from scheduling).
        self.depreciation_line_ids.filtered(lambda l: not l.posted and not l.reversed).unlink()
        # ``accumulated_depreciation`` is the posted total minus whatever a
        # partial retirement already released, so the remaining pool is
        # depreciated over what is genuinely left of its depreciable base.
        remaining = max(0.0, base - self.accumulated_depreciation)
        if remaining <= 0:
            return

        first_seq = max(self.depreciation_line_ids.mapped("sequence")) + 1 if self.depreciation_line_ids else 1
        months_left = months - len(self.depreciation_line_ids.filtered("posted"))
        if months_left <= 0:
            return

        vals_list = []
        if self.depreciation_method == "straight_line":
            monthly = round(remaining / months_left, 2)
            running = 0.0
            for i in range(months_left):
                line_date = self._depreciation_date_for(first_seq + i)
                if i == months_left - 1:
                    # Absorb rounding residual in the last line so total == base.
                    amount = round(remaining - running, 2)
                else:
                    amount = monthly
                    running += amount
                vals_list.append(
                    {
                        "asset_id": self.id,
                        "sequence": first_seq + i,
                        "date": line_date,
                        "amount": amount,
                    }
                )
        elif self.depreciation_method == "declining":
            # Declining balance: each month depreciate (factor / total_months)
            # of the remaining NBV. Switch to straight-line on the residual in
            # the final period to fully consume the base.
            rate = self.declining_factor / float(months)
            nbv = remaining
            running = 0.0
            for i in range(months_left):
                line_date = self._depreciation_date_for(first_seq + i)
                if i == months_left - 1:
                    amount = round(remaining - running, 2)
                else:
                    amount = round(nbv * rate, 2)
                    if running + amount > remaining:
                        amount = round(remaining - running, 2)
                    nbv -= amount
                    running += amount
                vals_list.append(
                    {
                        "asset_id": self.id,
                        "sequence": first_seq + i,
                        "date": line_date,
                        "amount": amount,
                    }
                )

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
                    raise UserError(
                        _(
                            'Asset "%(name)s": depreciation expense and accumulated '
                            "depreciation accounts must be set before confirming.",
                            name=asset.name,
                        )
                    )
                if not asset.journal_id:
                    raise UserError(
                        _(
                            'Asset "%(name)s": depreciation journal must be set.',
                            name=asset.name,
                        )
                    )
                asset._build_schedule()
            asset.state = "running"

    def action_cancel(self):
        for asset in self:
            if asset.depreciation_line_ids.filtered("posted"):
                raise UserError(
                    _(
                        'Cannot cancel asset "%(name)s": depreciation entries have '
                        "already been posted. Reverse them first.",
                        name=asset.name,
                    )
                )
        self.filtered(lambda a: a.state in ("draft", "running")).write(
            {
                "state": "cancelled",
            }
        )

    def action_reset_draft(self):
        for asset in self:
            if asset.depreciation_line_ids.filtered("posted"):
                raise UserError(
                    _(
                        'Asset "%(name)s" has posted depreciation; cannot reset.',
                        name=asset.name,
                    )
                )
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

    def action_open_revaluation_wizard(self):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only running assets can be revalued."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Revalue Asset"),
            "res_model": "custom.fixed.asset.revaluation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_id": self.id},
        }

    def action_open_partial_disposal_wizard(self):
        """Retire part of a pooled asset (e.g. 1 broken bin out of 5)."""
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only running assets can have units retired."))
        if self.quantity <= 1:
            raise UserError(
                _(
                    'Asset "%(name)s" carries a single unit. Use Dispose to retire it.',
                    name=self.name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Retire Units"),
            "res_model": "custom.fixed.asset.partial.disposal.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_asset_id": self.id},
        }

    def action_view_partial_disposals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partial Retirements"),
            "res_model": "custom.fixed.asset.partial.disposal",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
        }

    def _partial_retirement_split(self, quantity):
        """Split the asset's carrying amounts on ``quantity`` units going out.

        Everything is pro-rated on the units still held, so retiring 1 unit of 5
        takes exactly a fifth of the cost, of the revaluation, of the accumulated
        depreciation and of the salvage value with it. Returns a dict of the
        amounts that leave the asset, rounded to the company currency.
        """
        self.ensure_one()
        rounding = self.currency_id.round
        qty = self.quantity or 0.0
        if quantity <= 0:
            raise UserError(_("Retired quantity must be strictly positive."))
        if quantity > qty:
            raise UserError(
                _(
                    "Cannot retire %(out)s units: the asset only carries %(qty)s.",
                    out=quantity,
                    qty=qty,
                )
            )
        full = float_compare(quantity, qty, precision_rounding=0.000001) == 0
        ratio = 1.0 if full else quantity / qty
        acquisition = rounding(self.acquisition_value * ratio) if not full else self.acquisition_value
        revaluation = rounding((self.revaluation_value or 0.0) * ratio) if not full else (self.revaluation_value or 0.0)
        accum = rounding(self.accumulated_depreciation * ratio) if not full else self.accumulated_depreciation
        salvage = rounding((self.salvage_value or 0.0) * ratio) if not full else (self.salvage_value or 0.0)
        surplus = (
            rounding((self.revaluation_surplus_balance or 0.0) * ratio)
            if not full
            else (self.revaluation_surplus_balance or 0.0)
        )
        loss_recognized = (
            rounding((self.revaluation_loss_recognized or 0.0) * ratio)
            if not full
            else (self.revaluation_loss_recognized or 0.0)
        )
        cost = acquisition + revaluation
        return {
            "full": full,
            "quantity": quantity,
            "acquisition_value": acquisition,
            "revaluation_value": revaluation,
            "cost": cost,
            "accumulated_depreciation": accum,
            "salvage_value": salvage,
            "surplus": surplus,
            "loss_recognized": loss_recognized,
            "net_book_value": rounding(cost - accum),
        }

    def _apply_partial_retirement(self, split, disposal_date, proceeds, gain_loss, move):
        """Shrink the asset to the units it still holds and reschedule.

        The posted depreciation lines are history and stay as they are; the share
        of accumulated depreciation released by the retirement is carried in
        ``retired_accumulated_depreciation`` and netted off the totals. The
        unposted part of the schedule is then rebuilt, so from the next run the
        monthly charge follows the smaller pool.
        """
        self.ensure_one()
        if split["full"]:
            # Every unit is gone: this is a plain disposal. The carrying amounts
            # stay on the record (the journal entry has released them) exactly as
            # the disposal wizard leaves them, so the register still shows what
            # was disposed of and when.
            self.write(
                {
                    "state": "disposed",
                    "disposal_date": disposal_date,
                    "disposal_value": proceeds,
                    "disposal_gain_loss": gain_loss,
                    "disposal_move_id": move.id if move else False,
                    "revaluation_surplus_balance": 0.0,
                }
            )
            self.depreciation_line_ids.filtered(lambda l: not l.posted and not l.reversed).unlink()
            return
        vals = {
            "acquisition_value": self.acquisition_value - split["acquisition_value"],
            "revaluation_value": (self.revaluation_value or 0.0) - split["revaluation_value"],
            "salvage_value": (self.salvage_value or 0.0) - split["salvage_value"],
            "revaluation_surplus_balance": (self.revaluation_surplus_balance or 0.0) - split["surplus"],
            "revaluation_loss_recognized": (self.revaluation_loss_recognized or 0.0) - split["loss_recognized"],
            "retired_cost": (self.retired_cost or 0.0) + split["cost"],
            "retired_accumulated_depreciation": (self.retired_accumulated_depreciation or 0.0)
            + split["accumulated_depreciation"],
            "quantity": self.quantity - split["quantity"],
        }
        self.write(vals)
        self._build_schedule()

    def action_view_merged_assets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Merged Assets"),
            "res_model": "custom.fixed.asset",
            "view_mode": "list,form",
            "domain": [("merged_into_id", "=", self.id)],
        }

    def _merge_assets_into_pool(self, others):
        """Absorb ``others`` into ``self``, turning it into a pooled asset.

        For assets that are physically one purchase but were booked one record
        per unit. Nothing is posted to the GL: the cost already sits in the asset
        account and the depreciation already sits in accumulated depreciation.
        What moves is the subledger — the values are summed onto the survivor,
        the absorbed accumulated depreciation is carried in
        ``opening_accumulated_depreciation`` (its posted lines stay attached to
        the record they were booked against, so the audit trail survives), and
        the absorbed records are marked ``merged_into_id`` and cancelled.
        """
        self.ensure_one()
        others = others - self
        if not others:
            raise UserError(_("Nothing to merge into %(code)s.", code=self.code))
        for other in others:
            if other.company_id != self.company_id:
                raise UserError(_("Cannot merge assets across companies."))
            if other.currency_id != self.currency_id:
                raise UserError(_("Cannot merge assets in different currencies."))
            if other.state not in ("draft", "running"):
                raise UserError(
                    _(
                        'Asset "%(code)s" is %(state)s and cannot be merged.',
                        code=other.code,
                        state=other.state,
                    )
                )
            if other.merged_into_id:
                raise UserError(_('Asset "%(code)s" has already been merged elsewhere.', code=other.code))
            if other.partial_disposal_ids:
                raise UserError(
                    _(
                        'Asset "%(code)s" has partial retirements; merge it by hand.',
                        code=other.code,
                    )
                )

        absorbed_accum = sum(others.mapped("accumulated_depreciation"))
        vals = {
            "acquisition_value": self.acquisition_value + sum(others.mapped("acquisition_value")),
            "salvage_value": (self.salvage_value or 0.0) + sum(others.mapped("salvage_value")),
            "revaluation_value": (self.revaluation_value or 0.0) + sum(others.mapped("revaluation_value")),
            "revaluation_surplus_balance": (self.revaluation_surplus_balance or 0.0)
            + sum(others.mapped("revaluation_surplus_balance")),
            "revaluation_loss_recognized": (self.revaluation_loss_recognized or 0.0)
            + sum(others.mapped("revaluation_loss_recognized")),
            "opening_accumulated_depreciation": (self.opening_accumulated_depreciation or 0.0) + absorbed_accum,
            "quantity": self.quantity + sum(others.mapped("quantity")),
        }
        vals["original_quantity"] = vals["quantity"]
        self.write(vals)

        # The absorbed records keep their posted lines (history) but must never
        # be depreciated again.
        others.depreciation_line_ids.filtered(lambda line: not line.posted and not line.reversed).unlink()
        others.write({"merged_into_id": self.id, "state": "cancelled"})
        for other in others:
            other.message_post(
                body=_(
                    "Merged into pooled asset %(code)s. Cost %(cost)s and accumulated "
                    "depreciation %(accum)s carried over; this record is cancelled and "
                    "no longer depreciated.",
                    code=self.code,
                    cost=other.acquisition_value,
                    accum=other.accumulated_depreciation,
                )
            )
        self.message_post(
            body=_(
                "Absorbed %(count)s asset(s): %(codes)s. Quantity is now %(qty)s, "
                "acquisition value %(value)s, carried accumulated depreciation %(accum)s.",
                count=len(others),
                codes=", ".join(others.mapped("code")),
                qty=self.quantity,
                value=self.acquisition_value,
                accum=absorbed_accum,
            )
        )
        if self.state == "running":
            self._build_schedule()
        return self

    def action_view_revaluations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Revaluations"),
            "res_model": "custom.fixed.asset.revaluation",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"default_asset_id": self.id},
        }

    # ------------------------------------------------------------------
    # Posting due depreciation lines
    # ------------------------------------------------------------------
    def _group_depreciation_moves(self):
        """Whether to book ONE journal entry per period instead of one per asset.

        Default ON. A per-asset entry means 3,300+ documents a month on a real
        register (ARKA-AIM carries 3,328 running assets), which is not what
        Accounting asks for — they want a single monthly depreciation document
        they can point at, and the per-asset detail stays in this subledger.

        Set ``custom_accounting_asset.group_depreciation_moves`` to ``0`` on a
        tenant whose Accounting genuinely wants one entry per asset.
        """
        param = (
            self.env["ir.config_parameter"].sudo().get_param("custom_accounting_asset.group_depreciation_moves", "1")
        )
        return str(param).strip().lower() in ("1", "true", "yes")

    def _post_due_depreciation(self, as_of=None):
        """Post all unposted depreciation lines whose date is <= ``as_of``.

        Books DR expense / CR accumulated depreciation. Lines are grouped into
        one ``account.move`` per (company, journal, expense account, accumulated
        account, date) — so a monthly run yields one document per date rather
        than one per asset. See :meth:`_group_depreciation_moves` to opt out.

        Grouping keys on the exact line ``date`` rather than on the month, so
        assets whose schedule falls on a different day of the month keep their
        own correctly-dated entry instead of being pulled into someone else's
        accounting date.
        """
        as_of = as_of or fields.Date.context_today(self)
        AccountMove = self.env["account.move"]
        grouped = self._group_depreciation_moves()

        # Collect due lines across the whole recordset first: grouping has to
        # span assets, so this cannot be done inside a per-asset loop.
        buckets = {}
        for asset in self:
            if asset.state != "running":
                continue
            due = asset.depreciation_line_ids.filtered(lambda l: not l.posted and not l.reversed and l.date <= as_of)
            for line in due:
                key = (
                    asset.company_id.id,
                    asset.journal_id.id,
                    asset.expense_account_id.id,
                    asset.depreciation_account_id.id,
                    line.date,
                    # Without grouping, the line's own id keeps every bucket
                    # singular and restores the one-move-per-line behaviour.
                    None if grouped else line.id,
                )
                buckets.setdefault(key, self.env["custom.fixed.asset.depreciation.line"])
                buckets[key] |= line

        posted_count = 0
        for key in sorted(buckets, key=lambda k: (k[4], k[0], k[1])):
            company_id, journal_id, expense_id, accum_id, date, _singleton = key
            lines = buckets[key]
            total = sum(lines.mapped("amount"))
            if not total:
                continue

            if len(lines) == 1:
                asset = lines.asset_id
                ref = _(
                    "Depreciation %(code)s #%(seq)s",
                    code=asset.code,
                    seq=lines.sequence,
                )
                expense_label = _("Depreciation %(name)s", name=asset.name)
                accum_label = _("Accum. depreciation %(name)s", name=asset.name)
            else:
                ref = _(
                    "Depreciation %(date)s (%(count)s assets)",
                    date=date,
                    count=len(lines.asset_id),
                )
                expense_label = _("Depreciation %(date)s", date=date)
                accum_label = _("Accum. depreciation %(date)s", date=date)

            move = AccountMove.create(
                {
                    "date": date,
                    "journal_id": journal_id,
                    "company_id": company_id,
                    "ref": ref,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": expense_label,
                                "account_id": expense_id,
                                "debit": total,
                                "credit": 0.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": accum_label,
                                "account_id": accum_id,
                                "debit": 0.0,
                                "credit": total,
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            lines.write({"posted": True, "move_id": move.id})
            posted_count += len(lines)
        # If a schedule is fully consumed -> nothing else to do; the asset
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

    def action_post_selected(self):
        """Bulk-post every due depreciation line (as of today) for the assets
        in ``self``. Wired to a list multi-select server action.
        """
        count = self._post_due_depreciation()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if count else "warning",
                "title": _("Depreciation Posting"),
                "message": _("%(count)s depreciation entr(y/ies) posted.", count=count),
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Create with sequence
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("custom.fixed.asset")
                vals["code"] = seq or _("New")
            # Default the depreciation anchor to the acquisition date.
            if not vals.get("posting_date") and vals.get("acquisition_date"):
                vals["posting_date"] = vals["acquisition_date"]
            # A pooled asset records the quantity it was bought with; retirements
            # only ever move ``quantity`` down from there.
            if not vals.get("original_quantity"):
                vals["original_quantity"] = vals.get("quantity", 1.0)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "quantity" in vals and "original_quantity" not in vals:
            # While still draft the asset is being set up, so the original
            # quantity follows what the user types. Once running, only a
            # retirement moves the quantity and the original must stay put.
            draft = self.filtered(lambda a: a.state == "draft")
            if draft:
                super(CustomFixedAsset, draft).write({"original_quantity": vals["quantity"]})
        return res
