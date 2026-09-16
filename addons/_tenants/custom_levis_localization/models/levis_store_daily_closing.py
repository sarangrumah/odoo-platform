# -*- coding: utf-8 -*-
"""What each store took, and what it paid in, per trading day.

The report Finance reads before validating a cash deposit: for one store on one
day, what the tills counted beside what a deposit document claims was banked.

**Why this is a view and not a table.** ``pos.session`` already *is* the daily
closing — it has a state, a cash count and a difference, and a store closes it
every night. A second stateful record covering the same day would duplicate a
workflow that already exists, and duplicated workflows drift: the day would be
"closed" in one place and "open" in the other, and nobody could say which was
true. So nothing here is stored. Every figure is derived, which means it cannot
be stale and cannot disagree with its source.

If Finance later needs to write on this — a variance note, a sign-off — it
becomes a stored model and these column names become its field names unchanged.
That promotion is mechanical; doing it now would cost a table nobody had asked
for yet.

**Counted vs expected.** ``cash_counted`` is what the cashier actually counted
into the till at close (``cash_register_balance_end_real``); ``cash_expected`` is
the opening float plus the cash the orders say was taken. A gap between them is a
till problem, not a banking one, and it is reported separately from
``cash_undeposited``, which is a banking one. Neither is the receivable the
clearing consumes — that is a third number, and conflating any two of them is how
a cash difference gets blamed on the wrong team.
"""

from odoo import fields, models, tools


class LevisStoreDailyClosing(models.Model):
    _name = "levis.store.daily.closing"
    _description = "Store Daily Closing"
    _auto = False
    _rec_name = "closing_date"
    _order = "closing_date desc, store_code"

    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Store", readonly=True)
    store_code = fields.Char(readonly=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Operating Unit", readonly=True)
    closing_date = fields.Date(string="Trading Day", readonly=True)

    session_count = fields.Integer(string="Sessions", readonly=True)
    open_session_count = fields.Integer(string="Still Open", readonly=True)

    cash_counted = fields.Monetary(string="Cash Counted", readonly=True)
    cash_expected = fields.Monetary(string="Cash Expected", readonly=True)
    cash_variance = fields.Monetary(string="Till Variance", readonly=True)

    deposit_total = fields.Monetary(string="Deposited", readonly=True)
    cash_undeposited = fields.Monetary(string="Not Yet Deposited", readonly=True)

    status = fields.Selection(
        [
            ("open", "Session Open"),
            ("undeposited", "Awaiting Deposit"),
            ("ok", "Settled"),
        ],
        readonly=True,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Column notes, each of which cost a failed upgrade:
        #  * ``pos_session`` has no ``company_id`` column at all — company lives
        #    on ``pos_config``.
        #  * ``cash_register_balance_end`` is a *computed, unstored* field, so it
        #    cannot be selected. Odoo derives it as
        #    ``cash_register_balance_start + total cash payments``; that is
        #    reproduced below rather than approximated.
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS (
            WITH cash_in AS (
                SELECT p.session_id, SUM(p.amount) AS total_cash
                FROM pos_payment p
                JOIN pos_payment_method m ON m.id = p.payment_method_id
                WHERE m.is_cash_count IS TRUE
                GROUP BY p.session_id
            ),
            sess AS (
                SELECT
                    s.id                                          AS session_id,
                    c.warehouse_id                                AS warehouse_id,
                    c.company_id                                  AS company_id,
                    -- A session is banked on the day it closed, not the day it
                    -- opened: an overnight session's takings reach the bank with
                    -- the following morning's deposit.
                    COALESCE(s.stop_at, s.start_at)::date         AS closing_date,
                    s.state                                       AS state,
                    COALESCE(s.cash_register_balance_end_real, 0) AS counted,
                    COALESCE(s.cash_register_balance_start, 0)
                        + COALESCE(ci.total_cash, 0)              AS expected
                FROM pos_session s
                JOIN pos_config c ON c.id = s.config_id
                LEFT JOIN cash_in ci ON ci.session_id = s.id
                WHERE c.warehouse_id IS NOT NULL
                  AND COALESCE(s.stop_at, s.start_at) IS NOT NULL
            ),
            agg AS (
                SELECT
                    warehouse_id,
                    company_id,
                    closing_date,
                    COUNT(*)                                              AS session_count,
                    COUNT(*) FILTER (WHERE state <> 'closed')             AS open_session_count,
                    SUM(counted)                                          AS cash_counted,
                    SUM(expected)                                         AS cash_expected
                FROM sess
                GROUP BY warehouse_id, company_id, closing_date
            ),
            dep AS (
                -- A deposit covers a range of trading days, so it is spread over
                -- them rather than attributed to one. Splitting evenly is an
                -- approximation and is only ever used for presentation; nothing
                -- allocates or books from this number.
                SELECT
                    d.warehouse_id,
                    d.company_id,
                    gs.day::date                                          AS closing_date,
                    SUM(d.amount / GREATEST(
                        (d.trading_date_to - d.trading_date_from) + 1, 1)) AS deposit_total
                FROM levis_store_cash_deposit d
                CROSS JOIN LATERAL generate_series(
                    d.trading_date_from, d.trading_date_to, interval '1 day') AS gs(day)
                WHERE d.state IN ('validated', 'matched')
                GROUP BY d.warehouse_id, d.company_id, gs.day::date
            )
            SELECT
                (agg.warehouse_id::bigint * 100000
                    + (agg.closing_date - DATE '2000-01-01'))               AS id,
                agg.company_id,
                comp.currency_id,
                agg.warehouse_id,
                w.l10n_store_code                                          AS store_code,
                w.l10n_ou_analytic_id                                      AS analytic_account_id,
                agg.closing_date,
                agg.session_count,
                agg.open_session_count,
                agg.cash_counted,
                agg.cash_expected,
                agg.cash_counted - agg.cash_expected                       AS cash_variance,
                COALESCE(dep.deposit_total, 0)                             AS deposit_total,
                agg.cash_counted - COALESCE(dep.deposit_total, 0)          AS cash_undeposited,
                CASE
                    WHEN agg.open_session_count > 0 THEN 'open'
                    WHEN ABS(agg.cash_counted - COALESCE(dep.deposit_total, 0)) < 0.005 THEN 'ok'
                    ELSE 'undeposited'
                END                                                        AS status
            FROM agg
            JOIN stock_warehouse w ON w.id = agg.warehouse_id
            JOIN res_company comp  ON comp.id = agg.company_id
            LEFT JOIN dep ON dep.warehouse_id = agg.warehouse_id
                         AND dep.company_id  = agg.company_id
                         AND dep.closing_date = agg.closing_date
            )
            """
        )
