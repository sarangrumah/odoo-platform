# -*- coding: utf-8 -*-
"""Petty cash float — the revolving balance a store (Operating Unit) holds.

A store is granted an initial float ("Petty Cash Awal", 1.000.000 by default,
configurable by Finance). Every spend is *reserved* against that float from the
moment its request is drafted, and the reservation shrinks as the employee
realizes it.

Two different balances live on this record and they are **not** the same
number, on purpose:

``amount_available``
    The control balance Finance manages. ``granted - reserved``, where a
    reservation is ``requested - realized`` on every open Realisasi request.
    Realizing 250 of a 300 request therefore restores 250 immediately — the
    float is revolving and the realized spend is assumed replenished. This is
    the figure that gates new requests.

``amount_gl_balance``
    What the advance account actually says, summed over the OU's requests. A
    posted realization credits the advance (Dr Expense / Cr Uang Muka), so this
    drops with every realization and only returns to the plafon once the
    replenishment cash is booked. Shown for reconciliation, never used to gate.

Floats are created by Finance in Configuration, or automatically the first time
a "Petty Cash Awal" request for the OU is approved — never inside a compute, so
opening a form can never spawn records.
"""

from __future__ import annotations

from odoo import _, api, fields, models

DEFAULT_INITIAL_AMOUNT = 1000000.0


class PettyCashFloat(models.Model):
    _name = "petty.cash.float"
    _description = "Petty Cash Float per Operating Unit"
    _order = "company_id, id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    l10n_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        required=True,
        index=True,
        ondelete="restrict",
        help="The store this float belongs to.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)

    amount_plafon = fields.Monetary(
        string="Plafon Petty Cash Awal",
        currency_field="currency_id",
        default=lambda self: self._default_plafon(),
        help="Ceiling for this store's initial petty cash request. Defaults to "
        "the platform-wide figure in Petty Cash Settings (1.000.000) and can be "
        "raised or lowered per store by Finance.",
    )
    amount_granted = fields.Monetary(
        string="Granted",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Total of the store's approved 'Petty Cash Awal' requests.",
    )
    amount_reserved = fields.Monetary(
        string="Reserved",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Sum of the un-realized part of every open Realisasi request — counted from draft onwards.",
    )
    amount_available = fields.Monetary(
        string="Available",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Granted minus reserved. New Realisasi requests are gated on this.",
    )
    amount_gl_balance = fields.Monetary(
        string="GL Balance",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        help="Advance-account balance of this store's requests. Diverges from "
        "Available between a realization and its replenishment — see the "
        "module docstring.",
    )
    request_ids = fields.One2many("petty.cash.request", "float_id", string="Requests")
    request_count = fields.Integer(compute="_compute_amounts")

    _ou_company_uniq = models.Constraint(
        "unique(l10n_ou_analytic_id, company_id)",
        "One petty cash float per Operating Unit and company.",
    )

    # ------------------------------------------------------------------
    @api.model
    def _default_plafon(self):
        param = self.env["ir.config_parameter"].sudo().get_param("custom_petty_cash.initial_amount")
        try:
            return float(param) if param else DEFAULT_INITIAL_AMOUNT
        except (TypeError, ValueError):
            return DEFAULT_INITIAL_AMOUNT

    @api.depends("l10n_ou_analytic_id", "company_id")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.l10n_ou_analytic_id.display_name or _("Petty Cash Float")

    @api.depends(
        "request_ids.amount_float_granted",
        "request_ids.amount_float_consumed",
        "request_ids.amount_outstanding_company",
    )
    def _compute_amounts(self):
        for rec in self:
            requests = rec.request_ids
            rec.amount_granted = sum(requests.mapped("amount_float_granted"))
            rec.amount_reserved = sum(requests.mapped("amount_float_consumed"))
            rec.amount_available = rec.amount_granted - rec.amount_reserved
            rec.amount_gl_balance = sum(requests.mapped("amount_outstanding_company"))
            rec.request_count = len(requests)

    # ------------------------------------------------------------------
    @api.model
    def _pc_get_float(self, company, analytic, create=False):
        """Return the float for ``(company, analytic)``.

        ``create=True`` is only ever passed from an explicit user action
        (approving a Petty Cash Awal request, or the Finance form) — never from
        a compute, so merely opening a request can never spawn a float.
        """
        if not company or not analytic:
            return self.browse()
        domain = [("company_id", "=", company.id), ("l10n_ou_analytic_id", "=", analytic.id)]
        rec = self.sudo().search(domain, limit=1)
        if not rec and create:
            rec = self.sudo().create({"company_id": company.id, "l10n_ou_analytic_id": analytic.id})
        return rec

    def action_view_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Requests"),
            "res_model": "petty.cash.request",
            "domain": [("float_id", "=", self.id)],
            "view_mode": "list,form,pivot,graph",
            "context": {
                "default_l10n_ou_analytic_id": self.l10n_ou_analytic_id.id,
                "default_company_id": self.company_id.id,
            },
        }
