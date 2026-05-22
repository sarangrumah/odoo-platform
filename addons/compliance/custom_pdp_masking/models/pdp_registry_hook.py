# -*- coding: utf-8 -*-
"""Global ORM hook: every ``read()`` consults the PDP Field Registry.

We patch ``models.BaseModel.read`` indirectly by extending ``base`` so the
hook applies to *all* models without needing each one to inherit
``pdp.masked.mixin``. The cost is a registry lookup per read; the
registry helper memoises results in ``env.context``.

Audit events for mask applications are written via
:class:`pdp.audited.mixin`-style direct SQL into ``pdp.audit_log``
(category = ``pii_mask``).
"""

from __future__ import annotations

import json
import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class BaseMaskingHook(models.AbstractModel):
    _inherit = "base"

    def read(self, fields=None, load="_classic_read"):
        rows = super().read(fields=fields, load=load)
        try:
            Reg = self.env["custom.pdp.field.registry"].sudo()
            rules = Reg._registry_for(self._name)
        except Exception:
            return rows
        if not rules:
            return rows
        # Filter rules to those whose field is in the row + user lacks bypass.
        applicable = []
        for r in rules:
            if Reg._user_bypasses(r["groups"]):
                continue
            applicable.append(r)
        if not applicable:
            return rows
        # Apply masking and audit-log once per (model, field) batch.
        masked_field_summary = {}
        for row in rows:
            for r in applicable:
                fname = r["field"]
                if fname in row and row[fname] not in (None, False, ""):
                    row[fname] = Reg._apply(row[fname], r["pattern"])
                    masked_field_summary[fname] = masked_field_summary.get(fname, 0) + 1
        if masked_field_summary:
            _log_mask_event(self, masked_field_summary)
        return rows


def _log_mask_event(records, summary: dict):
    """Append a ``pii_mask`` audit row. Best-effort, never raises."""
    try:
        user = records.env.user
        ip = None
        ua = None
        try:
            if request:
                ip = request.httprequest.environ.get("REMOTE_ADDR")
                ua = request.httprequest.environ.get("HTTP_USER_AGENT")
        except Exception:
            pass
        records.env.cr.execute(
            """
            INSERT INTO pdp.audit_log (
                actor_user_id, actor_login, tenant_db,
                model_name, res_id, action,
                field_changes, classification,
                ip_address, user_agent
            ) VALUES (%s, %s, %s, %s, NULL, %s, %s::jsonb, %s, %s::inet, %s)
            """,
            (
                user.id,
                user.login,
                records.env.cr.dbname,
                records._name,
                "pii_mask",
                json.dumps(summary),
                "pii",
                ip,
                ua,
            ),
        )
    except Exception as e:  # pragma: no cover
        _logger.debug("pii_mask audit insert skipped: %s", e)
