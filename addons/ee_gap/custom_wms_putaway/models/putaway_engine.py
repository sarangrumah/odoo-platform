# -*- coding: utf-8 -*-
"""Putaway engine — abstract scoring/proposal service.

This service produces candidate locations + confidence scores. It is invoked
either by the per-strategy ``_suggest_putaway`` flow or directly through
``propose(move_line)`` to return a ranked list.
"""

from __future__ import annotations

import logging

from odoo import _, api, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class PutawayEngine(models.AbstractModel):
    _name = "custom.putaway.engine"
    _description = "WMS Putaway Engine"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def propose(self, move_line):
        """Return a ranked list of dicts:
        [{'location_id': int, 'score': int, 'rule_id': int|False, 'reason': str}, ...]
        """
        if not move_line or not move_line.product_id:
            return []
        warehouse = move_line.picking_id.picking_type_id.warehouse_id
        Strategy = self.env["custom.wms.putaway.strategy"]
        strategies = Strategy.search([("active", "=", True), ("warehouse_id", "=", warehouse.id)])
        proposals: list[dict] = []
        for strategy in strategies:
            for rule in strategy.rule_ids.filtered(lambda r: r.active).sorted(key=lambda r: (r.tier, r.sequence)):
                score, reason = self._score_rule(rule, move_line)
                if score <= 0:
                    continue
                loc = rule.target_location_id
                if not loc:
                    cands = rule._candidate_locations()
                    loc = cands[:1]
                proposals.append(
                    {
                        "location_id": loc.id if loc else False,
                        "score": score,
                        "rule_id": rule.id,
                        "reason": reason,
                        "tier": rule.tier,
                    }
                )
        proposals.sort(key=lambda d: (d.get("tier") or 9999, -d["score"]))
        return proposals

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @api.model
    def _score_rule(self, rule, move_line):
        """Return (score:int 0..100, reason:str)."""
        kind = rule.kind
        handler = getattr(self, f"_score_{kind}", None)
        if not handler:
            return 0, ""
        try:
            return handler(rule, move_line)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("Putaway scoring failed for rule=%s kind=%s: %s", rule.id, kind, exc)
            return 0, _("error: %s") % exc

    def _score_fixed_location(self, rule, move_line):
        if not rule.target_location_id:
            return 0, ""
        return 100, _("Fixed location")

    def _score_nearest_empty(self, rule, move_line):
        cands = rule._candidate_locations()
        # Empty = no quants
        Quant = self.env["stock.quant"]
        for loc in cands:
            qty = sum(Quant.search([("location_id", "=", loc.id)]).mapped("quantity"))
            if qty <= 0:
                # Score by lexical proximity to dock (lower id ~ closer is a stub)
                return 85, _("Nearest empty: %s") % loc.display_name
        return 0, ""

    def _score_zone_round_robin(self, rule, move_line):
        cands = rule._candidate_locations()
        if not cands:
            return 0, ""
        # Round-robin via modulo on move_line id
        idx = (move_line.id or 0) % len(cands)
        # We can't pick a different target without per-record state; bias score.
        return 70, _("Zone RR pick #%s") % idx

    def _score_by_volume(self, rule, move_line):
        loc = rule.target_location_id
        if not loc:
            cands = rule._candidate_locations()
            if not cands:
                return 0, ""
            loc = cands[:1]
        capacity = getattr(loc, "volume_capacity_m3", 0.0) or 0.0
        used = getattr(loc, "volume_used_m3", 0.0) or 0.0
        product = move_line.product_id
        product_vol = (product.volume or 0.0) * (move_line.quantity or move_line.reserved_uom_qty or 0.0)
        if capacity <= 0:
            return 0, _("Location has no volume capacity")
        if used + product_vol > capacity:
            return 0, _("Oversized: needs %.3fm3, free %.3fm3") % (product_vol, max(0.0, capacity - used))
        free_ratio = (capacity - used - product_vol) / capacity
        # Higher = better fit (less wasted space relative to product)
        score = int(60 + 40 * (1.0 - max(0.0, min(1.0, free_ratio))))
        return score, _("Volume fit: %.2f m3 free") % max(0.0, capacity - used)

    def _score_by_temperature(self, rule, move_line):
        if not rule.temperature_zone:
            return 0, ""
        # No standard field; treat as match if rule's zone is set and target exists
        if not rule.target_location_id:
            return 0, ""
        return 75, _("Temperature zone: %s") % rule.temperature_zone

    def _score_by_abc_velocity(self, rule, move_line):
        product = move_line.product_id
        abc = getattr(product, "abc_class", "B") or "B"
        # A items near dock — proxy: any rule with abc_class='A' scores higher
        weight = {"A": 95, "B": 75, "C": 55}.get(abc, 50)
        if rule.abc_class and rule.abc_class != abc:
            return 0, ""
        return weight, _("ABC velocity (%s)") % abc

    def _score_custom_python(self, rule, move_line):
        expr = (rule.custom_python or "").strip()
        if not expr:
            return 0, ""
        product = move_line.product_id
        candidate_locations = rule._candidate_locations()
        eval_ctx = {
            "move_line": move_line,
            "product": product,
            "candidate_locations": candidate_locations,
            "env": self.env,
        }
        # safe_eval blocks attribute access to dangerous builtins by default.
        try:
            result = safe_eval(expr, eval_ctx, {}, mode="eval", nocopy=True)
        except Exception as exc:
            _logger.warning("custom_python rejected: %s", exc)
            return 0, _("custom_python rejected (unsafe): %s") % exc
        if not isinstance(result, tuple) or len(result) != 2:
            return 0, _("custom_python must return (location_id, score) tuple")
        _loc_id, score = result
        try:
            score = int(score)
        except Exception:
            return 0, _("custom_python score must be int")
        return max(0, min(100, score)), _("custom_python")

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    @api.model
    def apply_top_proposal(self, move_line):
        """If top proposal confidence > 90, auto-apply by rewriting destination."""
        proposals = self.propose(move_line)
        if not proposals:
            return False
        top = proposals[0]
        Suggestion = self.env["custom.wms.putaway.suggestion"]
        sugg = Suggestion.create(
            {
                "picking_id": move_line.picking_id.id,
                "move_line_id": move_line.id,
                "original_dest_location_id": move_line.location_dest_id.id,
                "suggested_location_id": top["location_id"],
                "rule_id": top["rule_id"],
                "score": top["score"],
                "reason": top["reason"],
            }
        )
        if top["score"] > 90 and top["location_id"]:
            sugg.action_apply()
        return sugg
