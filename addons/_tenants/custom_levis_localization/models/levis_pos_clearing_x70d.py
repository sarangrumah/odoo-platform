# -*- coding: utf-8 -*-
"""The X70D tender file, made browsable.

``custom_retail_import`` stages every X70D row as JSON on
``retail.import.line`` and posts it as POS orders; nothing keeps the tender rows
themselves in a form anyone can open. The clearing already reads them — see
``LevisPosClearingAlloc._x24_rows`` — but only to answer "does this amount prove
these receipts", never to show a day.

The store reconciliation needs the second thing: the settlement of day H against
the tenders the store rang up on H-1, with the transactions listed underneath.
So the very query the matcher uses is exposed as a read-only SQL view: same
extraction, same tender folding, same store resolution, one place to be wrong.

It is a **view, not a table**: nothing is copied, nothing can drift, and a
re-imported day changes here the moment it changes there. Where the retail
import was never installed the view is created empty rather than not at all —
the clearing must keep working on a database that has no feed, and a missing
model would break every screen that reads this one.
"""

from odoo import fields, models, tools

# Kept identical to ``levis_pos_clearing._X24_TENDER_FOLD``: two names for one
# acquirer bucket, and a reconciliation that folded them differently from the
# matcher would disagree with it for no reason a reader could see.
_TENDER_FOLD_SQL = """
    CASE WHEN upper(r.j ->> 'tender_type') = 'OFFLINE_OTHER_CARD'
         THEN 'OFFLINE_OTHER_CREDITCARD'
         ELSE upper(r.j ->> 'tender_type') END
"""

_SELECT = """
    SELECT s.id,
           s.company_id,
           s.analytic_account_id,
           s.pos_config_id,
           s.log_id,
           s.trans_date,
           s.tender,
           s.store_code,
           s.register,
           s.transnum,
           concat_ws('-', s.store_code, s.register, s.transnum) AS ref,
           s.amount
      FROM (
            SELECT r.id                       AS id,
                   r.company_id               AS company_id,
                   w.l10n_ou_analytic_id      AS analytic_account_id,
                   c.id                       AS pos_config_id,
                   r.log_id                   AS log_id,
                   -- A staged row may carry an empty transaction date. The CASE
                   -- is what keeps the cast from ever seeing it: a bare WHERE
                   -- would be free to run after the cast and blow up.
                   CASE WHEN r.j ->> 'trans_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                        THEN (r.j ->> 'trans_date')::date END AS trans_date,
                   %(fold)s                   AS tender,
                   r.j ->> 'store_code'       AS store_code,
                   r.j ->> 'register'         AS register,
                   r.j ->> 'transnum'         AS transnum,
                   CASE WHEN r.j ->> 'tender_amount' ~ '^-?[0-9]+([.][0-9]+)?$'
                        THEN (r.j ->> 'tender_amount')::numeric END AS amount
              FROM (SELECT l.id, l.log_id, p.company_id, l.raw_data_json::json AS j
                      FROM retail_import_line l
                      JOIN retail_import_log g ON g.id = l.log_id
                      JOIN retail_import_profile p ON p.id = g.profile_id
                     WHERE p.file_type = 'x70d'
                       AND l.raw_data_json IS NOT NULL
                       AND l.raw_data_json LIKE '{%%') r
              JOIN ir_model_data d
                ON d.model = 'pos.config'
               AND d.name = 'posconfig_' || (r.j ->> 'store_code')
              JOIN pos_config c ON c.id = d.res_id
              JOIN stock_warehouse w ON w.id = c.warehouse_id
           ) s
     WHERE s.trans_date IS NOT NULL
       AND s.amount IS NOT NULL
"""

# What the view is when there is no feed to read: the right columns, no rows.
_SELECT_EMPTY = """
    SELECT NULL::integer   AS id,
           NULL::integer   AS company_id,
           NULL::integer   AS analytic_account_id,
           NULL::integer   AS pos_config_id,
           NULL::integer   AS log_id,
           NULL::date      AS trans_date,
           NULL::varchar   AS tender,
           NULL::varchar   AS store_code,
           NULL::varchar   AS register,
           NULL::varchar   AS transnum,
           NULL::varchar   AS ref,
           NULL::numeric   AS amount
     WHERE FALSE
"""


class LevisPosX70dTxn(models.Model):
    _name = "levis.pos.x70d.txn"
    _description = "X70D Tender Transaction"
    _auto = False
    _order = "trans_date desc, store_code, register, transnum"
    _rec_name = "ref"

    ref = fields.Char(string="Transaction No.", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Store Operating Unit",
        readonly=True,
        help="Resolved from the store code through its POS configuration and warehouse — the same route the matcher takes.",
    )
    pos_config_id = fields.Many2one("pos.config", string="POS", readonly=True)
    log_id = fields.Many2one("retail.import.log", string="Import", readonly=True)
    trans_date = fields.Date(string="Trading Day", readonly=True)
    tender = fields.Char(readonly=True)
    store_code = fields.Char(readonly=True)
    register = fields.Char(readonly=True)
    transnum = fields.Char(string="Trans. No.", readonly=True)
    amount = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        string="Currency",
    )

    def _compute_currency_id(self):
        for txn in self:
            txn.currency_id = (txn.company_id or self.env.company).currency_id

    def init(self):
        self.env.cr.execute(
            "SELECT to_regclass('retail_import_line'), "
            "       to_regclass('retail_import_log'), "
            "       to_regclass('retail_import_profile')"
        )
        staged = all(self.env.cr.fetchone())
        tools.drop_view_if_exists(self.env.cr, self._table)
        select = (_SELECT % {"fold": _TENDER_FOLD_SQL}) if staged else _SELECT_EMPTY
        self.env.cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({select})")
