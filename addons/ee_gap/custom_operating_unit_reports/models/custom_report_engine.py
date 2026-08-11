# -*- coding: utf-8 -*-
"""Make the raw-SQL reports obey the reader's Operating Units.

``ir.rule`` protects ORM reads. Every report in ``custom_accounting_reports``
builds its own SQL for speed, so the rules never see those queries — hence the
``_ou_sql_filter`` hook, implemented here and spliced into each report's WHERE
clause by the engine.
"""

from odoo import models


class CustomReportEngine(models.AbstractModel):
    _inherit = "custom.report.engine"

    def _ou_sql_filter(self, alias="aml"):
        user = self.env.user
        requested = self.env.context.get("report_operating_unit_ids")

        if requested:
            unit_ids = list(requested)
            if user.ou_is_scoped:
                # An explicit filter may narrow the reader's own units, never
                # widen them — otherwise the wizard becomes the way around the
                # isolation.
                allowed = set(user.ou_allowed_ids.ids)
                unit_ids = [uid for uid in unit_ids if uid in allowed]
            if not unit_ids:
                return " AND FALSE", []
            return " AND %s.operating_unit_id IN %%s" % alias, [tuple(unit_ids)]

        if not user.ou_is_scoped:
            return "", []

        unit_ids = user.ou_allowed_ids.ids
        if not unit_ids:
            return " AND FALSE", []
        if user.ou_include_untagged:
            # Same posture as the record rules: documents that carry no unit
            # yet (everything, before the backfill) stay visible.
            return (
                " AND (%s.operating_unit_id IS NULL OR %s.operating_unit_id IN %%s)"
                % (alias, alias),
                [tuple(unit_ids)],
            )
        return " AND %s.operating_unit_id IN %%s" % alias, [tuple(unit_ids)]


class CustomReportProfitLossBranch(models.AbstractModel):
    _inherit = "custom.report.profit.loss.branch"

    def _branch_columns(self):
        """The branch columns, restricted to the units the reader may see.

        The head-office column is a residual (it absorbs every untagged line),
        so a scoped reader must not get it — it would show them the whole
        company's remainder. Unscoped readers keep the report unchanged, and so
        does a tenant with no Operating Units at all.
        """
        columns = super()._branch_columns()
        user = self.env.user
        if not user.ou_is_scoped:
            return columns
        visible_analytic_ids = set(user.ou_allowed_ids.analytic_account_id.ids)
        return [
            column
            for column in columns
            if column[2] is not None and column[2] in visible_analytic_ids
        ]
