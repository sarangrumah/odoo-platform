# -*- coding: utf-8 -*-
"""Expose the Operating Unit on the GL Analysis cube.

The base view digs the unit's *analytic* account out of the JSONB distribution.
Now that journal items carry a real ``operating_unit_id`` column, add it as a
first-class dimension: it groups and filters like any other field, costs nothing
to read, and — unlike a subquery — can be scoped by a record rule.

The base definition is not copied here. It is read back from Postgres after
``super().init()`` and wrapped, so this stays correct when the base report
changes.
"""

from odoo import fields, models


class CustomReportJournalItemAnalysis(models.Model):
    _inherit = "custom.report.journal.item.analysis"

    operating_unit_id = fields.Many2one(
        "operating.unit", string="Operating Unit", readonly=True, index=True
    )

    def init(self):
        super().init()
        cr = self.env.cr
        cr.execute("SELECT pg_get_viewdef(%s::regclass, true)", (self._table,))
        row = cr.fetchone()
        if not row:
            return
        base_definition = row[0].rstrip().rstrip(";")
        cr.execute("DROP VIEW IF EXISTS %s CASCADE" % self._table)
        cr.execute(
            """
            CREATE VIEW {table} AS
            SELECT base.*, aml.operating_unit_id AS operating_unit_id
              FROM ({base}) base
              LEFT JOIN account_move_line aml ON aml.id = base.id
            """.format(table=self._table, base=base_definition)
        )
