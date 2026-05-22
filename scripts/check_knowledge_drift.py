#!/usr/bin/env python3
"""Drift check for MODULE_KNOWLEDGE.md.

Two modes:

1. **Staged (default)** — used as a git pre-commit hook. Scans
   ``git diff --cached --name-only`` and warns if a module's source files
   (manifest, models/, controllers/, wizards/) are staged but the module's
   ``MODULE_KNOWLEDGE.md`` is NOT also staged. Always exits 0 (warn-only).

2. **Diff range** — used in CI. Pass ``--diff <range>`` to compare a git
   range (e.g. ``origin/main...HEAD``). Exits 1 if drift is detected; exits 0
   if no drift OR if commit message contains ``[knowledge-deferred]``.

Either mode reports a clean list so devs can act:
* run ``python scripts/generate_module_knowledge.py --module X --force``
* OR edit MODULE_KNOWLEDGE.md by hand
* OR acknowledge with ``[knowledge-deferred]`` token in commit/PR.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_SOURCE_SUBDIRS = ("models/", "controllers/", "wizards/", "wizard/")
_MANIFEST = "__manifest__.py"
_KNOWLEDGE = "MODULE_KNOWLEDGE.md"
_DEFER_TOKEN = "[knowledge-deferred]"

# Recognise a module dir: any addons/<category>/custom_*/...
_MOD_RE = re.compile(r"^addons/([^/]+)/(custom_[^/]+)/(.*)$")


def _git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git"] + args, text=True).strip()
    except subprocess.CalledProcessError as e:
        print(f"git {' '.join(args)} failed: {e}", file=sys.stderr)
        return ""


def _changed_files(mode: str, diff_range: str | None) -> list[str]:
    if mode == "staged":
        out = _git(["diff", "--cached", "--name-only"])
    else:
        out = _git(["diff", "--name-only", diff_range or "HEAD"])
    return [l.strip() for l in out.splitlines() if l.strip()]


def _is_source(rel_in_mod: str) -> bool:
    if rel_in_mod == _MANIFEST:
        return True
    return any(rel_in_mod.startswith(sub) for sub in _SOURCE_SUBDIRS)


def detect_drift(changed: list[str]) -> dict[str, dict]:
    """Return {module_name: {source_touched: bool, knowledge_touched: bool, path: str}}."""
    per_module: dict[str, dict] = {}
    for f in changed:
        f = f.replace("\\", "/")
        m = _MOD_RE.match(f)
        if not m:
            continue
        category, module, rest = m.group(1), m.group(2), m.group(3)
        entry = per_module.setdefault(module, {
            "source_touched": False,
            "knowledge_touched": False,
            "path": f"addons/{category}/{module}",
        })
        if rest == _KNOWLEDGE:
            entry["knowledge_touched"] = True
        elif _is_source(rest):
            entry["source_touched"] = True
    return per_module


def commit_message_for_range(diff_range: str | None) -> str:
    if not diff_range:
        return _git(["log", "-1", "--pretty=%B"])
    # range of commits — concat all messages
    return _git(["log", "--pretty=%B", diff_range])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diff", help="Compare a git range (CI mode). Defaults to staged (pre-commit).")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on drift even in staged mode.")
    args = ap.parse_args()

    mode = "diff" if args.diff else "staged"
    changed = _changed_files(mode, args.diff)
    if not changed:
        return 0
    per_module = detect_drift(changed)
    drifted = {m: e for m, e in per_module.items()
               if e["source_touched"] and not e["knowledge_touched"]}
    if not drifted:
        return 0

    # Check for defer token in commit message(s).
    msg = commit_message_for_range(args.diff)
    deferred = _DEFER_TOKEN in (msg or "")

    header = "⚠ Knowledge drift detected" + (" (deferred)" if deferred else "")
    print(header, file=sys.stderr)
    for module, entry in sorted(drifted.items()):
        print(f"  {module}  (source changed, {entry['path']}/{_KNOWLEDGE} NOT staged)", file=sys.stderr)
    print("", file=sys.stderr)
    print("Either:", file=sys.stderr)
    print("  1. Edit MODULE_KNOWLEDGE.md to reflect the change, then re-stage it.", file=sys.stderr)
    print("  2. Run: python scripts/generate_module_knowledge.py --module <name> --force", file=sys.stderr)
    print(f"  3. Acknowledge by adding {_DEFER_TOKEN} to the commit message.", file=sys.stderr)

    if deferred:
        return 0
    if args.diff or args.strict:
        return 1
    # Pre-commit default: warn-only
    return 0


if __name__ == "__main__":
    sys.exit(main())
