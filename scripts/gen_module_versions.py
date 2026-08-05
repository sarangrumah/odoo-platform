#!/usr/bin/env python3
"""
gen_module_versions.py — build the data behind eal-hub.erajaya.com/signin/versi.

Walks every custom addon's ``__manifest__.py`` for its version, and ``git log``
for the commits that touched it, and writes the result to
``login-gateway/config/versions.json``.

Why a generated file and not a live query:
  - ``config/`` is bind-mounted read-only into the login-gateway container
    (see docker-compose.yml), so refreshing the page's data is
    ``python3 scripts/gen_module_versions.py && docker compose restart
    login-gateway`` — no image rebuild. Exactly how ``tenants.json`` works.
  - The gateway sits in front of the login, so it has no Odoo session and no
    business opening a database connection to ask ``ir.module.module``.

Manifest parsing is ``ast``-only (lifted from tools/module_diff.py): no Odoo
runtime, safe to run offline and in CI.

Usage:
    python3 scripts/gen_module_versions.py            # write the file
    python3 scripts/gen_module_versions.py --check    # exit 1 if it is stale
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDONS = ROOT / "addons"
OUT = ROOT / "login-gateway" / "config" / "versions.json"

# Order is presentation order on the page, and mirrors the addons_path order in
# odoo/odoo.conf.tmpl minus _vendor (third-party code, not ours to version).
BUCKETS: list[tuple[str, str, str]] = [
    ("core", "Core", "Fondasi platform — dipakai seluruh vertical."),
    ("control_plane", "Control Plane", "Orkestrasi tenant, provisioning, dan operasi platform."),
    ("compliance", "Kepatuhan", "Perpajakan DJP/Coretax dan perlindungan data pribadi (UU PDP)."),
    ("ee_gap", "Enterprise Gap", "Fitur yang di Odoo hanya ada di Enterprise, dibangun ulang untuk Community."),
    ("operations", "Operations", "Perkakas internal tim delivery."),
    ("verticals", "Vertical", "Modul khusus lini bisnis."),
    ("_tenants", "Tenant", "Kustomisasi milik satu klien."),
]

# _vendor is OCA/third-party and carries upstream version numbers that would be
# misleading next to ours. The _template is a scaffold, not a deployed module.
SKIP_BUCKETS = {"_vendor"}
SKIP_DIR_PARTS = {".claude", "node_modules", "__pycache__", "_template"}

# Buckets whose module names carry a client's identity. tenants.json goes to
# some trouble to keep client names off the public page; listing
# `custom_levis_localization` there would undo it. Flipping these to True (or
# emptying the set) publishes everything.
PRIVATE_BUCKETS = {"_tenants"}

CHANGES_PER_MODULE = 8


def parse_manifest(path: Path) -> dict | None:
    """First dict literal in the file. Same approach as tools/module_diff.py."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            try:
                return ast.literal_eval(node)
            except (ValueError, SyntaxError):
                continue
    return None


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return ""


def changes_for(module_dir: Path) -> list[dict]:
    """The last N commits that touched this module's directory.

    No --follow: it only accepts a single path and refuses a directory, and a
    module that was renamed is a different module for our purposes anyway.
    """
    rel = module_dir.relative_to(ROOT).as_posix()
    raw = git(
        "log",
        f"-n{CHANGES_PER_MODULE}",
        "--no-merges",
        "--date=short",
        "--format=%h\x1f%ad\x1f%s",
        "--",
        rel,
    )
    out = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        out.append({"sha": sha, "date": date, "subject": subject})
    return out


def total_commits(module_dir: Path) -> int:
    """How many commits have ever touched the module — the number the public
    view shows in place of the subjects it is not allowed to print."""
    rel = module_dir.relative_to(ROOT).as_posix()
    raw = git("rev-list", "--count", "--no-merges", "HEAD", "--", rel)
    try:
        return int(raw)
    except ValueError:
        return 0


def collect_modules() -> list[dict]:
    modules: list[dict] = []
    for manifest in sorted(ADDONS.rglob("__manifest__.py")):
        rel_parts = manifest.relative_to(ROOT).parts
        if SKIP_DIR_PARTS.intersection(rel_parts):
            continue
        try:
            bucket = manifest.relative_to(ADDONS).parts[0]
        except ValueError:
            continue
        if bucket in SKIP_BUCKETS:
            continue

        data = parse_manifest(manifest)
        if not data:
            print(f"warn: unparseable manifest {manifest}", file=sys.stderr)
            continue

        module_dir = manifest.parent
        changes = changes_for(module_dir)
        modules.append(
            {
                "module": module_dir.name,
                "bucket": bucket,
                "name": str(data.get("name") or module_dir.name),
                "version": str(data.get("version") or "—"),
                "summary": str(data.get("summary") or "").strip(),
                "category": str(data.get("category") or "").strip(),
                "depends": len(data.get("depends") or []),
                "public": bucket not in PRIVATE_BUCKETS,
                # Kept alongside `changes` because the public view drops the
                # subjects (they name clients) but still wants to say when the
                # module last moved. See publicVersions() in lib/versions.ts.
                "last_change": changes[0]["date"] if changes else "",
                "change_count": total_commits(module_dir),
                "changes": changes,
            }
        )
    modules.sort(key=lambda m: (m["bucket"], m["module"]))
    return modules


def platform_facts() -> dict:
    """Versions of the stack under the addons, read from the files that pin them
    rather than restated here — a hardcoded '19.0' would drift on the next bump.
    """
    odoo_version, odoo_digest = "19.0", ""
    dockerfile = ROOT / "odoo" / "Dockerfile"
    if dockerfile.is_file():
        m = re.search(r"^FROM\s+odoo:([\w.]+)(?:@(sha256:[0-9a-f]+))?", dockerfile.read_text(), re.M)
        if m:
            odoo_version, odoo_digest = m.group(1), m.group(2) or ""

    postgres = ""
    compose = ROOT / "docker-compose.yml"
    if compose.is_file():
        # `postgres:16-alpine` -> `16`; the base image flavour is not a version.
        m = re.search(r"^\s*image:\s*postgres:([\d.]+)", compose.read_text(), re.M)
        if m:
            postgres = m.group(1)

    python = ""
    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        m = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', pyproject.read_text())
        if m:
            python = f"{m.group(1)}.{m.group(2)}"

    return {
        "odoo": {"edition": "Community", "version": odoo_version, "digest": odoo_digest},
        "postgres": postgres,
        "python": python,
        "commit": git("rev-parse", "--short", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def build() -> dict:
    modules = collect_modules()
    return {
        # Bumped only when the consumer (login-gateway/src/lib/versions.ts) needs
        # to change shape; it refuses a schema it does not know.
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "platform": platform_facts(),
        "buckets": [{"key": k, "label": lbl, "note": note} for k, lbl, note in BUCKETS],
        "modules": modules,
    }


#: The per-module fields that come from the manifest rather than from git —
#: the only ones --check can meaningfully compare.
MANIFEST_FIELDS = ("module", "bucket", "name", "version", "summary", "category", "depends", "public")


def _manifest_view(modules: list) -> list:
    return [{k: m.get(k) for k in MANIFEST_FIELDS} for m in modules]


def serialise(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the committed file is out of date",
    )
    args = ap.parse_args()

    doc = build()

    if args.check:
        if not OUT.is_file():
            print(f"{OUT.relative_to(ROOT)} is missing — run scripts/gen_module_versions.py")
            return 1
        try:
            have = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{OUT.relative_to(ROOT)} is unreadable: {exc}")
            return 1
        # Compare only what a code change controls. `generated_at`, the HEAD
        # commit, and every git-derived field (`changes`, `last_change`,
        # `change_count`) move with each new commit, so including them would
        # mean the file is stale the moment it is committed — the check would
        # be unsatisfiable rather than useful.
        stale = set()
        if have.get("schema") != doc["schema"]:
            stale.add("schema")
        if have.get("buckets") != doc["buckets"]:
            stale.add("buckets")
        if (have.get("platform") or {}).get("odoo") != doc["platform"]["odoo"]:
            stale.add("platform.odoo")
        if _manifest_view(have.get("modules") or []) != _manifest_view(doc["modules"]):
            stale.add("modules")
        if stale:
            print(
                f"{OUT.relative_to(ROOT)} is stale ({', '.join(sorted(stale))}) — "
                "run: python3 scripts/gen_module_versions.py"
            )
            return 1
        print(f"{OUT.relative_to(ROOT)} is up to date ({len(doc['modules'])} modules)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(serialise(doc), encoding="utf-8")
    hidden = sum(1 for m in doc["modules"] if not m["public"])
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(doc['modules'])} modules "
        f"({hidden} staff-only), Odoo {doc['platform']['odoo']['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
