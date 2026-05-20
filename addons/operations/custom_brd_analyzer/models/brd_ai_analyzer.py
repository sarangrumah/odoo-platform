# -*- coding: utf-8 -*-
"""AI analysis driver — orchestrates the call to ``custom_ai_bridge``.

Design notes
============

* The capability catalog is the single largest, rarely changing block in the
  prompt. We embed it as ``cache_control: ephemeral`` so that within a 5-minute
  window every BRD that hits the same Odoo node benefits from a near-instant
  cache hit. ``custom_ai_bridge`` already sets ``cache_system=True`` for the
  system prompt; we additionally inject the catalog into the system prompt so
  it inherits the same caching behaviour.
* The user message is per-BRD and per-section, so it intentionally varies.
* Strict JSON via explicit schema + a low temperature.
* Chunking: if the BRD has too many sections, we split into batches and
  merge results.
* Retry: one retry on malformed JSON with a stricter "JSON ONLY, no prose"
  instruction prefix.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from odoo import fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """You are a senior Odoo solution architect analysing whether a customer's
Business Requirements Document (BRD) can be fulfilled by an existing custom
Odoo platform.

You receive:
  (a) The BRD as a list of structured sections (id, title, content).
  (b) A JSON catalog of available hub modules with their capabilities,
      models, dependencies and maturity.

Your job, for every BRD section, is to:
  1. Distil the underlying business capability the section is asking for.
  2. List capability tags (use the controlled vocabulary that appears as
     ``tags`` across the catalog; you may also propose new tags but prefer
     existing ones).
  3. Map to one or more hub modules from the catalog that already cover the
     capability (use the exact ``module`` name).
  4. Score fit 0-100 (0 = nothing covers it, 100 = fully covered today).
  5. Classify gap_status as one of: covered / partial / missing / unclear.
  6. Classify gap_severity as one of: must_have / should_have / nice_to_have.
  7. Write a short note explaining the reasoning.

After processing every section you must also propose a *minimal* set of new
``custom_<x>`` modules to fill the missing/partial parts, each with:
  - a snake_case name starting with ``custom_``,
  - a concise scope,
  - a tag list,
  - dependencies (existing modules from the catalog *and* other proposed
    siblings in this very response),
  - the existing modules they will *impact* (extend / patch),
  - an estimated_md (man-days, integer 1..120),
  - the severity it inherits from the worst section it addresses,
  - a justification paragraph,
  - **cross-vertical impact analysis** (REQUIRED): for every recommendation
    you MUST include
      * ``affects_existing_modules``: list of hub catalog module_name strings
        the proposal would extend or patch (subset of catalog),
      * ``cross_vertical_impact``: object keyed by module_name; each value is
        the list of verticals that already consume that module (use the
        ``deployed_in_verticals`` field of the catalog entry),
      * ``breaking_change``: boolean — true if the change would break the
        public API/schema for *any* of those verticals,
      * ``compat_strategy``: one of ``extend`` / ``abstract_base`` /
        ``feature_flag`` / ``fork_warning``.

OUTPUT MUST BE STRICT JSON matching the schema injected below. Do NOT wrap
the JSON in markdown code fences. Do NOT add commentary. If you are unsure
about a field, set gap_status = "unclear" and explain in notes.
"""


DEFAULT_USER_PROMPT_TEMPLATE = """BRD: {brd_name}
Business domain: {business_domain}
Language: {language}

=== BRD SECTIONS (JSON) ===
{sections_json}

=== AVAILABLE HUB MODULE CATALOG (JSON) ===
{catalog_json}

=== HUB MODULE CROSS-VERTICAL DEPLOYMENT (JSON) ===
{cross_vertical_json}

=== EXPECTED RESPONSE SCHEMA ===
{schema_json}

Return strict JSON now.
"""


DEFAULT_JSON_SCHEMA = {
    "type": "object",
    "required": ["overall_fit_pct", "sections", "recommendations"],
    "properties": {
        "overall_fit_pct": {"type": "integer", "minimum": 0, "maximum": 100},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "section_id",
                    "capability_required",
                    "capabilities_mentioned",
                    "mapped_module_names",
                    "fit_score",
                    "gap_status",
                    "gap_severity",
                    "notes",
                ],
                "properties": {
                    "section_id": {"type": "integer"},
                    "capability_required": {"type": "string"},
                    "capabilities_mentioned": {"type": "array", "items": {"type": "string"}},
                    "mapped_module_names": {"type": "array", "items": {"type": "string"}},
                    "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "gap_status": {"type": "string", "enum": ["covered", "partial", "missing", "unclear"]},
                    "gap_severity": {"type": "string", "enum": ["must_have", "should_have", "nice_to_have"]},
                    "notes": {"type": "string"},
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "scope", "capability_tags", "estimated_md", "depends", "impact_modules", "justification", "severity"],
                "properties": {
                    "name": {"type": "string"},
                    "scope": {"type": "string"},
                    "capability_tags": {"type": "array", "items": {"type": "string"}},
                    "estimated_md": {"type": "integer", "minimum": 1, "maximum": 240},
                    "depends": {"type": "array", "items": {"type": "string"}},
                    "depends_on_proposed": {"type": "array", "items": {"type": "string"}},
                    "impact_modules": {"type": "array", "items": {"type": "string"}},
                    "severity": {"type": "string", "enum": ["must_have", "should_have", "nice_to_have"]},
                    "justification": {"type": "string"},
                    "related_section_ids": {"type": "array", "items": {"type": "integer"}},
                    "affects_existing_modules": {"type": "array", "items": {"type": "string"}},
                    "cross_vertical_impact": {
                        "type": "object",
                        "additionalProperties": {"type": "array", "items": {"type": "string"}},
                    },
                    "breaking_change": {"type": "boolean"},
                    "compat_strategy": {
                        "type": "string",
                        "enum": ["extend", "abstract_base", "feature_flag", "fork_warning"],
                    },
                },
            },
        },
    },
}


# Section count above which we batch.
_SECTION_BATCH_SIZE = 25


class BrdAiAnalyzer:
    """Stateless analyzer; takes an env + a ``brd.document`` recordset of len 1."""

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    def analyze(self, brd_doc) -> dict[str, Any]:
        """Run the analysis and write Analyses + Recommendations.

        Returns the parsed AI response dict (useful for tests and debugging).
        """
        if not brd_doc:
            raise UserError("BRD record required.")
        sections = brd_doc.section_ids.sorted("sequence")
        if not sections:
            raise UserError("BRD has no extracted sections; run Extract first.")

        Param = self.env["ir.config_parameter"].sudo()
        system_prompt = Param.get_param("custom_brd_analyzer.system_prompt") or DEFAULT_SYSTEM_PROMPT
        user_template = Param.get_param("custom_brd_analyzer.user_prompt_template") or DEFAULT_USER_PROMPT_TEMPLATE
        schema = self._load_schema(Param)
        catalog = self.env["custom.module.capability.entry"].sudo()._build_prompt_catalog()
        catalog_json = json.dumps(catalog, ensure_ascii=False)
        cross_vertical = self._build_cross_vertical_context()
        cross_vertical_json = json.dumps(cross_vertical, ensure_ascii=False)

        merged: dict[str, Any] = {"sections": [], "recommendations": [], "overall_fit_pct": 0}
        scored = 0
        fit_total = 0
        raw_responses: list[str] = []  # for diagnostics
        for batch in self._chunk(sections, _SECTION_BATCH_SIZE):
            section_blob = [
                {"section_id": s.id, "title": s.title or "", "content": (s.content or "")[:3000]}
                for s in batch
            ]
            try:
                user_msg = user_template.format(
                    brd_name=brd_doc.name or "BRD",
                    business_domain=brd_doc.business_domain or "other",
                    language=brd_doc.language or "en",
                    sections_json=json.dumps(section_blob, ensure_ascii=False),
                    catalog_json=catalog_json,
                    cross_vertical_json=cross_vertical_json,
                    schema_json=json.dumps(schema),
                )
            except KeyError:
                # Backward-compat: a previously-overridden template in
                # ir.config_parameter may not know the new placeholder.
                user_msg = user_template.format(
                    brd_name=brd_doc.name or "BRD",
                    business_domain=brd_doc.business_domain or "other",
                    language=brd_doc.language or "en",
                    sections_json=json.dumps(section_blob, ensure_ascii=False),
                    catalog_json=catalog_json,
                    schema_json=json.dumps(schema),
                )
                user_msg += (
                    "\n\n=== HUB MODULE CROSS-VERTICAL DEPLOYMENT (JSON) ===\n"
                    + cross_vertical_json
                )
            response_text = self._call_ai(system_prompt=system_prompt, user_message=user_msg, catalog_json=catalog_json)
            raw_responses.append(response_text or "")
            _logger.info(
                "brd_ai_analyzer: batch response_text length=%d preview=%s",
                len(response_text or ""),
                (response_text or "")[:500].replace("\n", " "),
            )
            parsed = self._parse_json_strict(response_text, system_prompt=system_prompt, user_message=user_msg, catalog_json=catalog_json)
            batch_secs = parsed.get("sections") or []
            batch_recs = parsed.get("recommendations") or []
            _logger.info(
                "brd_ai_analyzer: parsed batch -> %d sections, %d recommendations",
                len(batch_secs), len(batch_recs),
            )
            merged["sections"].extend(batch_secs)
            merged["recommendations"].extend(batch_recs)
            if parsed.get("overall_fit_pct") is not None:
                fit_total += int(parsed["overall_fit_pct"])
                scored += 1

        if scored:
            merged["overall_fit_pct"] = int(fit_total / scored)

        # Stash diagnostics on the document so the UI can surface them even
        # when AI returns empty arrays.
        merged["_raw_responses"] = raw_responses

        self._persist(brd_doc, merged)
        return merged

    # ------------------------------------------------------------------
    # Cross-vertical context builder
    # ------------------------------------------------------------------

    def _build_cross_vertical_context(self) -> list[dict]:
        """Return a serializable view of the hub catalog with capability tags,
        maturity and per-module list of verticals it is deployed in.

        Format::

            [
                {"module_name": "custom_coretax",
                 "category": "compliance",
                 "maturity": "production",
                 "tags": ["tax", "indonesia"],
                 "deployed_in_verticals": ["retail", "fnb"]},
                ...
            ]

        Graceful degradation:
        * If ``custom.hub.module.catalog`` is not installed, returns ``[]``.
        * If ``custom.hub.module.deployment`` is missing, leaves the verticals
          list empty.
        """
        Catalog = self.env.get("custom.hub.module.catalog")
        if Catalog is None:
            return []
        Catalog = Catalog.sudo()
        Deployment = self.env.get("custom.hub.module.deployment")
        deployments_by_catalog: dict[int, list[str]] = {}
        if Deployment is not None:
            for dep in Deployment.sudo().search([]):
                cat = getattr(dep, "catalog_id", False)
                if not cat:
                    continue
                vertical = (
                    getattr(dep, "vertical_code", False)
                    or getattr(dep, "tenant_code", False)
                    or getattr(getattr(dep, "tenant_id", False), "code", False)
                    or getattr(getattr(dep, "vertical_id", False), "code", False)
                    or getattr(dep, "name", False)
                )
                if vertical:
                    deployments_by_catalog.setdefault(cat.id, []).append(str(vertical))

        rows: list[dict] = []
        for entry in Catalog.search([]):
            rows.append(
                {
                    "module_name": entry.module_name,
                    "category": entry.category or "",
                    "maturity": entry.maturity or "",
                    "tags": entry.capability_tag_ids.mapped("technical_code") or entry.capability_tag_ids.mapped("name"),
                    "deployed_in_verticals": sorted(set(deployments_by_catalog.get(entry.id, []))),
                }
            )
        return rows

    # ------------------------------------------------------------------
    # AI gateway call
    # ------------------------------------------------------------------

    def _call_ai(self, *, system_prompt: str, user_message: str, catalog_json: str) -> str:
        """Wraps ``custom.ai._chat``. The capability catalog is the cacheable
        block — we inject a cache-control sentinel by appending it to the
        system prompt (``custom_ai_bridge`` sets ``cache_system=True``)."""
        cached_system = (
            f"{system_prompt}\n\n"
            f"<!-- cache_control: ephemeral -->\n"
            f"=== CAPABILITY CATALOG (CACHED) ===\n{catalog_json}\n"
        )
        # ai-gateway accepts quality ∈ {"fast","high"}. BRD analysis benefits
        # from the quality model (claude-opus-4-7) — fewer JSON parse retries.
        result = self.env["custom.ai"].sudo()._chat(
            messages=[{"role": "user", "content": user_message}],
            system=cached_system,
            quality="high",
            max_tokens=4096,
            temperature=0.2,
        )
        # custom_ai_bridge gateway returns provider-shaped JSON; tolerate a few
        # common shapes.
        return self._unwrap_text(result)

    @staticmethod
    def _unwrap_text(result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            content = result.get("content")
            # 1) custom_ai_bridge gateway: ChatResponse.content is a pre-joined
            #    string of all text blocks. This is the common path for us.
            if isinstance(content, str):
                return content
            # 2) Raw Anthropic SDK response: content is list[{type,text}].
            if isinstance(content, list):
                parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                if parts:
                    return "".join(parts)
            # 3) OpenAI-shaped
            choices = result.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                if isinstance(msg, dict) and msg.get("content"):
                    return str(msg["content"])
            # 4) Other custom gateway shapes
            if "text" in result:
                return str(result["text"])
            if "output" in result:
                return str(result["output"])
        return json.dumps(result)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_json_strict(self, raw: str, *, system_prompt: str, user_message: str, catalog_json: str) -> dict:
        parsed = self._try_parse(raw)
        if parsed is not None:
            return parsed
        # Retry once with a stricter instruction prefix.
        _logger.warning("custom_brd_analyzer: first JSON parse failed; retrying with stricter prompt")
        retry_user = "STRICT JSON ONLY. NO PROSE. NO MARKDOWN FENCES. Output a single JSON object.\n\n" + user_message
        retry_text = self._call_ai(system_prompt=system_prompt, user_message=retry_user, catalog_json=catalog_json)
        parsed = self._try_parse(retry_text)
        if parsed is None:
            raise UserError("AI returned malformed JSON twice; check the logs for the raw response.")
        return parsed

    @staticmethod
    def _try_parse(raw: str) -> dict | None:
        if not raw:
            return None
        # Strip markdown code fences if present.
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        candidate = m.group(1) if m else raw
        # If still embedded, find the first '{' and last '}'.
        if not candidate.lstrip().startswith("{"):
            i = candidate.find("{")
            j = candidate.rfind("}")
            if i == -1 or j == -1 or j <= i:
                return None
            candidate = candidate[i : j + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _load_schema(Param) -> dict:
        raw = Param.get_param("custom_brd_analyzer.json_schema")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                _logger.warning("custom_brd_analyzer.json_schema is not valid JSON; falling back to default.")
        return DEFAULT_JSON_SCHEMA

    @staticmethod
    def _chunk(seq, size):
        seq = list(seq)
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, brd_doc, parsed: dict) -> None:
        Analysis = self.env["brd.analysis"].sudo()
        Recommendation = self.env["brd.recommendation"].sudo()
        Entry = self.env["custom.module.capability.entry"].sudo()
        Tag = self.env["custom.module.capability.tag"].sudo()
        Section = self.env["brd.document.section"].sudo()
        Catalog = self.env.get("custom.hub.module.catalog")
        if Catalog is not None:
            Catalog = Catalog.sudo()

        # Wipe previous run to keep idempotency.
        brd_doc.analysis_ids.unlink()
        brd_doc.recommendation_ids.unlink()

        # Sections
        for row in parsed.get("sections") or []:
            sec = Section.browse(int(row.get("section_id") or 0))
            if not sec.exists() or sec.document_id != brd_doc:
                # Be defensive: ignore section IDs the AI hallucinated.
                continue
            mapped = Entry.search([("module_name", "in", row.get("mapped_module_names") or [])])
            Analysis.create(
                {
                    "document_id": brd_doc.id,
                    "section_id": sec.id,
                    "capability_required": row.get("capability_required") or "",
                    "capabilities_mentioned": row.get("capabilities_mentioned") or [],
                    "mapped_module_ids": [(6, 0, mapped.ids)],
                    "fit_score": int(row.get("fit_score") or 0),
                    "gap_status": row.get("gap_status") or "unclear",
                    "gap_severity": row.get("gap_severity") or "should_have",
                    "notes": row.get("notes") or "",
                }
            )

        # Recommendations — two-pass so we can resolve sibling references.
        name_to_rec: dict[str, Any] = {}
        for seq, rec in enumerate(parsed.get("recommendations") or [], start=1):
            depends = Entry.search([("module_name", "in", rec.get("depends") or [])])
            impact = Entry.search([("module_name", "in", rec.get("impact_modules") or [])])
            tag_codes = rec.get("capability_tags") or []
            tag_ids: list[int] = []
            for code in tag_codes:
                tag = Tag.search([("technical_code", "=", code)], limit=1)
                if not tag:
                    tag = Tag.create({"name": code.replace("-", " ").title(), "technical_code": code})
                tag_ids.append(tag.id)
            related = Section.browse([int(x) for x in (rec.get("related_section_ids") or []) if x]).filtered(
                lambda s, brd=brd_doc: s.document_id.id == brd.id
            )
            affects_names = rec.get("affects_existing_modules") or []
            affects_ids: list[int] = []
            if Catalog is not None and affects_names:
                affects_ids = Catalog.search(
                    [("module_name", "in", list(affects_names))]
                ).ids
            cross_map = rec.get("cross_vertical_impact")
            cross_json = ""
            if isinstance(cross_map, dict):
                # Coerce values to list[str] for predictable storage.
                clean = {
                    str(k): [str(x) for x in (v if isinstance(v, list) else [])]
                    for k, v in cross_map.items()
                }
                cross_json = json.dumps(clean, ensure_ascii=False)
            compat = rec.get("compat_strategy")
            if compat not in ("extend", "abstract_base", "feature_flag", "fork_warning"):
                compat = False
            new_rec = Recommendation.create(
                {
                    "document_id": brd_doc.id,
                    "sequence": seq,
                    "name": rec.get("name") or f"custom_proposal_{seq}",
                    "scope": rec.get("scope") or "",
                    "capability_tag_ids": [(6, 0, tag_ids)],
                    "related_section_ids": [(6, 0, related.ids)],
                    "depends_on_module_ids": [(6, 0, depends.ids)],
                    "impact_module_ids": [(6, 0, impact.ids)],
                    "estimated_md": int(rec.get("estimated_md") or 0),
                    "severity": rec.get("severity") or "should_have",
                    "justification": rec.get("justification") or "",
                    "cross_vertical_impact_json": cross_json,
                    "breaking_change": bool(rec.get("breaking_change")),
                    "compat_strategy": compat,
                }
            )
            if "affects_existing_module_ids" in Recommendation._fields:
                new_rec.write({"affects_existing_module_ids": [(6, 0, affects_ids)]})
            name_to_rec[new_rec.name] = (new_rec, rec.get("depends_on_proposed") or [])

        # Second pass: sibling links.
        for rec_rec, sibling_names in name_to_rec.values():
            sibs = [name_to_rec[n][0].id for n in sibling_names if n in name_to_rec and name_to_rec[n][0].id != rec_rec.id]
            if sibs:
                rec_rec.write({"depends_on_proposed_ids": [(6, 0, sibs)]})

        # Persist diagnostic fields (truncated raw for UI surfacing).
        raw_responses = parsed.get("_raw_responses") or []
        raw_dump = "\n\n--- BATCH ---\n\n".join(raw_responses)
        if len(raw_dump) > 60000:
            raw_dump = raw_dump[:60000] + "\n…(truncated)"
        brd_doc.write({
            "state": "analyzed",
            "last_ai_raw": raw_dump or False,
            "last_ai_at": fields.Datetime.now(),
            "last_ai_section_count": len(parsed.get("sections") or []),
            "last_ai_recommendation_count": len(parsed.get("recommendations") or []),
        })
