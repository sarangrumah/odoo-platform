#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan ``addons/`` and emit ``catalog.json`` — the single source of truth for
the Erajaya platform feature catalog.

Nothing downstream (render_md, render_html, build_xlsx) reads ``addons/``; they
all read this file. That is what keeps the prose, the PDF and the spreadsheet
from disagreeing with each other about how many modules exist.

Usage:
    python3 build_catalog_json.py                 # write catalog.json
    python3 build_catalog_json.py --audit         # + catalog-audit.md
    python3 build_catalog_json.py --bootstrap     # propose DOMAIN_BY_MODULE, exit
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ADDONS = os.path.join(REPO, "addons")

sys.path.insert(0, HERE)
import catalog_scan as scan  # noqa: E402

ODOO_SERIES = "19.0"


# --- discovery --------------------------------------------------------------


def discover_modules() -> list[tuple[str, str, str]]:
    """Every directory under ``addons/`` holding a ``__manifest__.py``.

    Deliberately unbounded in depth: ``verticals/_template/custom_vertical_example``
    sits one level deeper than every other module, and a ``-maxdepth 3`` walk
    silently returns 157 instead of 158.
    """
    found = []
    for root, dirs, files in os.walk(ADDONS):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        if "__manifest__.py" not in files:
            continue
        rel = os.path.relpath(root, REPO).replace(os.sep, "/")
        group = os.path.relpath(root, ADDONS).split(os.sep)[0]
        found.append((os.path.basename(root), group, rel))
    return sorted(found, key=lambda t: (t[1], t[0]))


def _first_paragraph(text: str) -> str:
    for para in (text or "").strip().split("\n\n"):
        cleaned = " ".join(para.split())
        if cleaned:
            return cleaned[:600]
    return ""


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", REPO, *args],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


# --- per-module assembly ----------------------------------------------------


def build_module(name: str, group: str, relpath: str, taxonomy) -> dict:
    abspath = os.path.join(REPO, relpath)
    raw = scan.read_manifest(abspath) or {}

    manifest = {
        "name": raw.get("name") or name,
        "summary": raw.get("summary") or "",
        "description_first_para": _first_paragraph(raw.get("description") or ""),
        "category": raw.get("category") or "",
        "version": raw.get("version") or "",
        "license": raw.get("license") or "",
        "author": raw.get("author") or "",
        "depends": list(raw.get("depends") or []),
        "application": bool(raw.get("application")),
        "auto_install": bool(raw.get("auto_install")),
        "installable": raw.get("installable", True) is not False,
        "capability_tags": list(raw.get("capability_tags") or []),
        "external_dependencies": raw.get("external_dependencies") or {},
        "countries": list(raw.get("countries") or []),
    }

    models = scan.scrape_models(abspath)
    source = {
        "models_own": models["models_own"],
        "models_inherit": models["models_inherit"],
        "wizards": models["wizards"],
        "fields_by_model": models["fields_by_model"],
        "models_xml": scan.scrape_xml_models(abspath),
        "routes": scan.scrape_routes(abspath),
        "security_groups": scan.scrape_security_groups(abspath),
        "crons": scan.count_crons(abspath),
        "file_counts": scan.count_files(abspath),
        "test_files": scan.test_files(abspath),
        "source_hash": scan.compute_source_hash(abspath),
    }
    source["has_tests"] = source["test_files"] > 0

    knowledge = load_knowledge(name, abspath, manifest, source)
    scope = taxonomy.scope_for(name, group)

    return {
        "name": name,
        "group": group,
        "relpath": relpath,
        "manifest": manifest,
        "knowledge": knowledge,
        "source": source,
        "domain": taxonomy.DOMAIN_BY_MODULE[name],
        "domain_secondary": list(taxonomy.DOMAIN_SECONDARY.get(name, [])),
        "scope": scope,
        "tenants": list(taxonomy.TENANTS_BY_MODULE.get(name, [])),
        "maturity": infer_maturity(name, group, manifest, source, taxonomy),
        "confidence": confidence_for(knowledge),
        "audit_flags": [],
        "id": taxonomy.id_labels(name, manifest),
    }


def load_knowledge(name: str, abspath: str, manifest: dict, source: dict) -> dict:
    """Precedence: hand-written override > MODULE_KNOWLEDGE.md > synthesised.

    Overrides live under ``docs/`` rather than in ``addons/`` on purpose: they
    are catalog content, not generator output, and must not be picked up by
    ``scripts/check_knowledge_drift.py`` as if they were.
    """
    override = os.path.join(HERE, "overrides", f"{name}.md")
    knowledge_md = os.path.join(abspath, "MODULE_KNOWLEDGE.md")

    if os.path.isfile(override):
        with open(override, "r", encoding="utf-8") as fh:
            parsed = scan.parse_knowledge(fh.read())
        parsed.update({"present": True, "origin": "override", "status": "override"})
    elif os.path.isfile(knowledge_md):
        with open(knowledge_md, "r", encoding="utf-8") as fh:
            parsed = scan.parse_knowledge(fh.read())
        parsed.update({"present": True, "origin": "module"})
    else:
        purpose = manifest["summary"]
        extra = manifest["description_first_para"]
        if extra and extra.lower() not in purpose.lower():
            purpose = f"{purpose} {extra}".strip()
        parsed = {
            "present": False,
            "origin": "synthesised",
            "status": "missing",
            "generated_at": "",
            "generator": "",
            "manifest_version_at_gen": "",
            "purpose": purpose,
            "business_flow": [],
            "key_models": [{"name": m, "desc": m} for m in source["models_own"]],
            "important_fields": [],
        }

    at_gen = parsed.get("manifest_version_at_gen") or ""
    parsed["version_drift"] = bool(at_gen and at_gen != manifest["version"])
    return parsed


def infer_maturity(name, group, manifest, source, taxonomy) -> str:
    if name in taxonomy.MATURITY_OVERRIDE:
        return taxonomy.MATURITY_OVERRIDE[name]
    if group == "_vendor":
        return "vendor"
    if not manifest["installable"]:
        return "disabled"
    has_content = source["models_own"] or source["routes"] or source["file_counts"]["xml"]
    if not has_content:
        return "scaffold"
    if source["has_tests"]:
        return "production"
    return "beta"


def confidence_for(knowledge: dict) -> str:
    return {
        "override": "high",
        "reviewed": "high",
        "draft": "medium",
        "missing": "low",
    }.get(knowledge["status"], "low")


# --- audit ------------------------------------------------------------------

# Models a knowledge file may legitimately name without the module declaring
# them: core Odoo models it extends, and abstract/report helpers.
_AUDIT_IGNORE_PREFIXES = ("ir.", "res.", "mail.", "report.", "base.")


def _is_model_token(token: str) -> bool:
    """Odoo model names are dotted and all-lowercase.

    Filters out the class and method names that leak into the ``Key Models``
    section of a generated knowledge file — ``http.Controller`` is not a model,
    and flagging it as a hallucination just buries the real findings.
    """
    return bool(token) and token == token.lower() and "." in token


def audit(modules: list[dict]) -> None:
    """Flag claims in the knowledge files that the source does not support.

    111 of the 115 MODULE_KNOWLEDGE.md files are unreviewed LLM output. Reading
    all of them by hand is the expensive path; this narrows the manual review to
    the entries that actually look wrong.

    Resolution is **global**, not per-module: an Odoo model is routinely defined
    in one addon and extended in another, so checking a claim only against its
    own module's source manufactures false positives (a WMS report naming
    ``stock.move.line``, a hub field that ``custom_tenant_infra`` adds).
    """
    known_models: set[str] = set()
    known_fields: set[str] = set()
    known_field_names: set[str] = set()
    for mod in modules:
        src = mod["source"]
        known_models.update(src["models_own"])
        known_models.update(src["models_inherit"])
        known_models.update(src["models_xml"])
        for model, fields in src["fields_by_model"].items():
            known_fields.update(f"{model}.{f}" for f in fields)
            known_field_names.update(fields)

    for mod in modules:
        k = mod["knowledge"]
        if not k["present"]:
            continue
        declared = set(mod["source"]["models_own"])
        flags = []

        phantom_models = sorted({
            km["name"] for km in k["key_models"]
            if _is_model_token(km["name"])
            and km["name"] not in known_models
            and not km["name"].startswith(_AUDIT_IGNORE_PREFIXES)
        })
        if phantom_models:
            flags.append({"kind": "phantom_model", "items": phantom_models})

        phantom_fields = sorted({
            f"{f['model']}.{f['field']}" for f in k["important_fields"]
            # A leading underscore is a class constant or an SQL constraint
            # name, not a field. A dotted token that is itself a known model is
            # the parser mis-splitting `custom.foo.wizard.line` into model+field.
            if f["model"] and f["field"]
            and not f["field"].startswith("_")
            and f"{f['model']}.{f['field']}" not in known_fields
            and f"{f['model']}.{f['field']}" not in known_models
            and f["model"] in known_models
            # A field declared on a mixin and surfaced on the inheriting model
            # is never attributed to that model by a static scan. Accepting any
            # field name that exists somewhere in the codebase clears those
            # without also clearing an invented name, which will not collide.
            and f["field"] not in known_field_names
        })
        if phantom_fields:
            flags.append({"kind": "phantom_field", "items": phantom_fields})

        undocumented = sorted(
            declared - {km["name"] for km in k["key_models"]}
        )
        if undocumented:
            flags.append({"kind": "undocumented_model", "items": undocumented})

        if k["version_drift"]:
            flags.append({
                "kind": "version_drift",
                "items": [f"{k['manifest_version_at_gen']} → {mod['manifest']['version']}"],
            })

        mod["audit_flags"] = flags
        # A phantom model means the prose describes something that is not there.
        # Suppress the model list and stop claiming high confidence.
        if phantom_models:
            mod["confidence"] = "low"
            mod["knowledge"]["key_models"] = []


def write_audit_report(modules: list[dict], path: str) -> dict:
    tally = collections.Counter()
    lines = [
        "# Catalog accuracy audit",
        "",
        "Generated by `build_catalog_json.py --audit`. Each entry is a claim in a",
        "knowledge file that the source tree does not support. 111 of the 115",
        "`MODULE_KNOWLEDGE.md` files are unreviewed LLM output, so this is the gate",
        "that decides which of them can be quoted to a client.",
        "",
        "- **`phantom_model`** — the strongest signal. A model named in *Key Models*",
        "  that no module declares, inherits, or writes XML records against. These",
        "  auto-downgrade the module to `confidence: low` and its model list is",
        "  dropped from the appendix.",
        "- **`phantom_field`** — a `model.field` that exists nowhere. Resolution is",
        "  global and also accepts any field name seen elsewhere, because a static",
        "  scan cannot attribute a mixin-provided or upstream-core field to the",
        "  model that surfaces it. Survivors are worth reading; they are not",
        "  automatically wrong.",
        "- **`undocumented_model`** — the module declares a model the knowledge file",
        "  never mentions. A completeness hint, not an error.",
        "- **`version_drift`** — the knowledge file was generated against an older",
        "  manifest version. The prose may predate recent behaviour.",
        "",
    ]
    flagged = [m for m in modules if m["audit_flags"]]
    for mod in flagged:
        for f in mod["audit_flags"]:
            tally[f["kind"]] += 1
    lines.append("| Kind | Count |")
    lines.append("| --- | --- |")
    for kind, count in sorted(tally.items()):
        lines.append(f"| `{kind}` | {count} |")
    lines.append("")
    lines.append(f"{len(flagged)} of {len(modules)} modules carry at least one flag.")
    lines.append("")

    for mod in flagged:
        serious = [f for f in mod["audit_flags"] if f["kind"] != "undocumented_model"]
        if not serious:
            continue
        lines.append(f"## `{mod['name']}` ({mod['relpath']})")
        lines.append("")
        for f in serious:
            lines.append(f"- **{f['kind']}**: {', '.join('`%s`' % i for i in f['items'])}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return dict(tally)


# --- bootstrap --------------------------------------------------------------


def bootstrap(found) -> None:
    """Print one line per module so the domain mapping can be written by hand.

    This exists to seed ``taxonomy.py`` once. It is not part of the build path —
    a heuristic left in the pipeline would quietly reclassify modules later.
    """
    for name, group, relpath in found:
        raw = scan.read_manifest(os.path.join(REPO, relpath)) or {}
        tags = ",".join(raw.get("capability_tags") or []) or "-"
        print("\t".join([
            group, name,
            str(raw.get("category") or "-"),
            tags,
            (raw.get("summary") or "-")[:90],
        ]))


# --- main -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="also write catalog-audit.md")
    ap.add_argument("--bootstrap", action="store_true", help="dump module facts and exit")
    ap.add_argument("--out", default=os.path.join(HERE, "catalog.json"))
    args = ap.parse_args()

    found = discover_modules()
    if args.bootstrap:
        bootstrap(found)
        return 0

    import taxonomy

    on_disk = {name for name, _g, _r in found}
    classified = set(taxonomy.DOMAIN_BY_MODULE)
    missing = sorted(on_disk - classified)
    stale = sorted(classified - on_disk)
    if missing or stale:
        if missing:
            print("Modules on disk with no domain in taxonomy.py:", file=sys.stderr)
            for m in missing:
                print(f"  + {m}", file=sys.stderr)
        if stale:
            print("Modules in taxonomy.py that no longer exist:", file=sys.stderr)
            for m in stale:
                print(f"  - {m}", file=sys.stderr)
        return 2

    modules = [build_module(n, g, r, taxonomy) for n, g, r in found]
    if args.audit:
        audit(modules)

    by_group = collections.Counter(m["group"] for m in modules)
    by_domain = collections.Counter(m["domain"] for m in modules)
    by_scope = collections.Counter(m["scope"] for m in modules)
    by_confidence = collections.Counter(m["confidence"] for m in modules)

    domains = []
    for d in taxonomy.DOMAINS:
        names = sorted(m["name"] for m in modules if m["domain"] == d["id"])
        domains.append({**d, "module_count": len(names), "module_names": names})

    gaps = taxonomy.load_gaps(os.path.join(HERE, "gaps.yaml"))

    catalog = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": _git("rev-parse", "--short", "HEAD"),
            "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain")),
            "odoo_series": ODOO_SERIES,
            "counts": {
                "modules_total": len(modules),
                "by_group": dict(sorted(by_group.items())),
                "by_domain": dict(sorted(by_domain.items())),
                "by_scope": dict(sorted(by_scope.items())),
                "by_confidence": dict(sorted(by_confidence.items())),
                "knowledge_present": sum(1 for m in modules if m["knowledge"]["present"]),
                "knowledge_reviewed": sum(1 for m in modules if m["knowledge"]["status"] == "reviewed"),
                "knowledge_override": sum(1 for m in modules if m["knowledge"]["status"] == "override"),
                "knowledge_missing": sum(1 for m in modules if not m["knowledge"]["present"]),
            },
        },
        "domains": domains,
        "tenants": taxonomy.TENANTS,
        "modules": modules,
        "gaps": gaps,
    }

    if args.audit:
        tally = write_audit_report(modules, os.path.join(HERE, "catalog-audit.md"))
        catalog["meta"]["counts"]["audit_flags"] = tally

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")

    print(f"{len(modules)} modules → {os.path.relpath(args.out, REPO)}")
    for group, count in sorted(by_group.items()):
        print(f"  {group:<15} {count:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
