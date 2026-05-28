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
        if self.env.context.get("__pdp_skip_masking"):
            return rows
        try:
            Reg = self.env["custom.pdp.field.registry"].sudo()
            rules = Reg._registry_for(self._name)
        except Exception:
            return rows
        if not rules:
            return rows
        unmasked_ids = set(self.env.context.get("pdp_unmasked_ids") or [])
        # Filter rules to those whose field is in the row, the user lacks
        # bypass, and the field is text-like (masking integer IDs of m2o /
        # boolean / date fields corrupts downstream web_read batching).
        _MASKABLE_TYPES = {"char", "text", "html"}
        applicable = []
        for r in rules:
            if Reg._user_bypasses(r["groups"]):
                continue
            f = self._fields.get(r["field"])
            if f is None or f.type not in _MASKABLE_TYPES:
                continue
            applicable.append(r)
        if not applicable:
            return rows
        # Apply masking and audit-log once per (model, field) batch.
        masked_field_summary = {}
        for row in rows:
            if row.get("id") in unmasked_ids:
                continue
            for r in applicable:
                fname = r["field"]
                if fname in row and row[fname] not in (None, False, ""):
                    row[fname] = Reg._apply(row[fname], r["pattern"])
                    masked_field_summary[fname] = masked_field_summary.get(fname, 0) + 1
        if masked_field_summary:
            _log_mask_event(self, masked_field_summary)
        return rows

    def get_view(self, view_id=None, view_type="form", **options):
        """Post-process the final arch so PII fields get the eye-toggle
        widget regardless of what other modules' ``_get_view`` overrides
        set. Runs after ``_get_view`` + access-rights post-processing, so
        widgets set by autocomplete/email/phone modules are replaced.
        """
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        try:
            Reg = self.env["custom.pdp.field.registry"].sudo()
            rules = Reg._registry_for(self._name)
        except Exception:
            return result
        if not rules:
            return result
        masked_names = {
            r["field"]
            for r in rules
            if not Reg._user_bypasses(r["groups"])
            and self._fields.get(r["field"]) is not None
            and self._fields[r["field"]].type in {"char", "text", "html"}
        }
        if not masked_names:
            return result
        arch = result.get("arch")
        if not arch:
            return result
        try:
            from lxml import etree
            tree = etree.fromstring(arch)
        except Exception:
            return result
        # Skip <field> nodes living inside these containers — they are
        # view metadata / search controls, not render targets, and forcing
        # a widget on them confuses the web client.
        _SKIP_ANCESTOR_TAGS = {"header", "searchpanel", "search", "groupby", "filter"}

        def _in_skip_context(node) -> bool:
            p = node.getparent()
            while p is not None:
                if p.tag in _SKIP_ANCESTOR_TAGS:
                    return True
                p = p.getparent()
            return False

        changed = False
        if view_type == "form":
            for node in tree.iter("field"):
                if node.get("name") in masked_names and not _in_skip_context(node):
                    # Force-overwrite: PII reveal must win over autocomplete.
                    node.set("widget", "pdp_masked_field")
                    changed = True
        elif view_type in ("list", "tree"):
            for node in tree.iter("field"):
                if node.get("name") in masked_names and not _in_skip_context(node):
                    node.set("column_invisible", "1")
                    changed = True
        elif view_type == "kanban":
            for node in tree.iter("field"):
                if node.get("name") in masked_names and not _in_skip_context(node):
                    node.set("invisible", "1")
                    changed = True
        if changed:
            result["arch"] = etree.tostring(tree, encoding="unicode")
        return result


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
