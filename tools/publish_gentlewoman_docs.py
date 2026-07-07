"""Publish the GentleWoman v1.0 document package into Odoo as downloadable attachments.

Each PDF is uploaded as a PUBLIC ir.attachment in the `gentlewoman` database, so it is
downloadable via:
  - /web/content/<id>?download=true            (native Odoo)
  - /api/docs/<id>                             (storefront public proxy — PDF only)
The deck PPTX is uploaded too (public) for back-office / native download.

Upload is idempotent (keyed by attachment name). Resulting ids + links are written to
docs/gentlewoman/_release-1.0-attachments.json and printed.

Connection (XML-RPC) is configurable via env:
  ODOO_URL      (default http://localhost:18069)   — an endpoint whose dbfilter accepts `gentlewoman`
  ODOO_DB       (default gentlewoman)
  ODOO_USER     (default admin)
  ODOO_PASSWORD (default admin)
  PUBLIC_BASE   (optional, for printing links e.g. https://192.168.3.140:8443)

If XML-RPC is unreachable (e.g. Docker is down), run with --print-shell to emit a Python
snippet you can paste into `docker exec -it <odoo> odoo shell -d gentlewoman`.

Run : python tools/publish_gentlewoman_docs.py
      python tools/publish_gentlewoman_docs.py --print-shell
"""

from __future__ import annotations

import base64
import json
import os
import sys
import xmlrpc.client  # nosec B411 - client calls to our own controlled Odoo XML-RPC endpoint, not untrusted-XML parsing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "gentlewoman"

# (filename, attachment name, mimetype, public)
ARTIFACTS = [
    ("GentleWoman-Business-Presentation-v1.0.pdf", "GentleWoman - Business Presentation v1.0", "application/pdf", True),
    ("GentleWoman-TSD-v1.0.pdf", "GentleWoman - TSD v1.0", "application/pdf", True),
    ("GentleWoman-Blueprint-v1.0.pdf", "GentleWoman - Blueprint v1.0", "application/pdf", True),
    ("GentleWoman-FSD-v1.0.pdf", "GentleWoman - FSD v1.0", "application/pdf", True),
    (
        "GentleWoman-Business-Presentation-v1.0.pptx",
        "GentleWoman - Business Presentation v1.0 (PPTX)",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        True,
    ),
]

URL = os.environ.get("ODOO_URL", "http://localhost:18069")
DB = os.environ.get("ODOO_DB", "gentlewoman")
USER = os.environ.get("ODOO_USER", "admin")
PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "").rstrip("/")


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def print_shell_snippet() -> None:
    """Emit a snippet for `odoo shell -d gentlewoman` (no network needed from here)."""
    lines = [
        "# Paste into:  docker exec -it <odoo-container> odoo shell -d gentlewoman",
        "import base64, pathlib",
        "Att = env['ir.attachment'].sudo()",
        "specs = [",
    ]
    for fname, name, mime, public in ARTIFACTS:
        lines.append(f"    ({fname!r}, {name!r}, {mime!r}, {public}),")
    lines += [
        "]",
        "# adjust to where the docs/gentlewoman folder is mounted inside the container:",
        "base = pathlib.Path('/mnt/extra-addons/../docs/gentlewoman')  # EDIT THIS PATH",
        "for fname, name, mime, public in specs:",
        "    p = base / fname",
        "    data = base64.b64encode(p.read_bytes()).decode()",
        "    rec = Att.search([('name','=',name)], limit=1)",
        "    vals = dict(name=name, datas=data, mimetype=mime, type='binary', public=public)",
        "    if rec: rec.write(vals)",
        "    else:   rec = Att.create(vals)",
        "    print(rec.id, name, '/web/content/%s?download=true' % rec.id, '/api/docs/%s' % rec.id)",
        "env.cr.commit()",
    ]
    print("\n".join(lines))


def main() -> int:
    if "--print-shell" in sys.argv:
        print_shell_snippet()
        return 0

    missing = [f for f, *_ in ARTIFACTS if not (DOCS / f).exists()]
    if missing:
        print("Missing artifacts (build them first):", ", ".join(missing))
        return 2

    try:
        common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(DB, USER, PASSWORD, {})
        if not uid:
            print(f"Auth failed for db={DB} user={USER} at {URL}.")
            return 1
        models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
    except Exception as e:  # noqa: BLE001
        print(f"Cannot reach Odoo at {URL}: {e}")
        print("Docker/Odoo likely not running. Re-run when up, or use --print-shell.")
        return 1

    results = []
    for fname, name, mime, public in ARTIFACTS:
        path = DOCS / fname
        vals = {"name": name, "datas": b64(path), "mimetype": mime, "type": "binary", "public": public}
        found = models.execute_kw(DB, uid, PASSWORD, "ir.attachment", "search", [[["name", "=", name]]], {"limit": 1})
        if found:
            att_id = found[0]
            models.execute_kw(DB, uid, PASSWORD, "ir.attachment", "write", [[att_id], vals])
        else:
            att_id = models.execute_kw(DB, uid, PASSWORD, "ir.attachment", "create", [vals])
        web = f"/web/content/{att_id}?download=true"
        api = f"/api/docs/{att_id}" if mime == "application/pdf" else "(PPTX — back-office only)"
        results.append({"file": fname, "name": name, "id": att_id, "web_content": web, "api_docs": api})
        prefix = PUBLIC_BASE if PUBLIC_BASE else ""
        print(f"  #{att_id:<6} {name}")
        print(f"         {prefix}{web}")
        if mime == "application/pdf":
            print(f"         {prefix}{api}")

    out = DOCS / "_release-1.0-attachments.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
