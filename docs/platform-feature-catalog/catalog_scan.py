# -*- coding: utf-8 -*-
"""Static analysis of an Odoo addon directory, with no Odoo import.

The regexes and the hashing scheme are ported from
``addons/operations/custom_brd_analyzer/models/module_capability_entry.py`` so
the catalog and the in-Odoo module registry agree on what a module contains.
Keep them in sync: a divergence here shows up as a phantom-model false
positive in the audit report, not as an error.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re

# --- model / field / route scraping ----------------------------------------

RE_NAME = re.compile(r"^\s*_name\s*=\s*['\"]([\w.]+)['\"]", re.MULTILINE)
RE_INHERIT_SINGLE = re.compile(r"^\s*_inherit\s*=\s*['\"]([\w.]+)['\"]", re.MULTILINE)
RE_INHERIT_LIST = re.compile(r"^\s*_inherit\s*=\s*\[([^\]]+)\]", re.MULTILINE)
RE_FIELD = re.compile(r"^\s+(\w+)\s*=\s*fields\.(\w+)\s*\(", re.MULTILINE)
RE_ROUTE = re.compile(r"@(?:http\.)?route\(\s*['\"]([^'\"]+)['\"]")
RE_ROUTE_LIST = re.compile(r"@(?:http\.)?route\(\s*\[([^\]]+)\]")
RE_CLASS_SPLIT = re.compile(r"^class\s+", re.MULTILINE)

MODEL_DIRS = ("models", "wizards", "wizard", "report", "reports")


def read_manifest(path: str) -> dict | None:
    """``ast.literal_eval`` the manifest. Never ``exec`` — manifests are data."""
    manifest_file = os.path.join(path, "__manifest__.py")
    if not os.path.isfile(manifest_file):
        return None
    try:
        with open(manifest_file, "r", encoding="utf-8") as fh:
            return ast.literal_eval(fh.read())
    except (OSError, ValueError, SyntaxError):
        return None


def _py_files(path: str, subdirs) -> list[str]:
    out = []
    for sub in subdirs:
        base = os.path.join(path, sub)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            out.extend(os.path.join(root, fn) for fn in files if fn.endswith(".py"))
    return sorted(out)


def scrape_models(path: str) -> dict:
    """Harvest declared models, inherited models, fields and wizards.

    ``fields_by_model`` is what the audit uses to spot phantom fields, so it is
    kept complete rather than capped the way the in-Odoo scraper caps it.
    """
    own: set[str] = set()
    inherit: set[str] = set()
    wizards: set[str] = set()
    fields_by_model: dict[str, set[str]] = {}

    for fp in _py_files(path, MODEL_DIRS):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        is_wizard_dir = os.path.basename(os.path.dirname(fp)) in ("wizards", "wizard")
        # Attribute fields per class block, not per file: a single .py often
        # holds several models, and folding them all onto the first one
        # manufactures "phantom field" findings during the audit.
        for block in RE_CLASS_SPLIT.split(src):
            names = RE_NAME.findall(block)
            block_inherit = list(RE_INHERIT_SINGLE.findall(block))
            for chunk in RE_INHERIT_LIST.findall(block):
                block_inherit.extend(re.findall(r"['\"]([\w.]+)['\"]", chunk))
            own.update(names)
            inherit.update(block_inherit)
            if is_wizard_dir:
                wizards.update(names)
            wizards.update(n for n in names if ".wizard" in n)

            owner = (names[0] if names else None) or (block_inherit[0] if block_inherit else None)
            if owner:
                bucket = fields_by_model.setdefault(owner, set())
                bucket.update(fname for fname, _ftype in RE_FIELD.findall(block))

    return {
        "models_own": sorted(own),
        "models_inherit": sorted(inherit - own),
        "wizards": sorted(wizards),
        "fields_by_model": {k: sorted(v) for k, v in sorted(fields_by_model.items())},
    }


def scrape_routes(path: str) -> list[str]:
    routes: set[str] = set()
    for fp in _py_files(path, ("controllers",)):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        routes.update(RE_ROUTE.findall(src))
        for chunk in RE_ROUTE_LIST.findall(src):
            routes.update(re.findall(r"['\"]([^'\"]+)['\"]", chunk))
    return sorted(routes)


def scrape_security_groups(path: str) -> list[str]:
    csv_path = os.path.join(path, "security", "ir.model.access.csv")
    if not os.path.isfile(csv_path):
        return []
    try:
        with open(csv_path, "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return []
    return sorted(set(re.findall(r"\b([a-z_][\w]*\.group_[\w]+)\b", src)))


RE_XML_RECORD_MODEL = re.compile(r'<record[^>]*\bmodel="([\w.]+)"')


def scrape_xml_models(path: str) -> list[str]:
    """Models the module writes records against in its XML data.

    A data-only module (opening balances, CoA seeds) declares no Python model
    at all, so without this its knowledge file looks like it is describing
    models that do not exist.
    """
    found: set[str] = set()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for fn in files:
            if not fn.endswith(".xml"):
                continue
            try:
                with open(os.path.join(root, fn), "r", encoding="utf-8") as fh:
                    found.update(RE_XML_RECORD_MODEL.findall(fh.read()))
            except OSError:
                continue
    return sorted(found)


def count_crons(path: str) -> int:
    """Count ``ir.cron`` records declared in the module's XML data."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            if not fn.endswith(".xml"):
                continue
            try:
                with open(os.path.join(root, fn), "r", encoding="utf-8") as fh:
                    total += fh.read().count('model="ir.cron"')
            except OSError:
                continue
    return total


def count_files(path: str) -> dict:
    counts = {"py": 0, "xml": 0, "js": 0, "csv": 0}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for fn in files:
            ext = fn.rsplit(".", 1)[-1] if "." in fn else ""
            if ext in counts:
                counts[ext] += 1
    return counts


def test_files(path: str) -> int:
    tests_dir = os.path.join(path, "tests")
    if not os.path.isdir(tests_dir):
        return 0
    return sum(1 for fn in os.listdir(tests_dir) if fn.startswith("test_") and fn.endswith(".py"))


def compute_source_hash(path: str) -> str:
    """SHA-256 over manifest + every .py under models/controllers/wizards.

    Same input set and framing bytes as the in-Odoo scraper, so hashes are
    comparable across the two implementations.
    """
    h = hashlib.sha256()
    candidates: list[str] = []
    manifest_p = os.path.join(path, "__manifest__.py")
    if os.path.isfile(manifest_p):
        candidates.append(manifest_p)
    candidates.extend(_py_files(path, ("models", "controllers", "wizards", "wizard")))
    for fp in sorted(candidates):
        rel = os.path.relpath(fp, path).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            with open(fp, "rb") as fh:
                h.update(fh.read())
        except OSError:
            continue
        h.update(b"\n---FILE---\n")
    return h.hexdigest()


# --- MODULE_KNOWLEDGE.md / override parsing --------------------------------

_SECTION_ALIASES = {
    "purpose": "purpose",
    "business flow": "business_flow",
    "key models": "key_models",
    "important fields": "important_fields",
}

_MODEL_TOKEN = re.compile(r"`([a-z_][\w.]*\.[\w.]+)`")
_FIELD_TOKEN = re.compile(r"`([a-z_][\w.]*)\.(\w+)`")


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Parsed by hand — the frontmatter is a
    flat ``key: value`` block, so pulling in PyYAML here buys nothing."""
    if not raw.lstrip().startswith("---"):
        return {}, raw
    stripped = raw.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}, raw
    fm_raw = stripped[3:end]
    rest_start = stripped.find("\n", end + 4)
    body = stripped[rest_start + 1 :] if rest_start != -1 else ""
    fm = {}
    for line in fm_raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm, body


_BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def _bullets(block: str) -> list[str]:
    """Collect top-level bullets, folding their continuation lines in.

    Accepts both ``- `` and ``1. `` markers: the generated knowledge files use
    dashes, but a hand-written override describing a sequence of steps naturally
    numbers them, and silently dropping those would empty the Business Flow.
    """
    out: list[str] = []
    for line in block.splitlines():
        if _BULLET.match(line):
            out.append(_BULLET.sub("", line).strip())
        elif out and line.strip() and line.startswith((" ", "\t")):
            out[-1] += " " + line.strip()
    return out


def parse_knowledge(raw: str) -> dict:
    """Parse a MODULE_KNOWLEDGE.md (or an override with the same headings)."""
    fm, body = _split_frontmatter(raw)
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            key = m.group(1).strip().lower()
            current = _SECTION_ALIASES.get(key)
            buf = []
            continue
        if current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()

    key_models = []
    for item in _bullets(sections.get("key_models", "")):
        tok = _MODEL_TOKEN.search(item)
        key_models.append(
            {
                "name": tok.group(1) if tok else "",
                "desc": item,
            }
        )
    important_fields = []
    for item in _bullets(sections.get("important_fields", "")):
        tok = _FIELD_TOKEN.search(item)
        important_fields.append(
            {
                "model": tok.group(1) if tok else "",
                "field": tok.group(2) if tok else "",
                "desc": item,
            }
        )

    status = (fm.get("status") or "draft").lower()
    if status not in ("draft", "reviewed", "override"):
        status = "draft"
    return {
        "status": status,
        "generated_at": fm.get("generated_at") or "",
        "generator": fm.get("generator") or "",
        "manifest_version_at_gen": fm.get("manifest_version") or "",
        "purpose": sections.get("purpose", "").strip(),
        "business_flow": _bullets(sections.get("business_flow", "")),
        "key_models": key_models,
        "important_fields": important_fields,
    }
