#!/usr/bin/env python3
"""Bootstrap MODULE_KNOWLEDGE.md for every ``custom_*`` addon.

Reads each module's source (manifest, README, models/*.py, controllers/*.py)
and asks the ai-gateway to produce a structured knowledge file. Result is
written to ``<module_root>/MODULE_KNOWLEDGE.md`` with YAML frontmatter
(``status: draft``) so the developer must explicitly flip it to
``reviewed`` after vetting.

Usage:
    # All modules that don't yet have a knowledge file:
    python scripts/generate_module_knowledge.py --all

    # Just one (overwrite if exists):
    python scripts/generate_module_knowledge.py --module custom_rental --force

    # Preview prompt without calling the LLM:
    python scripts/generate_module_knowledge.py --module custom_rental --dry-run

    # Limit batch size and pace to avoid rate limits:
    python scripts/generate_module_knowledge.py --all --limit 10

The script does NOT touch the catalog; the catalog auto-rescans on next
Odoo upgrade and picks up the new files. To force-rescan immediately:
``docker exec ... odoo shell`` then ``self.env['custom.module.capability.entry']._scan_all_modules()``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
ADDONS_ROOTS = [
    ROOT / "addons" / "core",
    ROOT / "addons" / "compliance",
    ROOT / "addons" / "ee_gap",
    ROOT / "addons" / "operations",
    ROOT / "addons" / "verticals",
]

DEFAULT_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", "http://localhost:18080")
KNOWLEDGE_FILE = "MODULE_KNOWLEDGE.md"

# Per-module source budget. Stays well within Opus 4.7 input window even
# accounting for the system prompt + response tokens.
_MANIFEST_BUDGET = 4_000
_README_BUDGET = 6_000
_MODELS_BUDGET = 40_000
_CONTROLLERS_BUDGET = 12_000
_VIEWS_PEEK_BUDGET = 3_000


SYSTEM_PROMPT = """You are a senior Odoo solution architect. You write
**reference documentation** for a single custom_* module that lives inside
a multi-tenant Odoo 19 platform.

The output you produce will be read by ANOTHER large language model that
is doing BRD-gap analysis: it needs to decide whether a customer requirement
can be covered by this module without proposing a new one. Optimize for
that consumer:

- Be concrete. Use actual model technical names (e.g. ``rental.contract``)
  and field names (e.g. ``state``, ``date_start``), never humanised labels.
- Be honest about what's NOT covered. If you see only a stub, say so.
- Lead with the business capability (what problem this module solves),
  then the flow, then the technical map.
- Mention integration points: which models it inherits, which other
  custom_* modules it depends on, and which downstream modules typically
  extend it.
- Note any gotchas (multi-company quirks, transient state, hardcoded
  values, etc.) that would surprise a future implementer.

OUTPUT FORMAT: Plain markdown. Use exactly the section headings below.
DO NOT wrap in code fences. DO NOT add a preamble. Start directly with
the H1 title.

# {module_name}

## Purpose
<1-2 paragraphs on the business capability this module owns.>

## Business Flow
<Bullet list or short paragraphs describing the end-to-end user flow
through this module. Use record states and method names where helpful.>

## Key Models
<Bulleted list. For each, the technical _name then a one-line role:
- ``rental.contract`` — Top-level rental agreement; holds tenant, period, payment plan.
- ``rental.contract.line`` — Per-asset line item with daily rate and proration.>

## Important Fields
<Bullet list of the ~10 most BRD-relevant fields, grouped by model.
Mention type and what business decision they encode:
- ``rental.contract.state`` (Selection: draft/active/closed) — gates billing.
- ``rental.contract.line.unit_price`` (Monetary) — base rate before proration.>

## Public Methods
<Bullet list of the action_* / button-callable methods plus any
@api.model utilities a BRD might reference:
- ``rental.contract.action_activate()`` — flips state, books opening invoice.>

## Integration Points
<Bullet list:
- **Depends on:** custom_core, custom_pdp_audit
- **Inherits from:** account.move (adds rental_line_ids)
- **Extended by:** custom_rental_prorata, custom_drone_rental
- **External calls:** none / Pajakku /v1/coretax/...
- **Cross-vertical:** deployed in arkaim, jds, ppob>

## Gotchas
<Bulleted caveats only — leave blank line if none.>

## Out of Scope
<What this module deliberately does NOT cover, so the BRD analyzer
knows when to propose a NEW module instead of extending this one.>
"""


def list_custom_modules() -> list[Path]:
    out: list[Path] = []
    for root in ADDONS_ROOTS:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if not child.name.startswith("custom_"):
                continue
            if not (child / "__manifest__.py").is_file():
                continue
            out.append(child)
    return out


def read_clipped(path: Path, budget: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            data = fh.read(budget + 1)
    except OSError:
        return ""
    if len(data) > budget:
        return data[:budget] + "\n# ...(truncated)\n"
    return data


def harvest_module_source(module_path: Path) -> dict:
    manifest_raw = read_clipped(module_path / "__manifest__.py", _MANIFEST_BUDGET)
    manifest: dict = {}
    try:
        manifest = ast.literal_eval(manifest_raw) if manifest_raw else {}
    except Exception:  # noqa: BLE001
        manifest = {}
    readme = ""
    for fn in ("README.md", "README.rst", "README.txt"):
        p = module_path / fn
        if p.is_file():
            readme = read_clipped(p, _README_BUDGET)
            break
    models_blocks: list[str] = []
    budget = _MODELS_BUDGET
    models_dir = module_path / "models"
    if models_dir.is_dir():
        for py in sorted(models_dir.rglob("*.py")):
            if py.name == "__init__.py" or budget <= 0:
                continue
            rel = py.relative_to(module_path).as_posix()
            src = read_clipped(py, min(budget, 10_000))
            if not src:
                continue
            models_blocks.append(f"--- {rel} ---\n{src}")
            budget -= len(src)
            if budget <= 0:
                break
    controllers_blocks: list[str] = []
    budget = _CONTROLLERS_BUDGET
    ctrl_dir = module_path / "controllers"
    if ctrl_dir.is_dir():
        for py in sorted(ctrl_dir.rglob("*.py")):
            if py.name == "__init__.py" or budget <= 0:
                continue
            rel = py.relative_to(module_path).as_posix()
            src = read_clipped(py, min(budget, 6_000))
            if not src:
                continue
            controllers_blocks.append(f"--- {rel} ---\n{src}")
            budget -= len(src)
    # Views — only file list + first few hundred chars so the LLM sees
    # menus/actions without bloat.
    views_blocks: list[str] = []
    budget = _VIEWS_PEEK_BUDGET
    views_dir = module_path / "views"
    if views_dir.is_dir():
        files = sorted(p.name for p in views_dir.rglob("*.xml"))
        views_blocks.append("files: " + ", ".join(files))
        for p in sorted(views_dir.rglob("*.xml")):
            if budget <= 0:
                break
            head = read_clipped(p, min(budget, 600))
            views_blocks.append(f"--- {p.name} (head) ---\n{head}")
            budget -= len(head)
    return {
        "manifest": manifest,
        "manifest_raw": manifest_raw,
        "readme": readme,
        "models": "\n\n".join(models_blocks),
        "controllers": "\n\n".join(controllers_blocks),
        "views": "\n".join(views_blocks),
    }


def build_user_prompt(module_name: str, src: dict) -> str:
    manifest = src.get("manifest") or {}
    return (
        f"MODULE: {module_name}\n"
        f"Manifest summary: {manifest.get('summary', '')}\n"
        f"Manifest depends: {manifest.get('depends', [])}\n"
        f"Manifest version: {manifest.get('version', '')}\n\n"
        f"=== README ===\n{src.get('readme', '') or '(no README)'}\n\n"
        f"=== MODELS (truncated) ===\n{src.get('models', '') or '(no models/ folder)'}\n\n"
        f"=== CONTROLLERS (truncated) ===\n{src.get('controllers', '') or '(none)'}\n\n"
        f"=== VIEWS (file list + heads) ===\n{src.get('views', '') or '(none)'}\n\n"
        "Now write MODULE_KNOWLEDGE.md per the system instructions. "
        "Replace {module_name} in the heading template with the actual name above."
    )


_TIME_OFFSET = 0.0  # set once via _probe_server_time()


def _probe_server_time(base_url: str) -> None:
    """Pin local clock to the gateway by reading the HTTP Date header on
    an unauthenticated endpoint. Avoids host/container clock skew killing
    the HMAC replay window on Windows hosts where the system clock drifts.
    """
    global _TIME_OFFSET
    try:
        from email.utils import parsedate_to_datetime

        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=10) as r:
            server_date = r.headers.get("Date")
        if server_date:
            server_ts = parsedate_to_datetime(server_date).timestamp()
            _TIME_OFFSET = server_ts - time.time()
            if abs(_TIME_OFFSET) > 5:
                print(f"  [clock] using server time offset {_TIME_OFFSET:+.1f}s", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"  [clock] could not probe server time, falling back to local: {e}", file=sys.stderr)


def _sign(secret: str, body: bytes) -> tuple[str, str]:
    """Mirror ai-gateway's HMAC scheme: t=<ts>,v1=<sha256(secret, ts.body)>."""
    ts = str(int(time.time() + _TIME_OFFSET))
    digest = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}", ts


def call_ai_gateway(
    *, system: str, user: str, base_url: str, secret: str, quality: str = "fast", max_tokens: int = 4000
) -> str:
    body_dict = {
        "messages": [{"role": "user", "content": user}],
        "system": system,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "quality": quality if quality in ("fast", "high") else "fast",
        "cache_system": True,
    }
    raw = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")
    header, _ts = _sign(secret, raw)
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Custom-Signature": header,
            "X-Tenant-Id": "bootstrap",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    raise RuntimeError(f"Unexpected gateway response shape: {list(payload)[:5]}")


def write_knowledge(module_path: Path, body: str, manifest_version: str) -> Path:
    out = module_path / KNOWLEDGE_FILE
    frontmatter = (
        "---\n"
        "status: draft\n"
        f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        "generator: bootstrap-v1\n"
        f"module: {module_path.name}\n"
        f"manifest_version: {manifest_version}\n"
        "---\n\n"
    )
    out.write_text(frontmatter + body.strip() + "\n", encoding="utf-8")
    return out


def filter_modules(
    all_paths: list[Path], *, only: str | None, glob_pat: str | None, skip_existing: bool, force: bool
) -> Iterable[Path]:
    for p in all_paths:
        if only and p.name != only:
            continue
        if glob_pat and not Path(p.name).match(glob_pat):
            continue
        if skip_existing and (p / KNOWLEDGE_FILE).is_file() and not force:
            continue
        yield p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all", action="store_true", help="Process every custom_* module.")
    grp.add_argument("--module", help="Process a single module by name (e.g. custom_rental).")
    ap.add_argument("--glob", help="Filter modules by glob (e.g. 'custom_account*').")
    ap.add_argument("--force", action="store_true", help="Overwrite an existing MODULE_KNOWLEDGE.md.")
    ap.add_argument("--dry-run", action="store_true", help="Print the prompt, do not call LLM or write.")
    ap.add_argument("--limit", type=int, default=0, help="Cap how many modules to process this run (0 = no cap).")
    ap.add_argument("--gateway", default=DEFAULT_GATEWAY_URL, help=f"AI gateway URL (default {DEFAULT_GATEWAY_URL}).")
    ap.add_argument(
        "--secret",
        default=os.environ.get("GATEWAY_SHARED_SECRET", ""),
        help="HMAC shared secret (default: env GATEWAY_SHARED_SECRET).",
    )
    ap.add_argument(
        "--quality",
        choices=("fast", "high"),
        default="fast",
        help="Model tier: 'fast' = Sonnet 4.6 (~Rp 1-2rb/modul), 'high' = Opus 4.7 (~Rp 5-10rb/modul). Default 'fast'.",
    )
    ap.add_argument("--sleep", type=float, default=2.0, help="Seconds to sleep between calls (default 2.0).")
    args = ap.parse_args()

    if not args.dry_run and not args.secret:
        print("ERROR: --secret is required (or set GATEWAY_SHARED_SECRET in env).", file=sys.stderr)
        return 2

    paths = list_custom_modules()
    if not paths:
        print("ERROR: no custom_* modules found under", ADDONS_ROOTS, file=sys.stderr)
        return 2

    target = list(
        filter_modules(
            paths,
            only=args.module,
            glob_pat=args.glob,
            skip_existing=args.all,
            force=args.force,
        )
    )
    if args.limit:
        target = target[: args.limit]

    if not target:
        print("Nothing to do: every selected module already has MODULE_KNOWLEDGE.md (use --force to regenerate).")
        return 0

    print(f"Generating knowledge for {len(target)} module(s) via {args.gateway}")
    if not args.dry_run:
        _probe_server_time(args.gateway)
    failed: list[str] = []
    for i, mod in enumerate(target, 1):
        src = harvest_module_source(mod)
        user = build_user_prompt(mod.name, src)
        manifest_version = (src.get("manifest") or {}).get("version") or ""
        approx_tokens = (len(user) + len(SYSTEM_PROMPT)) // 4
        print(f"[{i}/{len(target)}] {mod.name} - prompt~{approx_tokens} tokens", flush=True)
        if args.dry_run:
            print("--- USER PROMPT (truncated to 2000ch) ---")
            print(user[:2000])
            print("--- END ---")
            continue
        try:
            body = call_ai_gateway(
                system=SYSTEM_PROMPT, user=user, base_url=args.gateway, secret=args.secret, quality=args.quality
            )
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="ignore")[:300]
            except Exception:  # noqa: BLE001
                pass
            print(f"  HTTPError {e.code}: {err_body}", file=sys.stderr)
            failed.append(mod.name)
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {e}", file=sys.stderr)
            failed.append(mod.name)
            continue
        if not body or not body.strip():
            print("  empty response, skipping", file=sys.stderr)
            failed.append(mod.name)
            continue
        out = write_knowledge(mod, body, manifest_version)
        print(f"  wrote {out.relative_to(ROOT).as_posix()} ({len(body)}ch)")
        if args.sleep and i < len(target):
            time.sleep(args.sleep)

    if failed:
        print(f"\n{len(failed)} failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(
        f"\nOK — {len(target)} knowledge file(s) generated. Review the diffs, "
        f"flip ``status: draft`` to ``status: reviewed`` in each, then commit."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
