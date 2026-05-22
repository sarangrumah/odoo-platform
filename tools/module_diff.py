#!/usr/bin/env python3
"""
module_diff.py — Inventory and compare Odoo addons across multiple roots.

Purpose (plan P1):
  Hub at E:/Projects/Odoo/platform must absorb generic features from
  vertical repos (Arkaim, rnd-ppob, JDS) without duplication. This tool
  walks __manifest__.py files in each given root, parses model files for
  _name / _inherit / field declarations, and emits a markdown report that
  highlights:
    - Per-project module inventory
    - Models that are NEW in a vertical but ABSENT in the hub
      (port-to-hub candidates)
    - Models that ALREADY exist in the hub (vertical should depend,
      not duplicate)
    - Manifest depends graph & maturity heuristic
    - Controller route inventory (for HHT / API surface analysis)

Usage:
  python tools/module_diff.py \
    --hub  E:/Projects/Odoo/platform/addons \
    --vertical arkaim=E:/Projects/Odoo/arkaaim/addons \
    --vertical ppob=E:/Projects/Odoo/rnd-ppob/addons \
    --vertical jds=E:/Projects/Odoo/jds-odoo/addons \
    --out  E:/Projects/Odoo/platform/docs/audit/module-diff.md

Notes:
  - Pure ast parsing; no Odoo runtime required. Safe to run offline.
  - Skip _vendor and OCA-style vendored bundles (manifest path heuristic).
  - "Maturity heuristic" = (model_count, view_count, test_count, controller_count)
    rolled into scaffold / partial / production label.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SKIP_DIR_NAMES = {"_vendor", "__pycache__", "static", "i18n", "node_modules"}
SKIP_MANIFEST_PARENTS = {"_vendor"}  # any ancestor name in this set => skip
VENDORED_HINTS = (
    "om_account",
    "accounting_pdf_reports",
    "base_accounting_kit",
    "dynamic_accounts_report",
    "tk_purchase_advance_payment",
    "browseinfo_",
    "request_uri_fix",
)


@dataclass
class ModelInfo:
    name: str | None = None
    inherit: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)  # field-name only
    file: str = ""


@dataclass
class ModuleInfo:
    project: str
    module: str
    path: Path
    version: str = ""
    depends: list[str] = field(default_factory=list)
    summary: str = ""
    application: bool = False
    installable: bool = True
    models_own: list[ModelInfo] = field(default_factory=list)  # _name
    models_inherit: list[ModelInfo] = field(default_factory=list)  # _inherit
    view_files: int = 0
    test_files: int = 0
    controller_routes: list[str] = field(default_factory=list)
    is_vendored: bool = False

    @property
    def model_count(self) -> int:
        return len(self.models_own) + len(self.models_inherit)

    @property
    def maturity(self) -> str:
        # Heuristic. Tune by inspection.
        own = len(self.models_own)
        inh = len(self.models_inherit)
        tests = self.test_files
        views = self.view_files
        ctrl = len(self.controller_routes)
        score = own * 3 + inh * 1 + tests * 2 + min(views, 10) + ctrl
        if score < 3:
            return "scaffold"
        if score < 12:
            return "partial"
        return "production"


def _parse_manifest(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        node = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None
    for n in ast.walk(node):
        if isinstance(n, ast.Expression):
            n = n.body
        if isinstance(n, ast.Dict):
            try:
                return ast.literal_eval(n)
            except Exception:
                continue
    # Fallback: scan top-level for `{...}` literal
    try:
        return ast.literal_eval(text.strip().rstrip(";").lstrip("# -*- coding: utf-8 -*-").strip())
    except Exception:
        return None


def _is_vendored(manifest_path: Path) -> bool:
    parts_lower = [p.lower() for p in manifest_path.parts]
    for p in parts_lower:
        if p in SKIP_MANIFEST_PARENTS:
            return True
    name = manifest_path.parent.name.lower()
    if any(name.startswith(h) for h in VENDORED_HINTS):
        return True
    if re.search(r"-\d+\.\d+\.\d+", str(manifest_path)):
        return True
    return False


def _extract_models_from_file(file_path: Path) -> list[ModelInfo]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(file_path))
    except (OSError, SyntaxError):
        return []
    results: list[ModelInfo] = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        info = ModelInfo(file=str(file_path))
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                tgt = stmt.targets[0]
                if isinstance(tgt, ast.Name):
                    val = stmt.value
                    if tgt.id == "_name" and isinstance(val, ast.Constant) and isinstance(val.value, str):
                        info.name = val.value
                    elif tgt.id == "_inherit":
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            info.inherit.append(val.value)
                        elif isinstance(val, (ast.List, ast.Tuple)):
                            for el in val.elts:
                                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                    info.inherit.append(el.value)
                    else:
                        # Field heuristic: RHS is a Call to fields.<Type>
                        if isinstance(val, ast.Call):
                            fn = val.func
                            if (
                                isinstance(fn, ast.Attribute)
                                and isinstance(fn.value, ast.Name)
                                and fn.value.id == "fields"
                            ):
                                info.fields.append(tgt.id)
        if info.name or info.inherit:
            results.append(info)
    return results


def _extract_controller_routes(file_path: Path) -> list[str]:
    """Return route strings from @http.route('/x', ...) decorators."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(file_path))
    except (OSError, SyntaxError):
        return []
    routes: list[str] = []
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for dec in func.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            if call is None:
                continue
            fn = call.func
            is_route = False
            if isinstance(fn, ast.Attribute) and fn.attr == "route":
                is_route = True
            elif isinstance(fn, ast.Name) and fn.id == "route":
                is_route = True
            if not is_route:
                continue
            if call.args:
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    routes.append(first.value)
                elif isinstance(first, (ast.List, ast.Tuple)):
                    for el in first.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            routes.append(el.value)
    return routes


def _scan_module(project: str, manifest_path: Path) -> ModuleInfo | None:
    manifest = _parse_manifest(manifest_path)
    if not manifest:
        return None
    module_dir = manifest_path.parent
    info = ModuleInfo(
        project=project,
        module=module_dir.name,
        path=module_dir,
        version=str(manifest.get("version", "") or ""),
        depends=list(manifest.get("depends", []) or []),
        summary=str(manifest.get("summary", "") or "")[:200],
        application=bool(manifest.get("application", False)),
        installable=bool(manifest.get("installable", True)),
        is_vendored=_is_vendored(manifest_path),
    )

    # Walk module dir for models, views, tests, controllers
    for root, dirs, files in os.walk(module_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        rel_root = Path(root).relative_to(module_dir)
        top = rel_root.parts[0] if rel_root.parts else ""
        for fname in files:
            fpath = Path(root) / fname
            if top == "views" and fname.endswith(".xml"):
                info.view_files += 1
            elif top == "tests" and fname.endswith(".py") and fname.startswith("test_"):
                info.test_files += 1
            elif top == "models" and fname.endswith(".py") and fname != "__init__.py":
                info.models_own.extend([m for m in _extract_models_from_file(fpath) if m.name])
                info.models_inherit.extend([m for m in _extract_models_from_file(fpath) if m.inherit and not m.name])
            elif top == "controllers" and fname.endswith(".py") and fname != "__init__.py":
                info.controller_routes.extend(_extract_controller_routes(fpath))
    return info


def scan_root(project: str, root: Path) -> list[ModuleInfo]:
    if not root.exists():
        print(f"WARN: root not found for {project!r}: {root}", file=sys.stderr)
        return []
    modules: list[ModuleInfo] = []
    for manifest in root.rglob("__manifest__.py"):
        if _is_vendored(manifest):
            continue
        info = _scan_module(project, manifest)
        if info is None:
            print(f"WARN: failed to parse {manifest}", file=sys.stderr)
            continue
        modules.append(info)
    return modules


# --- Report rendering ----------------------------------------------------


def render_markdown(by_project: dict[str, list[ModuleInfo]], hub_project: str) -> str:
    out: list[str] = []
    out.append("# Module Diff Report — Hub vs Verticals\n")
    out.append(f"Generated by `tools/module_diff.py`. Hub project: **{hub_project}**.\n")

    # Section 1: Inventory per project
    out.append("\n## 1. Inventory per Project\n")
    for project, mods in by_project.items():
        out.append(f"\n### {project} — {len(mods)} modules\n")
        out.append("| Module | Version | Maturity | Own models | Inherit | Views | Tests | Routes | Depends |")
        out.append("|---|---|---|---:|---:|---:|---:|---:|---|")
        for m in sorted(mods, key=lambda x: x.module):
            deps_str = ", ".join(m.depends[:4]) + (f", … +{len(m.depends) - 4}" if len(m.depends) > 4 else "")
            out.append(
                f"| `{m.module}` | {m.version} | {m.maturity} "
                f"| {len(m.models_own)} | {len(m.models_inherit)} "
                f"| {m.view_files} | {m.test_files} | {len(m.controller_routes)} "
                f"| {deps_str} |"
            )

    # Section 2: Duplicate model coverage (vertical model also defined in hub)
    hub_mods = by_project.get(hub_project, [])
    hub_own_models: dict[str, str] = {}  # _name -> hub module name
    hub_inherit_models: dict[str, set[str]] = defaultdict(set)  # inherited -> {hub modules}
    for m in hub_mods:
        for mo in m.models_own:
            if mo.name:
                hub_own_models[mo.name] = m.module
        for mo in m.models_inherit:
            for inh in mo.inherit:
                hub_inherit_models[inh].add(m.module)

    out.append("\n## 2. Duplicate Model Coverage (Vertical defines what Hub already has)\n")
    out.append(
        "If a vertical module defines a `_name` that already exists as `_name` in the hub, that is hard duplication and needs renaming or merging.\n"
    )
    out.append("\n| Vertical project | Vertical module | Duplicated `_name` | Already in Hub module |")
    out.append("|---|---|---|---|")
    any_dup = False
    for project, mods in by_project.items():
        if project == hub_project:
            continue
        for m in mods:
            for mo in m.models_own:
                if mo.name and mo.name in hub_own_models:
                    out.append(f"| {project} | `{m.module}` | `{mo.name}` | `{hub_own_models[mo.name]}` |")
                    any_dup = True
    if not any_dup:
        out.append("| — | — | _(no hard duplicates)_ | — |")

    # Section 3: Inherit-extension overlap
    out.append("\n## 3. Same-Model Extension Overlap (Vertical & Hub both inherit the same model)\n")
    out.append("These need careful merge — both projects added fields/behavior to the same base model.\n")
    out.append("\n| Inherited model | Hub modules | Vertical modules |")
    out.append("|---|---|---|")
    vertical_inherit_index: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for project, mods in by_project.items():
        if project == hub_project:
            continue
        for m in mods:
            for mo in m.models_inherit:
                for inh in mo.inherit:
                    vertical_inherit_index[inh][project].add(m.module)
    overlap_keys = sorted(set(vertical_inherit_index.keys()) & set(hub_inherit_models.keys()))
    if not overlap_keys:
        out.append("| _(none)_ | — | — |")
    for inh in overlap_keys:
        hub_str = ", ".join(sorted(hub_inherit_models[inh]))
        vert_parts = []
        for project, mset in vertical_inherit_index[inh].items():
            vert_parts.append(f"{project}: " + ", ".join(sorted(mset)))
        out.append(f"| `{inh}` | {hub_str} | {' / '.join(vert_parts)} |")

    # Section 4: Port-to-hub candidates (vertical model NOT in hub at all)
    out.append("\n## 4. Port-to-Hub Candidates (Vertical-defined models absent from Hub)\n")
    out.append("These are models the hub does not own or extend. If the capability is generic, port to hub.\n")
    out.append("\n| Project | Module | Model `_name` | Sample fields | Source file |")
    out.append("|---|---|---|---|---|")
    candidates_count = 0
    for project, mods in by_project.items():
        if project == hub_project:
            continue
        for m in mods:
            if m.is_vendored:
                continue
            for mo in m.models_own:
                if mo.name and mo.name not in hub_own_models and mo.name not in hub_inherit_models:
                    fields_preview = ", ".join(mo.fields[:6]) + ("…" if len(mo.fields) > 6 else "")
                    src_rel = mo.file.replace("\\", "/")
                    out.append(f"| {project} | `{m.module}` | `{mo.name}` | {fields_preview} | `{src_rel}` |")
                    candidates_count += 1
    if candidates_count == 0:
        out.append("| _(none — all vertical models already represented in hub)_ | — | — | — | — |")

    # Section 5: Controller route inventory (relevant for HHT / API surface)
    out.append("\n## 5. Controller Routes (HTTP / API Surface)\n")
    out.append("\n| Project | Module | Route |")
    out.append("|---|---|---|")
    for project, mods in by_project.items():
        for m in sorted(mods, key=lambda x: x.module):
            for route in m.controller_routes:
                out.append(f"| {project} | `{m.module}` | `{route}` |")

    # Section 6: Hub gap summary
    out.append("\n## 6. Action Summary\n")
    out.append(
        f"- Hub modules inventoried: **{len(hub_mods)}** "
        f"({sum(1 for m in hub_mods if m.maturity == 'production')} production, "
        f"{sum(1 for m in hub_mods if m.maturity == 'partial')} partial, "
        f"{sum(1 for m in hub_mods if m.maturity == 'scaffold')} scaffold)"
    )
    for project, mods in by_project.items():
        if project == hub_project:
            continue
        prod = sum(1 for m in mods if m.maturity == "production")
        out.append(f"- {project}: {len(mods)} modules ({prod} production-grade)")
    out.append(f"- Port-to-hub candidate models: **{candidates_count}**")
    out.append(f"- Same-model overlaps needing merge: **{len(overlap_keys)}**")
    return "\n".join(out) + "\n"


# --- Main ----------------------------------------------------------------


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", required=True, help="Path to hub addons root")
    parser.add_argument(
        "--vertical",
        action="append",
        default=[],
        help="Vertical in form name=path/to/addons (repeatable)",
    )
    parser.add_argument("--out", required=True, help="Output markdown file path")
    parser.add_argument("--json", help="Optional JSON dump of structured data")
    args = parser.parse_args(list(argv) if argv is not None else None)

    by_project: dict[str, list[ModuleInfo]] = {}
    by_project["hub"] = scan_root("hub", Path(args.hub))
    for spec in args.vertical:
        if "=" not in spec:
            print(f"ERROR: --vertical expects name=path, got: {spec}", file=sys.stderr)
            return 2
        name, path = spec.split("=", 1)
        by_project[name.strip()] = scan_root(name.strip(), Path(path.strip()))

    report = render_markdown(by_project, hub_project="hub")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")

    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            project: [
                {
                    "module": m.module,
                    "version": m.version,
                    "maturity": m.maturity,
                    "depends": m.depends,
                    "models_own": [{"name": mo.name, "fields": mo.fields, "file": mo.file} for mo in m.models_own],
                    "models_inherit": [
                        {"inherit": mo.inherit, "fields": mo.fields, "file": mo.file} for mo in m.models_inherit
                    ],
                    "views": m.view_files,
                    "tests": m.test_files,
                    "routes": m.controller_routes,
                }
                for m in mods
            ]
            for project, mods in by_project.items()
        }
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Wrote {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
