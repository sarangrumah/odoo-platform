# -*- coding: utf-8 -*-
"""stock.quant hook — flag rule re-evaluation on inventory mutation.

We intentionally do NOT run the engine inline (it would block writes and may
fan out across many locations). Instead the write() override marks the
relevant rule(s) "dirty" by stamping ``last_run_at`` so the cron picks them
up next tick.
"""

from __future__ import annotations

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def write(self, vals):
        res = super().write(vals)
        if "quantity" in vals:
            # Stamp low-water mark rules so the cron knows to re-evaluate.
            try:
                Rule = self.env["custom.to.rule"]
                rules = Rule.sudo().search([
                    ("active", "=", True),
                    ("trigger", "=", "low_water_mark"),
                ])
                if rules:
                    rules.write({"last_run_at": fields.Datetime.now()})
            except Exception as exc:  # pragma: no cover - never break write
                _logger.debug("TO low-water stamp skipped: %s", exc)
        return res
