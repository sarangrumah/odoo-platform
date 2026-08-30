# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CustomFixedAssetPartialDisposalWizard(models.TransientModel):
    """Retire part of a pooled asset.

    A pooled asset carries N units under one code (5 waste bins bought on one
    non-trade PO, say). When one breaks, its share of the cost and of the
    accumulated depreciation is released to the GL, the asset shrinks to 4 units
    and the remaining schedule is rebuilt so every following month depreciates
    four bins instead of five.
    """

    _name = "custom.fixed.asset.partial.disposal.wizard"
    _description = "Custom Fixed Asset Partial Retirement Wizard"

    def _default_asset(self):
        return self.env["custom.fixed.asset"].browse(self.env.context.get("default_asset_id"))

    def _default_surplus_account(self):
        asset = self._default_asset()
        if not asset:
            return False
        reval = asset.revaluation_ids.filtered("surplus_account_id")[:1]
        if reval:
            return reval.surplus_account_id.id
        return asset.group_id.default_revaluation_surplus_account_id.id if asset.group_id else False

    def _default_retained_earnings(self):
        asset = self._default_asset()
        grp = asset.group_id if asset else False
        return grp.default_retained_earnings_account_id.id if grp else False

    asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(related="asset_id.currency_id", readonly=True)
    asset_quantity = fields.Float(
        string="Units Held",
        related="asset_id.quantity",
        readonly=True,
    )
    unit_acquisition_value = fields.Monetary(
        string="Value per Unit",
        related="asset_id.unit_acquisition_value",
        readonly=True,
        currency_field="currency_id",
    )
    quantity = fields.Float(
        string="Units to Retire",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )
    disposal_date = fields.Date(required=True, default=fields.Date.context_today)
    reason = fields.Selection(
        selection=[
            ("scrap", "Broken / scrapped"),
            ("sale", "Sold"),
            ("loss", "Lost / stolen"),
            ("transfer", "Transferred out"),
            ("other", "Other"),
        ],
        default="scrap",
        required=True,
    )
    proceeds = fields.Monetary(
        string="Proceeds",
        default=0.0,
        currency_field="currency_id",
        help="Amount received for the retired units. Zero when they are simply written off.",
    )
    cost_removed = fields.Monetary(
        compute="_compute_amounts",
        currency_field="currency_id",
        string="Cost Removed",
    )
    accumulated_removed = fields.Monetary(
        compute="_compute_amounts",
        currency_field="currency_id",
        string="Accum. Depreciation Removed",
    )
    net_book_value_removed = fields.Monetary(
        compute="_compute_amounts",
        currency_field="currency_id",
        string="NBV Removed",
    )
    gain_loss = fields.Monetary(
        compute="_compute_amounts",
        currency_field="currency_id",
        string="Gain / (Loss)",
    )
    quantity_after = fields.Float(
        compute="_compute_amounts",
        string="Units Remaining",
        digits="Product Unit of Measure",
    )
    receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Proceeds Account",
        help="Receivable / bank account debited for the proceeds.",
    )
    gain_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Gain Account",
    )
    loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Loss Account",
        help="Account debited for the written-off net book value of the retired units.",
    )
    surplus_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Revaluation Surplus Account",
        default=_default_surplus_account,
    )
    retained_earnings_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Retained Earnings Account",
        default=_default_retained_earnings,
    )
    create_journal_entry = fields.Boolean(
        default=True,
        help="If checked, a journal entry releases the retired units' cost and "
        "accumulated depreciation and books the gain/loss.",
    )
    note = fields.Text()

    @api.depends("quantity", "proceeds", "asset_id")
    def _compute_amounts(self):
        for wiz in self:
            asset = wiz.asset_id
            qty = wiz.quantity or 0.0
            if not asset or qty <= 0 or qty > (asset.quantity or 0.0):
                wiz.cost_removed = 0.0
                wiz.accumulated_removed = 0.0
                wiz.net_book_value_removed = 0.0
                wiz.gain_loss = 0.0
                wiz.quantity_after = (asset.quantity or 0.0) - qty if asset else 0.0
                continue
            split = asset._partial_retirement_split(qty)
            wiz.cost_removed = split["cost"]
            wiz.accumulated_removed = split["accumulated_depreciation"]
            wiz.net_book_value_removed = split["net_book_value"]
            wiz.gain_loss = (wiz.proceeds or 0.0) - split["net_book_value"]
            wiz.quantity_after = asset.quantity - qty

    def action_retire(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state != "running":
            raise UserError(_("Only running assets can have units retired."))
        split = asset._partial_retirement_split(self.quantity)
        quantity_before = asset.quantity
        gain_loss = (self.proceeds or 0.0) - split["net_book_value"]

        move = self._create_retirement_move(split, gain_loss) if self.create_journal_entry else False
        asset._apply_partial_retirement(split, self.disposal_date, self.proceeds, gain_loss, move)

        record = self.env["custom.fixed.asset.partial.disposal"].create(
            {
                "name": "%s/RET/%s" % (asset.code, len(asset.partial_disposal_ids) + 1),
                "asset_id": asset.id,
                "disposal_date": self.disposal_date,
                "reason": self.reason,
                "quantity": self.quantity,
                "quantity_before": quantity_before,
                "quantity_after": 0.0 if split["full"] else asset.quantity,
                "cost_removed": split["cost"],
                "accumulated_removed": split["accumulated_depreciation"],
                "net_book_value_removed": split["net_book_value"],
                "proceeds": self.proceeds,
                "gain_loss": gain_loss,
                "move_id": move.id if move else False,
                "note": self.note,
            }
        )
        asset.message_post(
            body=_(
                "%(qty)s unit(s) retired on %(date)s (%(reason)s). Cost removed: "
                "%(cost)s, accumulated depreciation released: %(accum)s, gain/(loss): "
                "%(gain)s. Remaining quantity: %(left)s.",
                qty=self.quantity,
                date=self.disposal_date,
                reason=dict(self._fields["reason"].selection).get(self.reason, self.reason),
                cost=split["cost"],
                accum=split["accumulated_depreciation"],
                gain=gain_loss,
                left=0 if split["full"] else asset.quantity,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Partial Retirement"),
            "res_model": "custom.fixed.asset.partial.disposal",
            "res_id": record.id,
            "view_mode": "form",
            "target": "current",
        }

    def _create_retirement_move(self, split, gain_loss):
        """Balanced entry releasing the retired units:

        DR Accumulated depreciation   (their share of accumulated)
        DR Proceeds account           (sale amount, if any)
        DR Loss account               (if proceeds < NBV released)
              CR Asset account        (their share of the carrying amount)
              CR Gain account         (if proceeds > NBV released)
        """
        self.ensure_one()
        asset = self.asset_id
        if not asset.asset_account_id or not asset.depreciation_account_id:
            raise UserError(
                _("Asset and accumulated depreciation accounts must be set on the asset to post a retirement entry.")
            )
        if not asset.journal_id:
            raise UserError(_("A depreciation journal must be set on the asset to post a retirement entry."))
        if self.proceeds and not self.receivable_account_id:
            raise UserError(_("Proceeds account is required when proceeds > 0."))
        if gain_loss > 0 and not self.gain_account_id:
            raise UserError(_("Gain account is required when proceeds exceed the net book value released."))
        if gain_loss < 0 and not self.loss_account_id:
            raise UserError(_("Loss account is required when proceeds fall short of the net book value released."))
        surplus = split["surplus"]
        if surplus > 0 and (not self.surplus_account_id or not self.retained_earnings_account_id):
            raise UserError(
                _(
                    "The retired units carry a revaluation surplus of %(amount)s. A "
                    "revaluation surplus account and a retained earnings account are "
                    "required to transfer it.",
                    amount=surplus,
                )
            )

        lines = []
        if split["accumulated_depreciation"]:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Release accum. depreciation (%(qty)s unit)", qty=self.quantity),
                        "account_id": asset.depreciation_account_id.id,
                        "debit": split["accumulated_depreciation"],
                        "credit": 0.0,
                    },
                )
            )
        if self.proceeds:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Retirement proceeds"),
                        "account_id": self.receivable_account_id.id,
                        "debit": self.proceeds,
                        "credit": 0.0,
                    },
                )
            )
        if gain_loss < 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Loss on retirement"),
                        "account_id": self.loss_account_id.id,
                        "debit": abs(gain_loss),
                        "credit": 0.0,
                    },
                )
            )
        lines.append(
            (
                0,
                0,
                {
                    "name": _("Release asset cost (%(qty)s unit)", qty=self.quantity),
                    "account_id": asset.asset_account_id.id,
                    "debit": 0.0,
                    "credit": split["cost"],
                },
            )
        )
        if gain_loss > 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Gain on retirement"),
                        "account_id": self.gain_account_id.id,
                        "debit": 0.0,
                        "credit": gain_loss,
                    },
                )
            )
        # IAS 16.41 — the surplus attached to the retired units moves to retained
        # earnings, never through P&L. Balanced within itself.
        if surplus > 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Release revaluation surplus"),
                        "account_id": self.surplus_account_id.id,
                        "debit": surplus,
                        "credit": 0.0,
                    },
                )
            )
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Revaluation surplus to retained earnings"),
                        "account_id": self.retained_earnings_account_id.id,
                        "debit": 0.0,
                        "credit": surplus,
                    },
                )
            )

        move = self.env["account.move"].create(
            {
                "date": self.disposal_date,
                "journal_id": asset.journal_id.id,
                "company_id": asset.company_id.id,
                "ref": _(
                    "Partial retirement %(code)s (%(qty)s unit)",
                    code=asset.code,
                    qty=self.quantity,
                ),
                "line_ids": lines,
            }
        )
        move.action_post()
        return move
