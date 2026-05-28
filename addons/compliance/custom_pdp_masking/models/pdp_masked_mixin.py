# -*- coding: utf-8 -*-
"""Mixin that hooks `read` to apply masking on PDP-classified fields.

Odoo 19's preferred extension point for masking is the public `read()` (and
`search_read`, which routes through `read()`). We override `read()` here and
post-process the result.
"""

from __future__ import annotations

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class PdpMaskedMixin(models.AbstractModel):
    _name = "pdp.masked.mixin"
    _description = "PDP Masked Mixin"

    @api.model
    def _pdp_classified_field_map(self) -> dict[str, str]:
        """Return {field_name: classification_code} for this model."""
        cache = self.env.context.get("__pdp_class_cache")
        if cache is None:
            cache = {}
        key = self._name
        if key in cache:
            return cache[key]
        fields = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("x_pdp_classification_id", "!=", False),
                ]
            )
        )
        out = {f.name: f.x_pdp_classification_id.code for f in fields}
        cache[key] = out
        return out

    def read(self, fields=None, load="_classic_read"):
        rows = super().read(fields=fields, load=load)
        try:
            classmap = self._pdp_classified_field_map()
        except Exception:
            return rows
        if not classmap:
            return rows
        Masking = self.env["pdp.masking"]
        policy = Masking._policy()
        can_view = Masking._user_can_view_pii(self.env.user)
        unmasked_ids = set(self.env.context.get("pdp_unmasked_ids") or [])
        if policy == "always_mask":
            allow_clear = False
        elif policy == "mask_in_export_only":
            allow_clear = True
        else:  # unmask_with_reason
            allow_clear = can_view
        if allow_clear and not unmasked_ids:
            return rows
        # Only mask text-like fields. Mangling an integer m2o id into a
        # string breaks Odoo's web_read m2o batch lookup (KeyError on the
        # masked value).
        _MASKABLE_TYPES = {"char", "text", "html"}
        for row in rows:
            if row.get("id") in unmasked_ids:
                continue
            for fname, code in classmap.items():
                if fname not in row:
                    continue
                f = self._fields.get(fname)
                if f is None or f.type not in _MASKABLE_TYPES:
                    continue
                row[fname] = Masking._mask(row[fname], code, self.env.user, field_name=fname)
        return rows
