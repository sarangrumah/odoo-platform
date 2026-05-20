# -*- coding: utf-8 -*-
"""Tighten the ``journey_id`` field on ``brd.document``.

Track B already declared the forward-reference field. Now that the comodel
exists we don't need to touch the field at all — the O2M ``brd_document_ids``
on the journey side uses ``journey_id`` as its inverse name, which works as-is.

This stub exists so that any future extension (e.g. propagating
``journey_id`` on copy, or adding domain restrictions) has a natural home
without editing the brd_analyzer module.
"""

from odoo import models


class BrdDocumentJourneyLink(models.Model):
    _inherit = "brd.document"

    # No field redeclaration needed; inverse from onboarding.journey.brd_document_ids
    # already binds correctly because the M2O exists with the proper comodel.

    def write(self, vals):
        # If a BRD is bound to a journey, transition the journey when the BRD
        # reaches ``analyzed`` (best-effort; silent failure if context blocks).
        result = super().write(vals)
        if vals.get("state") == "analyzed":
            for rec in self:
                if rec.journey_id and rec.journey_id.stage == "brd_uploaded":
                    try:
                        rec.journey_id.with_context(_transition_notes="Auto from BRD analysis").write(
                            {"stage": "brd_analyzed"}
                        )
                    except Exception:
                        # Don't block BRD workflow on journey-state issues.
                        pass
        return result
