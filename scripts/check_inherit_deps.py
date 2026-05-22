#!/usr/bin/env python3
"""Static checker: for every `_inherit = "model"` in a custom module, ensure
the module that DEFINES that model (via `_name = "model"`) is reachable through
the manifest's `depends` graph.

Scope: addons/ (excluding _vendor).  Vendor / stock Odoo / Enterprise modules
are treated as "external" — if a model isn't defined in any scanned module,
we assume it comes from stock Odoo and skip it (we can't validate those here).
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict

ROOT = os.path.join("e:/Projects/Odoo/platform", "addons")
SKIP_DIRS = {"_vendor", "__pycache__"}

# model_name -> set of modules that define it (via _name=)
defined_by: dict[str, set[str]] = defaultdict(set)
# module -> direct depends list
depends: dict[str, list[str]] = {}
# module -> abs path
module_path: dict[str, str] = {}
# module -> list of (model, file, line) inherits
inherits: dict[str, list[tuple[str, str, int]]] = defaultdict(list)


def parse_manifest(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        node = ast.parse(src, filename=path)
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Dict):
                return ast.literal_eval(stmt.value)
    except Exception as e:
        print(f"!! manifest parse failed {path}: {e}", file=sys.stderr)
    return None


def _str_values(value: ast.AST) -> list[str]:
    """Return string literals from a Constant, List, Tuple, or Set node."""
    out: list[str] = []
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        out.append(value.value)
    elif isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        for el in value.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                out.append(el.value)
    return out


def scan_class(cls: ast.ClassDef) -> tuple[list[str], list[tuple[str, int]]]:
    """Return (names_defined, inherits) for one ClassDef.

    A class only DEFINES a model when it sets `_name` AND does NOT also
    `_inherit` that same name (extending an existing model).
    """
    name_vals: list[str] = []
    inherit_vals: list[tuple[str, int]] = []
    for stmt in cls.body:
        if not isinstance(stmt, ast.Assign):
            continue
        targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        if "_name" in targets:
            name_vals.extend(_str_values(stmt.value))
        if "_inherit" in targets:
            for v in _str_values(stmt.value):
                inherit_vals.append((v, stmt.lineno))
    inherited_names = {v for v, _ in inherit_vals}
    names_defined = [n for n in name_vals if n not in inherited_names]
    return names_defined, inherit_vals


def scan_module(mod_dir: str, mod_name: str) -> None:
    for dirpath, dirnames, filenames in os.walk(mod_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fn)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
                tree = ast.parse(src, filename=fpath)
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    names, inh = scan_class(node)
                    for n in names:
                        defined_by[n].add(mod_name)
                    for model, line in inh:
                        inherits[mod_name].append((model, fpath, line))


def find_modules() -> None:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # don't descend into vendor
        parts = set(os.path.relpath(dirpath, ROOT).split(os.sep))
        if SKIP_DIRS & parts:
            dirnames[:] = []
            continue
        if "__manifest__.py" in filenames:
            mod_name = os.path.basename(dirpath)
            manifest = parse_manifest(os.path.join(dirpath, "__manifest__.py"))
            if manifest is None:
                continue
            module_path[mod_name] = dirpath
            depends[mod_name] = list(manifest.get("depends") or [])
            dirnames[:] = []  # don't descend further; nested modules unlikely
            scan_module(dirpath, mod_name)


def transitive_deps(mod: str) -> set[str]:
    seen: set[str] = set()
    stack = list(depends.get(mod, []))
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        stack.extend(depends.get(d, []))
    return seen


def main() -> int:
    find_modules()
    print(
        f"Scanned {len(module_path)} custom modules; "
        f"{sum(len(v) for v in inherits.values())} _inherit references; "
        f"{len(defined_by)} unique models defined.\n"
    )

    problems: list[tuple[str, str, str, str, int]] = []
    same_module_ok = 0
    external_skipped = 0

    for mod, refs in inherits.items():
        tdeps = transitive_deps(mod) | {mod}
        for model, fpath, line in refs:
            definers = defined_by.get(model, set())
            if not definers:
                external_skipped += 1
                continue
            # If model is defined inside this very module (extension+_name same), fine.
            if mod in definers:
                same_module_ok += 1
                continue
            if definers & tdeps:
                continue  # reachable through depends graph
            # Pick most likely target (first sorted) for the report
            target = sorted(definers)[0]
            problems.append((mod, model, target, fpath, line))

    if not problems:
        print(
            "OK — no missing depends detected. "
            f"({same_module_ok} same-module inherits, "
            f"{external_skipped} external/stock inherits skipped.)"
        )
        return 0

    print(f"FOUND {len(problems)} missing-dependency issue(s):\n")
    by_mod: dict[str, list] = defaultdict(list)
    for mod, model, target, fpath, line in problems:
        by_mod[mod].append((model, target, fpath, line))
    for mod in sorted(by_mod):
        print(f"# {mod}  (manifest depends={depends[mod]})")
        for model, target, fpath, line in by_mod[mod]:
            rel = os.path.relpath(fpath, "e:/Projects/Odoo/platform").replace("\\", "/")
            print(f"  - inherits '{model}' (defined in '{target}')  -- {rel}:{line}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
