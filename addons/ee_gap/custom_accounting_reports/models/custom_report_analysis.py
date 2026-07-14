# -*- coding: utf-8 -*-
"""Journal-item analysis cube ("GL Analysis").

A read-only ``_auto = False`` SQL view over ``account_move_line`` that
powers a native Odoo pivot/graph/list experience — the accounting
equivalent of *Purchase Analysis*. One row per journal item; the
groupable dimensions (account, account type, journal, partner, company,
period) and the summable measures (debit, credit, balance) let users
slice the ledger interactively without leaving the browser.

Note on the account *code*: in Odoo 19 ``account.account.code`` is
company-dependent (stored in ``code_store`` JSONB keyed by company), so a
plain SQL view cannot expose it correctly. We deliberately group by
``account_id`` instead — its m2o display name (``[code] name``) is
resolved per-company by the ORM. See memory
``odoo19-company-dependent-account-code``.
"""

from odoo import fields, models, tools


class CustomReportJournalItemAnalysis(models.Model):
    _name = "custom.report.journal.item.analysis"
    _description = "GL Analysis"
    _auto = False
    _order = "date desc"
    _rec_name = "account_id"

    date = fields.Date(string="Date", readonly=True)
    account_id = fields.Many2one("account.account", string="Account", readonly=True)
    account_type = fields.Selection(
        selection=lambda self: self.env["account.account"]._fields["account_type"].selection,
        string="Account Type",
        readonly=True,
    )
    journal_id = fields.Many2one("account.journal", string="Journal", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Partner", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    parent_state = fields.Char(string="Status", readonly=True)

    debit = fields.Float(string="Debit", readonly=True, aggregator="sum")
    credit = fields.Float(string="Credit", readonly=True, aggregator="sum")
    balance = fields.Float(string="Balance", readonly=True, aggregator="sum")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS
            SELECT
                aml.id            AS id,
                aml.date          AS date,
                aml.account_id    AS account_id,
                acc.account_type  AS account_type,
                aml.journal_id    AS journal_id,
                aml.partner_id    AS partner_id,
                aml.company_id    AS company_id,
                aml.move_id       AS move_id,
                aml.parent_state  AS parent_state,
                aml.debit         AS debit,
                aml.credit        AS credit,
                aml.balance       AS balance
            FROM account_move_line aml
            JOIN account_account acc ON acc.id = aml.account_id
            WHERE aml.account_id IS NOT NULL
            """
        )
