#!/usr/bin/env python3
"""Migrate `_sql_constraints` class attribute to Odoo 19 `models.Constraint` API.

In-place rewrite of Python files. Idempotent: skips files that don't define
``_sql_constraints``.

Pattern (input):
    _sql_constraints = [
        ('cname', 'unique(x)', 'Message'),
        ...
    ]

Pattern (output):
    _cname = models.Constraint('unique(x)', 'Message')
    ...

Tuple elements are parsed via ``ast`` so multiline strings and quotes are
preserved verbatim. The original indentation of ``_sql_constraints`` is reused
for each emitted assignment.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "_sql_constraints" not in text:
        return False

    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        print(f"  SKIP (syntax error): {path} :: {e}")
        return False

    # Locate `_sql_constraints = [...]` assignments.
    replacements: list[tuple[int, int, str]] = []
    lines = text.splitlines(keepends=True)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "_sql_constraints":
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            print(f"  SKIP (non-list _sql_constraints): {path}")
            continue

        constraints = []
        for elt in node.value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) != 3:
                print(f"  SKIP (unexpected element shape): {path}")
                constraints = None
                break
            name_node, sql_node, msg_node = elt.elts
            if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
                print(f"  SKIP (non-literal name): {path}")
                constraints = None
                break
            constraints.append((name_node.value, sql_node, msg_node))
        if not constraints:
            continue

        # Indent of the assignment's first column.
        first_line_idx = node.lineno - 1
        first_line = lines[first_line_idx]
        indent = first_line[: len(first_line) - len(first_line.lstrip())]

        # Build new lines. The first line omits the indent prefix because the
        # original assignment's leading whitespace (preserved by start_offset
        # pointing at col_offset, not column 0) already supplies it. Subsequent
        # lines need full indent.
        new_lines: list[str] = []
        for i, (name, sql_node, msg_node) in enumerate(constraints):
            sql_src = ast.unparse(sql_node)
            msg_src = ast.unparse(msg_node)
            leading = "" if i == 0 else indent
            new_lines.append(
                f"{leading}_{name} = models.Constraint(\n{indent}    {sql_src},\n{indent}    {msg_src},\n{indent})\n"
            )
        new_text = "".join(new_lines)

        # Byte offsets of the original assignment.
        start_offset = sum(len(l) for l in lines[: node.lineno - 1]) + node.col_offset
        end_lineno = node.end_lineno or node.lineno
        end_col = node.end_col_offset or 0
        end_offset = sum(len(l) for l in lines[: end_lineno - 1]) + end_col

        replacements.append((start_offset, end_offset, new_text.rstrip("\n")))

    if not replacements:
        return False

    # Apply replacements right-to-left so earlier offsets stay valid.
    replacements.sort(reverse=True)
    new_text = text
    for start, end, replacement in replacements:
        new_text = new_text[:start] + replacement + new_text[end:]

    path.write_text(new_text, encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: migrate_sql_constraints.py <root_dir> [...more dirs]")
        return 2

    files_modified = 0
    files_scanned = 0
    for root_arg in argv[1:]:
        root = Path(root_arg)
        for py_file in root.rglob("*.py"):
            if "_vendor" in py_file.parts or "__pycache__" in py_file.parts:
                continue
            files_scanned += 1
            if migrate_file(py_file):
                files_modified += 1
                print(f"  migrated: {py_file}")

    print(f"\nScanned {files_scanned} .py files, modified {files_modified}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
