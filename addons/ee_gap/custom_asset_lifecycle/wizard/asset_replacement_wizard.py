# -*- coding: utf-8 -*-
"""Register a replacement unit handed over by a client, at fair value.

Two distinct accounting events, deliberately kept apart:

1. **Derecognition of the old unit** -- the disposal wizard, proceeds zero, loss
   equal to net book value. Not done here; ``action_open_writeoff_wizard`` on
   the asset routes to it.
2. **Recognition of the replacement** -- what this wizard does. The unit becomes
   company property, so it is capitalised at fair market value with the credit
   going to compensation income.

Why the journal is posted here rather than left to the register: creating a
``custom.fixed.asset`` posts **nothing**. Assets normally reach the GL through
the vendor bill behind ``custom_asset_from_receipt``, and a unit handed over by a
client has no vendor bill. Skip the entry and the register grows while the GL
stands still -- register-vs-GL drift that nobody notices until a reconciliation
months later.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AssetReplacementWizard(models.TransientModel):
    _name = "custom.asset.replacement.wizard"
    _description = "Register Replacement Asset"

    replaced_asset_id = fields.Many2one(
        comodel_name="custom.fixed.asset",
        string="Replaced Asset",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(related="replaced_asset_id.company_id", readonly=True)
    currency_id = fields.Many2one(related="replaced_asset_id.currency_id", readonly=True)
    replaced_net_book_value = fields.Monetary(
        related="replaced_asset_id.net_book_value",
        string="NBV of Replaced Unit",
        readonly=True,
        currency_field="currency_id",
    )
    replaced_state = fields.Selection(related="replaced_asset_id.state", readonly=True)
    replaced_condition = fields.Selection(related="replaced_asset_id.condition", readonly=True)

    name = fields.Char(string="Asset Name", required=True)
    code = fields.Char(
        string="Asset Code",
        help="Leave empty to draw the next number from the register sequence.",
    )
    serial_number = fields.Char(string="Serial Number")
    acquisition_date = fields.Date(
        string="Handover Date",
        required=True,
        default=fields.Date.context_today,
        help="Date the replacement unit was received. Depreciation starts here, "
        "over a full useful life -- this is a new unit, not the remaining life "
        "of the one it replaces.",
    )
    market_value = fields.Monetary(
        string="Fair Market Value",
        required=True,
        currency_field="currency_id",
        help="Value the replacement is capitalised at.",
    )
    group_id = fields.Many2one(comodel_name="custom.fixed.asset.group", string="Asset Group")
    location_id = fields.Many2one(comodel_name="custom.fixed.asset.location", string="Asset Location")
    custodian_id = fields.Many2one(comodel_name="res.partner", string="Custodian")
    useful_life_months = fields.Integer(string="Useful Life (months)", required=True, default=48)

    replacement_reason = fields.Selection(
        selection=[("damage", "Beyond Repair"), ("missing", "Lost / Missing")],
        required=True,
    )
    claim_ref = fields.Char(string="Client Claim Ref.")

    post_journal_entry = fields.Boolean(
        string="Post Acquisition Entry",
        default=True,
        help="Debit the asset account and credit compensation income at fair value. "
        "Untick ONLY when the entry has already been booked by hand -- otherwise "
        "the register and the general ledger will disagree.",
    )
    income_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Compensation Income Account",
        default=lambda self: self.env.company.asset_compensation_income_account_id,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Journal",
        domain="[('type', '=', 'general')]",
        default=lambda self: self.env.company.asset_replacement_journal_id,
    )
    confirm_asset = fields.Boolean(
        string="Confirm And Start Depreciating",
        default=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        asset = self.env["custom.fixed.asset"].browse(
            res.get("replaced_asset_id") or self.env.context.get("default_replaced_asset_id")
        )
        if not asset:
            return res
        res.setdefault("name", asset.name)
        res.setdefault("group_id", asset.group_id.id)
        res.setdefault("location_id", asset.location_id.id)
        res.setdefault("custodian_id", asset.custodian_id.id)
        res.setdefault("useful_life_months", asset.useful_life_months or 48)
        res.setdefault("replacement_reason", "missing" if asset.condition in ("missing", "written_off") else "damage")
        return res

    # ------------------------------------------------------------------
    def action_register(self):
        self.ensure_one()
        old = self.replaced_asset_id
        if old.replaced_by_asset_id:
            raise UserError(
                _(
                    "Asset %(code)s has already been replaced by %(new)s.",
                    code=old.code,
                    new=old.replaced_by_asset_id.code,
                )
            )
        if self.market_value <= 0:
            raise UserError(_("Fair market value must be greater than zero."))
        if self.post_journal_entry and not self.income_account_id:
            raise UserError(
                _(
                    "A compensation income account is required to post the acquisition "
                    "entry. Set it under Accounting Settings > Asset Lifecycle."
                )
            )

        new_asset = self._create_replacement()
        move = self._post_acquisition_move(new_asset) if self.post_journal_entry else False
        if move:
            new_asset.replacement_move_id = move

        if self.confirm_asset and new_asset.state == "draft":
            new_asset.action_confirm()

        old._log_condition_event(
            "replaced",
            description=_(
                "Replaced by %(code)s, capitalised at fair value %(value)s.",
                code=new_asset.code,
                value=self.market_value,
            ),
            event_date=self.acquisition_date,
            reference=self.claim_ref,
            replacement_asset_id=new_asset.id,
            move_id=move.id if move else None,
        )
        new_asset.message_post(
            body=_(
                "Registered as the replacement for asset %(code)s (%(reason)s), at fair "
                "market value. Client claim reference: %(ref)s",
                code=old.code,
                reason=dict(self._fields["replacement_reason"].selection).get(self.replacement_reason),
                ref=self.claim_ref or "-",
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Replacement Asset"),
            "res_model": "custom.fixed.asset",
            "res_id": new_asset.id,
            "view_mode": "form",
        }

    def _create_replacement(self):
        self.ensure_one()
        old = self.replaced_asset_id
        group = self.group_id or old.group_id
        vals = {
            "name": self.name,
            "code": self.code or _("New"),
            "company_id": old.company_id.id,
            "acquisition_date": self.acquisition_date,
            "posting_date": self.acquisition_date,
            "acquisition_value": self.market_value,
            "useful_life_months": self.useful_life_months,
            "depreciation_method": old.depreciation_method or "straight_line",
            "group_id": group.id,
            "location_id": (self.location_id or old.location_id).id,
            "custodian_id": (self.custodian_id or old.custodian_id).id,
            "serial_number": self.serial_number,
            "replaces_asset_id": old.id,
            "replacement_reason": self.replacement_reason,
            "replacement_claim_ref": self.claim_ref,
            # Account wiring is not filled in by onchange when creating in code,
            # so take it from the group, falling back to the replaced unit --
            # a replacement is booked exactly where its predecessor was.
            "asset_account_id": (group.default_asset_account_id or old.asset_account_id).id,
            "depreciation_account_id": (group.default_depreciation_account_id or old.depreciation_account_id).id,
            "expense_account_id": (group.default_expense_account_id or old.expense_account_id).id,
            "journal_id": (group.default_journal_id or old.journal_id).id,
        }
        return self.env["custom.fixed.asset"].create(vals)

    def _post_acquisition_move(self, new_asset):
        """DR fixed asset / CR compensation income, at fair value."""
        self.ensure_one()
        if not new_asset.asset_account_id:
            raise UserError(
                _("No asset account resolved for %(code)s -- set one on its asset group.", code=new_asset.code)
            )
        journal = self.journal_id or new_asset.journal_id
        if not journal:
            raise UserError(
                _(
                    "No journal for the acquisition entry. Set an asset replacement "
                    "journal under Accounting Settings > Asset Lifecycle."
                )
            )
        label = _("Replacement of %(code)s", code=self.replaced_asset_id.code)
        move = self.env["account.move"].create(
            {
                "date": self.acquisition_date,
                "journal_id": journal.id,
                "company_id": new_asset.company_id.id,
                "ref": _("Asset replacement %(code)s", code=new_asset.code),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": label,
                            "account_id": new_asset.asset_account_id.id,
                            "debit": self.market_value,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": label,
                            "account_id": self.income_account_id.id,
                            "debit": 0.0,
                            "credit": self.market_value,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move
