# -*- coding: utf-8 -*-
"""Capability catalog — one entry per scanned ``custom_*`` module.

Auto-populated by ``_scan_all_modules()`` (called from a button, the monthly
cron, and the post-install hook). Each entry stores enough structured metadata
about a module for the AI analyzer to reason about whether a BRD requirement
can be fulfilled by it.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import get_modules, get_module_path

_logger = logging.getLogger(__name__)


CATEGORY_BY_PATH_SEGMENT = {
    "core": "core",
    "compliance": "compliance",
    "ee_gap": "ee_gap",
    "operations": "operations",
    "verticals": "vertical",
}


# Map keywords found in the manifest summary/description/category to capability tag codes.
_KEYWORD_TAG_MAP: dict[str, list[str]] = {
    "rental": ["rental"],
    "lease": ["rental"],
    "withholding": ["withholding"],
    "pph": ["withholding", "indonesian-tax"],
    "ppn": ["indonesian-tax"],
    "coretax": ["indonesian-tax", "coretax"],
    "pajakku": ["indonesian-tax", "coretax"],
    "consolidation": ["consolidation", "accounting"],
    "intercompany": ["intercompany", "accounting"],
    "approval": ["approval-workflow"],
    "barcode": ["barcode-scan"],
    "wms": ["wms"],
    "hht": ["hht"],
    "audit": ["audit-trail"],
    "pdp": ["pdp", "audit-trail"],
    "ppob": ["ppob"],
    "ai": ["ai"],
    "anomaly": ["ai", "anomaly-detection"],
    "rfid": ["barcode-scan", "rfid"],
    "manufacturing": ["manufacturing"],
    "mrp": ["manufacturing"],
    "plm": ["manufacturing", "plm"],
    "payroll": ["payroll", "indonesian-payroll"],
    "bpjs": ["indonesian-payroll", "indonesian-tax"],
    "attendance": ["attendance"],
    "fleet": ["fleet"],
    "voip": ["voip"],
    "whatsapp": ["whatsapp"],
    "ecommerce": ["ecommerce"],
    "subscription": ["subscription"],
    "marketing": ["marketing"],
    "crm": ["crm"],
    "helpdesk": ["helpdesk"],
    "knowledge": ["knowledge"],
    "field service": ["field-service"],
    "iot": ["iot"],
    "quality": ["quality"],
    "tenant": ["multi-tenant"],
    "multi-tenant": ["multi-tenant"],
}


class CustomModuleCapabilityEntry(models.Model):
    _name = "custom.module.capability.entry"
    _description = "Module Capability Catalog Entry"
    _order = "category, module_name"
    _rec_name = "module_name"

    module_name = fields.Char(required=True, index=True)
    module_path = fields.Char()
    category = fields.Selection(
        [
            ("core", "Core"),
            ("compliance", "Compliance"),
            ("ee_gap", "EE-Gap"),
            ("operations", "Operations"),
            ("vertical", "Vertical"),
        ],
        index=True,
    )
    summary = fields.Text()
    capability_tag_ids = fields.Many2many(
        "custom.module.capability.tag",
        "custom_module_capability_entry_tag_rel",
        "entry_id",
        "tag_id",
        string="Capability Tags",
    )
    depends = fields.Json(default=list)
    models_own = fields.Json(default=list)
    models_inherit = fields.Json(default=list)
    routes = fields.Json(default=list)
    maturity = fields.Selection(
        [
            ("scaffold", "Scaffold"),
            ("partial", "Partial"),
            ("production", "Production"),
        ],
        default="partial",
        index=True,
    )
    version = fields.Char()
    last_scanned = fields.Datetime()
    notes = fields.Text()

    _sql_constraints = [
        ("module_name_uniq", "unique(module_name)", "Capability entry module_name must be unique."),
    ]

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    @api.model
    def action_rescan(self):
        count = self._scan_all_modules()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Capability Catalog"),
                "message": _("Scanned %s modules.") % count,
                "sticky": False,
                "type": "success",
            },
        }

    @api.model
    def _scan_all_modules(self) -> int:
        """Walk every available addon, harvest hub modules whose name starts
        with ``custom_``, and upsert a catalog entry per module.

        Returns number of entries written.
        """
        Tag = self.env["custom.module.capability.tag"]
        # Make sure we know the full tag vocabulary up-front to avoid N queries.
        tag_cache: dict[str, int] = {
            t.technical_code: t.id for t in Tag.sudo().search([])
        }

        written = 0
        for mod_name in get_modules():
            if not mod_name.startswith("custom_"):
                continue
            try:
                payload = self._scrape_module(mod_name)
            except Exception as exc:  # pragma: no cover - resilient scan
                _logger.warning("BRD scan: skipping %s: %s", mod_name, exc)
                continue
            if not payload:
                continue
            tag_ids = self._resolve_tag_ids(payload, tag_cache, Tag)
            vals = dict(payload, capability_tag_ids=[(6, 0, tag_ids)], last_scanned=fields.Datetime.now())
            existing = self.sudo().search([("module_name", "=", mod_name)], limit=1)
            if existing:
                existing.write(vals)
            else:
                self.sudo().create(vals)
            written += 1
        return written

    @api.model
    def _scrape_module(self, mod_name: str) -> dict | None:
        path = get_module_path(mod_name)
        if not path:
            return None
        manifest_data = self._read_manifest(path)
        if manifest_data is None:
            return None
        category = self._infer_category(path)
        models_own, models_inherit = self._scrape_models(path)
        routes = self._scrape_routes(path)
        summary = manifest_data.get("summary") or manifest_data.get("description") or ""
        return {
            "module_name": mod_name,
            "module_path": path,
            "category": category,
            "summary": (summary or "").strip()[:4000],
            "depends": manifest_data.get("depends") or [],
            "models_own": models_own,
            "models_inherit": models_inherit,
            "routes": routes,
            "version": manifest_data.get("version"),
            "maturity": self._infer_maturity(models_own, routes),
        }

    @staticmethod
    def _read_manifest(path: str) -> dict | None:
        manifest_file = os.path.join(path, "__manifest__.py")
        if not os.path.isfile(manifest_file):
            return None
        try:
            with open(manifest_file, "r", encoding="utf-8") as fh:
                raw = fh.read()
            return ast.literal_eval(raw)
        except Exception as exc:
            _logger.debug("BRD scan: bad manifest in %s: %s", path, exc)
            return None

    @staticmethod
    def _infer_category(path: str) -> str:
        parts = Path(path).parts
        for seg in parts:
            if seg in CATEGORY_BY_PATH_SEGMENT:
                return CATEGORY_BY_PATH_SEGMENT[seg]
        return "operations"

    @staticmethod
    def _scrape_models(path: str) -> tuple[list[str], list[str]]:
        models_dir = os.path.join(path, "models")
        own: set[str] = set()
        inh: set[str] = set()
        if not os.path.isdir(models_dir):
            return [], []
        # Patterns over raw source so we never need to import the module.
        re_name = re.compile(r"^\s*_name\s*=\s*['\"]([\w.]+)['\"]", re.MULTILINE)
        re_inherit_single = re.compile(r"^\s*_inherit\s*=\s*['\"]([\w.]+)['\"]", re.MULTILINE)
        re_inherit_list = re.compile(r"^\s*_inherit\s*=\s*\[([^\]]+)\]", re.MULTILINE)
        for root, _dirs, files in os.walk(models_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(root, fn), "r", encoding="utf-8") as fh:
                        src = fh.read()
                except OSError:
                    continue
                own.update(re_name.findall(src))
                inh.update(re_inherit_single.findall(src))
                for chunk in re_inherit_list.findall(src):
                    inh.update(re.findall(r"['\"]([\w.]+)['\"]", chunk))
        return sorted(own), sorted(inh)

    @staticmethod
    def _scrape_routes(path: str) -> list[str]:
        ctrl_dir = os.path.join(path, "controllers")
        routes: set[str] = set()
        if not os.path.isdir(ctrl_dir):
            return []
        re_route = re.compile(r"@(?:http\.)?route\(\s*['\"]([^'\"]+)['\"]")
        re_route_list = re.compile(r"@(?:http\.)?route\(\s*\[([^\]]+)\]")
        for root, _dirs, files in os.walk(ctrl_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(root, fn), "r", encoding="utf-8") as fh:
                        src = fh.read()
                except OSError:
                    continue
                routes.update(re_route.findall(src))
                for chunk in re_route_list.findall(src):
                    routes.update(re.findall(r"['\"]([^'\"]+)['\"]", chunk))
        return sorted(routes)

    @staticmethod
    def _infer_maturity(models_own: list[str], routes: list[str]) -> str:
        score = len(models_own) + len(routes) // 2
        if score >= 8:
            return "production"
        if score >= 2:
            return "partial"
        return "scaffold"

    def _resolve_tag_ids(self, payload: dict, tag_cache: dict, Tag) -> list[int]:
        haystack = " ".join(
            [
                (payload.get("summary") or "").lower(),
                payload.get("module_name", "").lower(),
            ]
        )
        found_codes: set[str] = set()
        for keyword, codes in _KEYWORD_TAG_MAP.items():
            if keyword in haystack:
                found_codes.update(codes)
        result: list[int] = []
        for code in found_codes:
            tag_id = tag_cache.get(code)
            if tag_id is None:
                new = Tag.sudo().create({"name": code.replace("-", " ").title(), "technical_code": code})
                tag_cache[code] = new.id
                tag_id = new.id
            result.append(tag_id)
        return result

    # ------------------------------------------------------------------
    # Cron entry-point
    # ------------------------------------------------------------------

    @api.model
    def _cron_rescan_catalog(self):
        try:
            count = self._scan_all_modules()
            _logger.info("custom_brd_analyzer: monthly catalog rescan wrote %s entries", count)
        except Exception as exc:  # pragma: no cover
            _logger.exception("custom_brd_analyzer: catalog rescan failed: %s", exc)

    # ------------------------------------------------------------------
    # Catalog snapshot for AI prompt
    # ------------------------------------------------------------------

    @api.model
    def _build_prompt_catalog(self, maturities: tuple[str, ...] = ("partial", "production")) -> list[dict]:
        """Compact dict-list for embedding in the LLM prompt.

        Only includes modules with maturity in ``maturities`` (default: skip
        scaffolds — they cannot fulfil requirements yet).
        """
        entries = self.sudo().search([("maturity", "in", list(maturities))])
        out: list[dict] = []
        for e in entries:
            out.append(
                {
                    "module": e.module_name,
                    "category": e.category,
                    "summary": (e.summary or "")[:600],
                    "tags": e.capability_tag_ids.mapped("technical_code"),
                    "models": (e.models_own or [])[:30],
                    "depends": (e.depends or [])[:30],
                    "maturity": e.maturity,
                }
            )
        return out
