#!/usr/bin/env python3
"""Generate bespoke icons for custom_* modules with no upstream Odoo
equivalent, using an OpenAI image model.

Usage:
    OPENAI_API_KEY=sk-...  python tools/generate_module_icons.py
    OPENAI_API_KEY=sk-...  python tools/generate_module_icons.py --only custom_coretax
    OPENAI_API_KEY=sk-...  python tools/generate_module_icons.py --model dall-e-3

Output: writes a 1024x1024 PNG to
``addons/<group>/<module>/static/description/icon.png``. The image is
post-processed to a 256x256 RGBA PNG so it matches the Odoo app icon
convention without bloating module size.

The script is **idempotent on disk** — it overwrites existing icons,
so re-run after editing the prompt if you want a different result.

Cost: gpt-image-1 standard ≈ $0.04/image; 28 icons ≈ $1.10 total.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Please install pillow: pip install pillow")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Please install openai: pip install openai")


REPO_ROOT = Path(__file__).resolve().parent.parent
ADDONS = REPO_ROOT / "addons"

# Visual style guideline appended to every prompt for consistency.
STYLE = (
    "Flat vector app icon, Odoo style. Centered subject on a soft "
    "rounded-square background. Minimal palette (2-3 colors), subtle "
    "gradient shading, no text, no letters, no people. Modern, clean, "
    "professional. Square 1:1, ample padding around the subject, "
    "single focal element. Suitable as a small launcher icon."
)

# (module_folder_name, short_concept_prompt). Background color is
# suggested per group to give the launcher visual rhythm.
PROMPTS: list[tuple[str, str]] = [
    # --- core / platform plumbing -------------------------------------
    ("custom_core", "Stylized hexagonal platform foundation icon with "
                    "subtle layered base. Purple accent background "
                    "(#714B67). Conveys 'core foundation'."),
    ("custom_adapter_framework", "Two interlocking puzzle pieces forming "
                                 "one shape, connected with a plug. Teal "
                                 "background. Conveys 'integration adapter'."),
    ("custom_ai_bridge", "A stylized brain silhouette connected to a "
                         "bridge arch with glowing dots. Indigo "
                         "background. Conveys 'AI gateway bridge'."),
    ("custom_ai_features", "A magic wand with three sparkle stars. "
                           "Gradient violet background. Conveys 'AI "
                           "powered features'."),
    ("custom_bast", "A formal handover document with a glossy "
                    "signature ribbon and check seal. Maroon background. "
                    "Represents 'official handover record'."),
    ("custom_hht_bridge", "A modern handheld barcode scanner gun with a "
                          "small wifi signal arc. Slate gray background. "
                          "Conveys 'handheld terminal integration'."),
    ("custom_home_console", "A house silhouette with a spotlight beam "
                            "and a small sparkle. Warm coral background. "
                            "Conveys 'home launcher'."),

    # --- hub / orchestration ------------------------------------------
    ("custom_hub_console", "A central node with radial spokes and small "
                           "satellite circles. Deep blue background. "
                           "Conveys 'control hub'."),
    ("custom_super_admin", "A minimal shield with a small crown emblem "
                           "on top. Royal purple background. Conveys "
                           "'super administrator'."),
    ("custom_tenant_infra", "Three small skyscraper buildings of "
                            "different heights with a cloud above. Sky "
                            "blue background. Conveys 'multi-tenant "
                            "infrastructure'."),
    ("custom_onboarding_journey", "A winding path with a flag at the "
                                  "end and three checkpoint dots. Fresh "
                                  "green background. Conveys 'onboarding "
                                  "journey'."),

    # --- ops / dev ----------------------------------------------------
    ("custom_ops_monitor", "A heart-rate ECG line on a dashboard "
                           "rectangle with one peak. Crimson background. "
                           "Conveys 'operations monitoring'."),
    ("custom_dev_cycle", "Two curved arrows forming an infinite loop "
                         "with a small code bracket inside. Dark indigo "
                         "background. Conveys 'continuous development "
                         "cycle'."),
    ("custom_brd_analyzer", "A document page with a large magnifying "
                            "glass overlapping it. Mustard yellow "
                            "background. Conveys 'document analysis'."),

    # --- compliance / Indonesian tax & privacy ------------------------
    ("custom_coretax", "An official Indonesian tax form shape with a "
                       "red seal stamp in the corner. Crimson background. "
                       "Conveys 'tax core authority'."),
    ("custom_coretax_bupot", "A small receipt slip with a checkmark "
                             "stamp. Burgundy background. Conveys 'tax "
                             "withholding receipt slip'."),
    ("custom_coretax_pajakku", "A gear connected to a small tax form "
                               "with a connection arrow. Crimson "
                               "background. Conveys 'tax service "
                               "integration'."),
    ("custom_pph_witholding", "A coin stack with an arrow being clipped "
                              "by scissors above. Amber background. "
                              "Conveys 'income withholding tax'."),
    ("custom_pdp_core", "A solid shield with a subtle padlock keyhole. "
                        "Forest green background. Conveys 'data "
                        "protection core'."),
    ("custom_pdp_consent", "Two hands meeting in a handshake with a "
                           "small lock above. Teal background. Conveys "
                           "'consent management'."),
    ("custom_pdp_audit", "A shield with a magnifier overlaid and a "
                        "small checkmark. Olive background. Conveys "
                        "'privacy audit'."),
    ("custom_pdp_dsar", "A small key with a person silhouette outline. "
                        "Slate background. Conveys 'data subject access "
                        "request'."),
    ("custom_pdp_masking", "An eye outline with a diagonal slash and "
                           "small asterisk dots. Charcoal background. "
                           "Conveys 'data masking'."),
    ("custom_pdp_retention", "An hourglass with a small archive box "
                             "below. Bronze background. Conveys 'data "
                             "retention schedule'."),

    # --- ee_gap niche --------------------------------------------------
    ("custom_esg", "A leaf wrapped around a small globe outline. "
                   "Emerald green background. Conveys 'ESG "
                   "sustainability'."),
    ("custom_wms_cycle_count", "A storage box with two curved refresh "
                               "arrows around it. Steel blue background. "
                               "Conveys 'inventory cycle count'."),
    ("custom_wms_putaway", "A storage box with a downward arrow into "
                           "a shelf slot. Navy background. Conveys "
                           "'warehouse putaway'."),
    ("custom_wms_to_engine", "A warehouse outline with an embedded gear. "
                             "Charcoal background. Conveys 'warehouse "
                             "engine'."),
]


def find_module_dir(name: str) -> Path | None:
    for parent in ADDONS.iterdir():
        if not parent.is_dir():
            continue
        candidate = parent / name
        if candidate.is_dir():
            return candidate
    return None


def render_icon(client: OpenAI, model: str, prompt: str) -> bytes:
    """Call the OpenAI image API and return raw PNG bytes."""
    full_prompt = f"{prompt}\n\n{STYLE}"
    if model.startswith("gpt-image"):
        result = client.images.generate(
            model=model,
            prompt=full_prompt,
            size="1024x1024",
            n=1,
        )
        return base64.b64decode(result.data[0].b64_json)
    # dall-e-3 returns a URL by default unless response_format=b64_json
    result = client.images.generate(
        model=model,
        prompt=full_prompt,
        size="1024x1024",
        n=1,
        response_format="b64_json",
    )
    return base64.b64decode(result.data[0].b64_json)


def downscale(raw: bytes, size: int = 256) -> bytes:
    """Resize to a manageable launcher size, force RGBA."""
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[],
                        help="Restrict to one or more module names")
    parser.add_argument("--model", default="gpt-image-1",
                        choices=["gpt-image-1", "dall-e-3"])
    parser.add_argument("--size", type=int, default=256,
                        help="Output icon side length (default 256)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts; do not call the API")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not args.dry_run and not api_key:
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr)
        return 2

    targets = PROMPTS
    if args.only:
        wanted = set(args.only)
        targets = [p for p in PROMPTS if p[0] in wanted]
        if not targets:
            print(f"No matches for {args.only}; valid names:")
            for name, _ in PROMPTS:
                print(f"  {name}")
            return 2

    if args.dry_run:
        for name, prompt in targets:
            print(f"\n=== {name} ===\n{prompt}")
        return 0

    client = OpenAI(api_key=api_key)
    ok, fail = 0, 0
    for name, prompt in targets:
        dest_dir = find_module_dir(name)
        if not dest_dir:
            print(f"  miss   {name} (folder not found)")
            fail += 1
            continue
        out_dir = dest_dir / "static" / "description"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "icon.png"
        try:
            raw = render_icon(client, args.model, prompt)
            small = downscale(raw, args.size)
            out_path.write_bytes(small)
            print(f"  ok     {name} ({len(small)}B) -> {out_path.relative_to(REPO_ROOT)}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 — surface API failures
            print(f"  FAIL   {name}: {exc}")
            fail += 1
    print(f"\nDone. ok={ok}  fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
