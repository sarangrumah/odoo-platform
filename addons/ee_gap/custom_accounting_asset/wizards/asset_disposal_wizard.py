# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CustomFixedAssetDisposalWizard(models.TransientModel):
    _name = "custom.fixed.asset.disposal.wizard"
    _description = "Custom Fixed Asset Disposal Wizard"

    asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="asset_id.currency_id",
        readonly=True,
    )
    net_book_value = fields.Monetary(
        related="asset_id.net_book_value",
        readonly=True,
        currency_field="currency_id",
    )
    disposal_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
    )
    disposal_value = fields.Monetary(
        string="Sale / Disposal Proceeds",
        required=True,
        default=0.0,
        currency_field="currency_id",
        help="Amount received from the sale. Zero if the asset is written off.",
    )
    gain_loss = fields.Monetary(
        string="Gain / (Loss)",
        compute="_compute_gain_loss",
        currency_field="currency_id",
    )
    gain_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Gain Account",
        help="Account to credit when proceeds exceed NBV.",
    )
    loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Loss Account",
        help="Account to debit when proceeds fall short of NBV.",
    )
    receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Proceeds Account",
        help="Receivable / bank account that will be debited for the proceeds.",
    )
    create_journal_entry = fields.Boolean(
        default=True,
        help="If checked, a journal entry will be generated that retires the "
        "asset cost, reverses accumulated depreciation, books proceeds, "
        "and records gain/loss.",
    )
    note = fields.Text()

    @api.depends("disposal_value", "asset_id.net_book_value")
    def _compute_gain_loss(self):
        for wiz in self:
            wiz.gain_loss = (wiz.disposal_value or 0.0) - (wiz.asset_id.net_book_value or 0.0)

    def action_dispose(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state != "running":
            raise UserError(_("Only running assets can be disposed."))

        move = False
        if self.create_journal_entry:
            move = self._create_disposal_move()

        asset.write(
            {
                "state": "disposed",
                "disposal_date": self.disposal_date,
                "disposal_value": self.disposal_value,
                "disposal_gain_loss": self.gain_loss,
                "disposal_move_id": move.id if move else False,
            }
        )
        asset.message_post(
            body=_(
                "Asset disposed on %(date)s. Proceeds: %(value)s, gain/(loss): %(gain)s. %(note)s",
                date=self.disposal_date,
                value=self.disposal_value,
                gain=self.gain_loss,
                note=self.note or "",
            )
        )
        return {"type": "ir.actions.act_window_close"}

    def _create_disposal_move(self):
        """Create a balanced disposal journal entry:
        DR Accumulated depreciation       (release accumulated)
        DR Proceeds account               (sale amount)
        DR Loss account (if loss)
              CR Asset account            (release asset cost)
              CR Gain account (if gain)
        """
        self.ensure_one()
        asset = self.asset_id
        if not asset.asset_account_id or not asset.depreciation_account_id:
            raise UserError(
                _("Asset and accumulated depreciation accounts must be set on the asset to post a disposal entry.")
            )
        if self.disposal_value and not self.receivable_account_id:
            raise UserError(_("Proceeds account is required when disposal value > 0."))
        if self.gain_loss > 0 and not self.gain_account_id:
            raise UserError(_("Gain account is required when proceeds exceed NBV."))
        if self.gain_loss < 0 and not self.loss_account_id:
            raise UserError(_("Loss account is required when proceeds fall short of NBV."))

        accum = asset.accumulated_depreciation
        cost = asset.acquisition_value
        proceeds = self.disposal_value
        gain = self.gain_loss

        lines = []
        if accum:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Release accum. depreciation"),
                        "account_id": asset.depreciation_account_id.id,
                        "debit": accum,
                        "credit": 0.0,
                    },
                )
            )
        if proceeds:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Disposal proceeds"),
                        "account_id": self.receivable_account_id.id,
                        "debit": proceeds,
                        "credit": 0.0,
                    },
                )
            )
        if gain < 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Loss on disposal"),
                        "account_id": self.loss_account_id.id,
                        "debit": abs(gain),
                        "credit": 0.0,
                    },
                )
            )
        lines.append(
            (
                0,
                0,
                {
                    "name": _("Release asset cost"),
                    "account_id": asset.asset_account_id.id,
                    "debit": 0.0,
                    "credit": cost,
                },
            )
        )
        if gain > 0:
            lines.append(
                (
                    0,
                    0,
                    {
                        "name": _("Gain on disposal"),
                        "account_id": self.gain_account_id.id,
                        "debit": 0.0,
                        "credit": gain,
                    },
                )
            )

        move = self.env["account.move"].create(
            {
                "date": self.disposal_date,
                "journal_id": asset.journal_id.id,
                "company_id": asset.company_id.id,
                "ref": _("Disposal %(code)s", code=asset.code),
                "line_ids": lines,
            }
        )
        move.action_post()
        return move
