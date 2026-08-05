# -*- coding: utf-8 -*-
"""Expose petty-cash configuration in Settings."""

from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    petty_cash_advance_account_id = fields.Many2one(
        related="company_id.petty_cash_advance_account_id",
        readonly=False,
    )
    petty_cash_bank_out_journal_id = fields.Many2one(
        related="company_id.petty_cash_bank_out_journal_id",
        readonly=False,
    )
    petty_cash_payment_journal_id = fields.Many2one(
        related="company_id.petty_cash_payment_journal_id",
        readonly=False,
    )
    petty_cash_expense_journal_id = fields.Many2one(
        related="company_id.petty_cash_expense_journal_id",
        readonly=False,
    )
    petty_cash_realization_days = fields.Integer(
        string="Realization Deadline (days)",
        config_parameter="custom_petty_cash.realization_days",
        default=14,
        help="Default number of days after disbursement by which the "
        "employee must submit the realization. Drives the overdue filter "
        "and reminder cron.",
    )
    petty_cash_ou_plan_name = fields.Char(
        string="Operating Unit Analytic Plan",
        config_parameter="custom_petty_cash.ou_plan_name",
        help="Name of the analytic plan the Operating Unit field should offer "
        "on a request. Defaults to 'Operating Unit'; set it to whatever this "
        "tenant actually calls that dimension (ARKA-AIM uses 'Project'). An "
        "unknown plan name widens the field to every analytic account rather "
        "than blocking it.",
    )
    petty_cash_employee_plan_name = fields.Char(
        string="Employee Analytic Plan",
        config_parameter="custom_petty_cash.employee_plan_name",
        help="Analytic plan holding the per-employee accounts used to slice "
        "the shared advance account. Created on first use if missing.",
    )
    petty_cash_disburse_via_payment = fields.Boolean(
        string="Disburse via account.payment",
        config_parameter="custom_petty_cash.disburse_via_payment",
        default=False,
        help="When enabled, disbursement is booked through an "
        "account.payment (outbound, bank-reconcilable) instead of a direct "
        "journal entry. The advance account is used as the payment "
        "destination account.",
    )
