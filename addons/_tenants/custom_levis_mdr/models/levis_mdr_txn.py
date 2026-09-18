# -*- coding: utf-8 -*-
"""Every nightly X70D transaction, with the acquirer label and the fee it implies.

Three sources meet here, and each answers something the others cannot:

* the **nightly X70D** says what was tendered, for all 22 stores, every night. It
  is the population -- one row per card transaction -- and it is the only source
  that is complete;
* the **store's own X70D export** says *which* acquirer and product, in its
  ``PAYMENT`` column. The nightly file heads that column ``AUTH NUMBER`` and
  leaves it empty in every row, so this is the only place the pair that decides a
  rate exists. It arrives weekly and covers only the stores that send it;
* ``levis.mdr.rate`` turns the label into a percentage, as of the trading day.

A transaction whose store has not sent its export keeps ``payment`` and
``mdr_amount`` **null**. That is deliberate and it is the whole point of the
model: a missing rate must read as "not known", never as a free transaction. Null
also propagates through SUM, so a store-day total that includes an unlabelled
transaction is null rather than quietly short.

Matching is on ``store_code + trans_date + register + transnum`` -- the
transaction's own identity, not a surrogate. Stores resend the whole month every
week, so the same transaction is staged many times; ``DISTINCT ON`` takes the
most recently imported row, which is also what lets a store correct a week by
sending it again.
"""

from odoo import fields, models, tools

#: One nightly X70D row per card transaction, extracted the way
#: ``levis.pos.x70d.txn`` extracts it. Read straight from the staged JSON rather
#: than from that view: the view belongs to another module and gains columns, and
#: a view built on a view cannot survive its parent being dropped and recreated.
_NIGHTLY = """
    SELECT l.id                       AS id,
           p.company_id               AS company_id,
           r.j ->> 'store_code'       AS store_code,
           r.j ->> 'register'         AS register,
           r.j ->> 'transnum'         AS transnum,
           upper(r.j ->> 'tender_type') AS tender_type,
           CASE WHEN r.j ->> 'trans_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                THEN (r.j ->> 'trans_date')::date END AS trans_date,
           CASE WHEN r.j ->> 'tender_amount' ~ '^-?[0-9]+([.][0-9]+)?$'
                THEN (r.j ->> 'tender_amount')::numeric END AS amount
      FROM retail_import_line l
      JOIN retail_import_log g ON g.id = l.log_id
      JOIN retail_import_profile p ON p.id = g.profile_id
      CROSS JOIN LATERAL (SELECT l.raw_data_json::json AS j) r
     WHERE p.file_type = 'x70d'
       AND l.raw_data_json IS NOT NULL
       AND l.raw_data_json LIKE '{%'
"""

#: The store export, one row per transaction: the most recently imported copy.
_STORE = """
    SELECT DISTINCT ON (store_code, trans_date, register, transnum)
           store_code, trans_date, register, transnum, payment, appr_code, line_id
      FROM (
            SELECT l.id                   AS line_id,
                   r.j ->> 'store_code'   AS store_code,
                   r.j ->> 'register'     AS register,
                   r.j ->> 'transnum'     AS transnum,
                   nullif(btrim(r.j ->> 'payment'), '')   AS payment,
                   nullif(btrim(r.j ->> 'appr_code'), '') AS appr_code,
                   CASE WHEN r.j ->> 'trans_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                        THEN (r.j ->> 'trans_date')::date END AS trans_date
              FROM retail_import_line l
              JOIN retail_import_log g ON g.id = l.log_id
              JOIN retail_import_profile p ON p.id = g.profile_id
              CROSS JOIN LATERAL (SELECT l.raw_data_json::json AS j) r
             WHERE p.file_type = 'x70d_store'
               AND l.raw_data_json IS NOT NULL
               AND l.raw_data_json LIKE '{%'
           ) q
     WHERE store_code IS NOT NULL AND trans_date IS NOT NULL
     ORDER BY store_code, trans_date, register, transnum, line_id DESC
"""

_SELECT = """
    WITH nightly AS (%(nightly)s), store AS (%(store)s)
    SELECT n.id,
           n.company_id,
           n.trans_date,
           n.store_code,
           n.register,
           n.transnum,
           n.tender_type,
           n.amount,
           concat_ws('-', n.store_code, n.register, n.transnum) AS ref,
           w.l10n_ou_analytic_id AS analytic_account_id,
           c.id                  AS pos_config_id,
           s.payment,
           -- The stores write 0 in APPR CODE on a cash line to mean "none".
           nullif(s.appr_code, '0') AS appr_code,
           rt.id                 AS rate_id,
           rt.percent            AS mdr_percent,
           -- Null, not zero, when no rate resolves: an unlabelled transaction is
           -- unknown, not free, and null keeps a SUM honest about it.
           CASE WHEN rt.id IS NOT NULL
                THEN round((n.amount * rt.percent / 100.0)::numeric, 2) + coalesce(rt.fixed_fee, 0) END AS mdr_amount,
           CASE WHEN rt.id IS NOT NULL
                THEN n.amount - (round((n.amount * rt.percent / 100.0)::numeric, 2) + coalesce(rt.fixed_fee, 0)) END AS net_settlement
      FROM nightly n
      LEFT JOIN store s
             ON s.store_code = n.store_code
            AND s.trans_date = n.trans_date
            AND s.register   = n.register
            AND s.transnum   = n.transnum
      LEFT JOIN LATERAL (
            SELECT r.id, r.percent, r.fixed_fee
              FROM levis_mdr_rate r
             WHERE r.active
               AND s.payment IS NOT NULL
               AND upper(btrim(r.payment)) = upper(btrim(s.payment))
               AND r.company_id = n.company_id
               AND (r.date_from IS NULL OR r.date_from <= n.trans_date)
               AND (r.date_to   IS NULL OR r.date_to   >= n.trans_date)
             ORDER BY r.date_from DESC NULLS LAST, r.id DESC
             LIMIT 1
           ) rt ON TRUE
      LEFT JOIN ir_model_data d
             ON d.model = 'pos.config'
            AND d.name = 'posconfig_' || n.store_code
      LEFT JOIN pos_config c ON c.id = d.res_id
      LEFT JOIN stock_warehouse w ON w.id = c.warehouse_id
     WHERE n.trans_date IS NOT NULL
       AND n.amount IS NOT NULL
"""

#: The right columns and no rows, for a database with no retail feed at all. A
#: missing model would break every screen that reads this one.
_SELECT_EMPTY = """
    SELECT NULL::integer AS id, NULL::integer AS company_id, NULL::date AS trans_date,
           NULL::varchar AS store_code, NULL::varchar AS register, NULL::varchar AS transnum,
           NULL::varchar AS tender_type, NULL::numeric AS amount, NULL::varchar AS ref,
           NULL::integer AS analytic_account_id, NULL::integer AS pos_config_id,
           NULL::varchar AS payment, NULL::varchar AS appr_code, NULL::integer AS rate_id,
           NULL::double precision AS mdr_percent, NULL::numeric AS mdr_amount,
           NULL::numeric AS net_settlement
     WHERE FALSE
"""


class LevisMdrTxn(models.Model):
    _name = "levis.mdr.txn"
    _description = "Card Transaction MDR"
    _auto = False
    _order = "trans_date desc, store_code, register, transnum"
    _rec_name = "ref"

    ref = fields.Char(string="Transaction No.", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    trans_date = fields.Date(string="Trading Day", readonly=True)
    store_code = fields.Char(readonly=True)
    register = fields.Char(readonly=True)
    transnum = fields.Char(string="Trans. No.", readonly=True)
    tender_type = fields.Char(
        readonly=True, help="From the nightly file. Too coarse to price: one value spans several rates."
    )
    pos_config_id = fields.Many2one("pos.config", string="POS", readonly=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Store Operating Unit", readonly=True)
    payment = fields.Char(
        string="Tender Type (acquirer)",
        readonly=True,
        help="From the store's own X70D export. Empty means that store has not sent the week covering this day.",
    )
    appr_code = fields.Char(string="Approval Code", readonly=True)
    rate_id = fields.Many2one("levis.mdr.rate", string="Rate Applied", readonly=True)
    mdr_percent = fields.Float(string="MDR %", digits=(16, 4), readonly=True)
    amount = fields.Monetary(string="Gross", currency_field="currency_id", readonly=True)
    mdr_amount = fields.Monetary(string="MDR", currency_field="currency_id", readonly=True)
    net_settlement = fields.Monetary(
        string="Expected Settlement",
        currency_field="currency_id",
        readonly=True,
        help="Gross less MDR: what the acquirer should pay for this transaction.",
    )
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id", string="Currency")

    def _compute_currency_id(self):
        for txn in self:
            txn.currency_id = (txn.company_id or self.env.company).currency_id

    def init(self):
        self.env.cr.execute(
            "SELECT to_regclass('retail_import_line'), "
            "       to_regclass('retail_import_log'), "
            "       to_regclass('retail_import_profile'), "
            "       to_regclass('levis_mdr_rate')"
        )
        ready = all(self.env.cr.fetchone())
        tools.drop_view_if_exists(self.env.cr, self._table)
        select = (_SELECT % {"nightly": _NIGHTLY, "store": _STORE}) if ready else _SELECT_EMPTY
        self.env.cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({select})")
