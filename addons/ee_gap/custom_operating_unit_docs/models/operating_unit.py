# -*- coding: utf-8 -*-
"""Links from an Operating Unit to the stock/accounting records it owns.

These live here rather than in ``custom_operating_unit`` so the base module
stays installable on a tenant that has neither ``stock`` nor ``account``.
"""

from odoo import api, fields, models, tools


class OperatingUnit(models.Model):
    _inherit = "operating.unit"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        ondelete="restrict",
        index=True,
        help="The warehouse that represents this unit. Documents are matched to "
        "the unit through it — never rename or re-code the warehouse to fit.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        ondelete="restrict",
        help="Sales / miscellaneous journal dedicated to this unit, if any.",
    )
    purchase_journal_id = fields.Many2one(
        "account.journal",
        string="Purchase Journal",
        domain="[('type', '=', 'purchase')]",
        ondelete="restrict",
    )

    _warehouse_uniq = models.Constraint(
        "UNIQUE (warehouse_id)", "That warehouse already belongs to another Operating Unit."
    )

    @api.model
    @tools.ormcache()
    def _warehouse_index(self):
        """``{warehouse_id: operating_unit_id}`` — one query, cached.

        The document computes run over whole journals and pickings; resolving
        the unit per record would be a query per row.
        """
        rows = (
            self.with_context(active_test=False).sudo().search_read([("warehouse_id", "!=", False)], ["warehouse_id"])
        )
        return {row["warehouse_id"][0]: row["id"] for row in rows}

    @api.model
    @tools.ormcache()
    def _journal_index(self):
        """``{journal_id: operating_unit_id}`` for both journal links."""
        index = {}
        rows = (
            self.with_context(active_test=False)
            .sudo()
            .search_read(
                ["|", ("journal_id", "!=", False), ("purchase_journal_id", "!=", False)],
                ["journal_id", "purchase_journal_id"],
            )
        )
        for row in rows:
            for key in ("journal_id", "purchase_journal_id"):
                if row[key]:
                    index[row[key][0]] = row["id"]
        return index

    def write(self, vals):
        res = super().write(vals)
        if {"warehouse_id", "journal_id", "purchase_journal_id"} & set(vals):
            self.env.registry.clear_cache()
        return res
