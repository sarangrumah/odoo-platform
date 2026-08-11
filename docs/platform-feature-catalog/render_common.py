# -*- coding: utf-8 -*-
"""Assemble the catalog document from ``catalog.json`` + ``narrative/*.md``.

Both renderers (Markdown and HTML) call ``build_document()`` and then format the
same block list, so the two outputs cannot drift in content — only in
presentation.

Placeholder contract used inside the narrative files:

  ``{{n.modules_total}}``            total module count
  ``{{n.group.ee_gap}}``             modules in an addons group
  ``{{n.domain.keuangan-akuntansi}}``modules in a domain
  ``{{n.scope.tenant}}``             modules with a scope
  ``{{n.knowledge_missing}}``        any key under meta.counts
  ``{{n.tenants}}``                  registered tenants
  ``{{n.gaps}}`` / ``{{n.gaps.high}}``

Block directives, alone on a line:

  ``{{TABEL_MODUL}}``      module table for this chapter's domain
  ``{{KHUSUS_BRAND}}``     the "specific to one brand" closing subsection
  ``{{TABEL_GRUP}}``       modules per addons group
  ``{{TABEL_DOMAIN}}``     modules per domain
  ``{{TABEL_TENANT}}``     the brand/tenant register
  ``{{TABEL_KESENJANGAN}}``the gap register
  ``{{LAMPIRAN}}``         the full English per-module appendix

An unknown placeholder raises rather than rendering as literal braces: a typo
that silently ships ``{{n.doman.x}}`` into a client PDF is worse than a failed
build.
"""

from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
NARRATIVE = os.path.join(HERE, "narrative")

INLINE = re.compile(r"\{\{n\.([a-zA-Z0-9_.\-]+)\}\}")
DIRECTIVE = re.compile(r"^\{\{([A-Z_]+)\}\}\s*$")

SCOPE_LABEL = {
    "general": "Umum",
    "tenant": "Khusus brand",
    "platform": "Platform",
    "vendor": "Pihak ketiga",
}
MATURITY_LABEL = {
    "production": "Produksi",
    "beta": "Beta",
    "scaffold": "Kerangka",
    "vendor": "Vendor",
    "disabled": "Nonaktif",
}
CONFIDENCE_LABEL = {"high": "Tinggi", "medium": "Sedang", "low": "Rendah"}
SEVERITY_LABEL = {"high": "Tinggi", "medium": "Sedang", "low": "Rendah"}


def scope_label(mod) -> str:
    if mod["scope"] == "general" and mod["tenants"]:
        return "Umum, dikonfigurasi"
    return SCOPE_LABEL.get(mod["scope"], mod["scope"])


# --- inline numbers ---------------------------------------------------------


def _resolve_number(cat, key: str):
    counts = cat["meta"]["counts"]
    if key == "tenants":
        return len(cat["tenants"])
    if key == "gaps":
        return len(cat["gaps"])
    if key.startswith("gaps."):
        sev = key.split(".", 1)[1]
        return sum(1 for g in cat["gaps"] if g["severity"] == sev)
    if key.startswith("group."):
        return counts["by_group"][key.split(".", 1)[1]]
    if key.startswith("domain."):
        return counts["by_domain"].get(key.split(".", 1)[1], 0)
    if key.startswith("scope."):
        return counts["by_scope"].get(key.split(".", 1)[1], 0)
    if key.startswith("confidence."):
        return counts["by_confidence"].get(key.split(".", 1)[1], 0)
    if key == "knowledge_draft":
        return (counts["knowledge_present"] - counts["knowledge_reviewed"]
                - counts["knowledge_override"])
    if key in counts:
        return counts[key]
    raise KeyError(f"unknown placeholder {{{{n.{key}}}}}")


def substitute(text: str, cat) -> str:
    return INLINE.sub(lambda m: str(_resolve_number(cat, m.group(1))), text)


# --- generated blocks -------------------------------------------------------


def _mods_in_domain(cat, domain_id):
    return sorted(
        (m for m in cat["modules"] if m["domain"] == domain_id),
        key=lambda m: (m["scope"] != "general", m["name"]),
    )


def table_modules(cat, domain_id, brand_by_id):
    rows = []
    for m in _mods_in_domain(cat, domain_id):
        rows.append([
            m["id"]["nama"],
            f"`{m['name']}`",
            scope_label(m),
            ", ".join(brand_by_id[t] for t in m["tenants"]) or "—",
            MATURITY_LABEL.get(m["maturity"], m["maturity"]),
            m["id"]["ringkasan"],
        ])
    return {
        "kind": "table",
        "head": ["Fitur", "Modul", "Cakupan", "Brand", "Kematangan", "Ringkasan"],
        "rows": rows,
        "widths": ["17%", "22%", "10%", "12%", "9%", "30%"],
    }


def block_tenant_specific(cat, domain_id, brand_by_id):
    """The closing subsection every domain chapter carries.

    Brand-specificity is an axis orthogonal to function, so tenant modules stay
    in their functional chapter rather than being collected into a "tenant
    modules" chapter that would split Finance in two.
    """
    tenant_mods = [m for m in _mods_in_domain(cat, domain_id) if m["scope"] == "tenant"]
    configured = [m for m in _mods_in_domain(cat, domain_id)
                  if m["scope"] == "general" and m["tenants"]]
    out = [{"kind": "heading", "level": 3, "text": "Yang bersifat khusus per-brand"}]
    if not tenant_mods and not configured:
        out.append({"kind": "para", "text":
                    "Tidak ada. Seluruh modul di domain ini berlaku umum untuk "
                    "tenant mana pun, tanpa data atau konfigurasi khusus brand."})
        return out
    if tenant_mods:
        items = [f"**{m['id']['nama']}** (`{m['name']}`) — "
                 f"{', '.join(brand_by_id[t] for t in m['tenants']) or 'tanpa brand terdaftar'}. "
                 f"{m['id']['ringkasan']}" for m in tenant_mods]
        out.append({"kind": "para", "text":
                    "Modul berikut berada di `addons/_tenants/` dan **tidak dapat dipakai "
                    "ulang apa adanya** oleh tenant lain:"})
        out.append({"kind": "list", "items": items})
    if configured:
        items = [f"**{m['id']['nama']}** (`{m['name']}`) — sudah membawa data atau profil untuk "
                 f"{', '.join(brand_by_id[t] for t in m['tenants'])}." for m in configured]
        out.append({"kind": "para", "text":
                    "Modul berikut adalah mesin umum yang **sudah dikonfigurasi** untuk satu "
                    "brand atau lebih. Tenant baru dapat memakainya, tetapi perlu profil dan "
                    "data sendiri:"})
        out.append({"kind": "list", "items": items})
    return out


def table_groups(cat):
    rows = [[f"`addons/{g}/`", str(n)] for g, n in sorted(cat["meta"]["counts"]["by_group"].items())]
    rows.append(["**Total**", f"**{cat['meta']['counts']['modules_total']}**"])
    return {"kind": "table", "head": ["Grup", "Modul"], "rows": rows,
            "widths": ["70%", "30%"]}


def table_domains(cat):
    rows = [[d["title_id"], str(d["module_count"]), d["blurb_id"]] for d in cat["domains"]]
    rows.append(["**Total**", f"**{cat['meta']['counts']['modules_total']}**", ""])
    return {"kind": "table", "head": ["Domain", "Modul", "Cakupan isi"], "rows": rows,
            "widths": ["24%", "8%", "68%"]}


def table_tenants(cat):
    rows = []
    for t in cat["tenants"]:
        rows.append([
            t["brand"],
            t.get("legal", ""),
            "Erajaya Group" if t["erajaya"] else "Di luar grup",
            t.get("industry", ""),
            ", ".join(f"`{d}`" for d in t.get("dbs", [])) or "—",
            t.get("status", ""),
        ])
    return {"kind": "table",
            "head": ["Brand", "Entitas", "Afiliasi", "Industri", "Basis data", "Status"],
            "rows": rows,
            "widths": ["14%", "20%", "12%", "18%", "24%", "12%"]}


EFFORT_LABEL = {"S": "S — di bawah 1 minggu", "M": "M — 1 sampai 4 minggu",
                "L": "L — lebih dari 1 bulan"}


def block_gaps(cat):
    """One block per gap, not one wide table.

    Nine columns of prose across A4 portrait squeezes the short columns until
    "Sedang" wraps to "Seda / ng". A per-gap block reads properly on paper; the
    filterable wide table lives in the XLSX, where filtering is the point.
    """
    # Gap prose states counts too, so it gets the same placeholder treatment as
    # the narrative. Hand-typed numbers here survived a rebase that moved every
    # other figure in the document.
    def sub(g, key):
        return substitute(g.get(key, ""), cat)

    out = []
    summary = [[g["id"], g["area"], sub(g, "title_id"),
                SEVERITY_LABEL.get(g["severity"], g["severity"]),
                g.get("horizon", "")] for g in cat["gaps"]]
    out.append({"kind": "table",
                "head": ["ID", "Area", "Kesenjangan", "Prioritas", "Horizon (bulan)"],
                "rows": summary,
                "widths": ["12%", "18%", "45%", "13%", "12%"]})

    for g in cat["gaps"]:
        out.append({"kind": "heading", "level": 3,
                    "text": f"{g['id']} · {sub(g, 'title_id')}"})
        rows = [
            ["Area", g["area"]],
            ["Prioritas", SEVERITY_LABEL.get(g["severity"], g["severity"])
             + f" · upaya {EFFORT_LABEL.get(g.get('effort', ''), g.get('effort', '—'))}"
             + f" · horizon {g.get('horizon', '—')} bulan"],
            ["Kondisi saat ini (NOW)", sub(g, "now_id")],
            ["Sasaran (TARGET)", sub(g, "target_id")],
        ]
        if g.get("impact_id"):
            rows.append(["Dampak bisnis", sub(g, "impact_id")])
        if g.get("evidence"):
            rows.append(["Rujukan", " · ".join(f"`{e}`" for e in g["evidence"])])
        out.append({"kind": "table", "head": ["", ""], "rows": rows,
                    "widths": ["22%", "78%"], "headless": True})
    return out


# --- English per-module appendix -------------------------------------------


def block_appendix(cat, domain_title, brand_by_id):
    out = []
    vendor_like = []
    for d in cat["domains"]:
        mods = [m for m in cat["modules"] if m["domain"] == d["id"]]
        if not mods:
            continue
        out.append({"kind": "heading", "level": 2,
                    "text": f"{d['title_en']} ({d['title_id']})"})
        for m in sorted(mods, key=lambda x: x["name"]):
            if m["group"] == "_vendor" or m["name"] == "custom_vertical_example":
                vendor_like.append(m)
                continue
            out.extend(_appendix_entry(m, brand_by_id))
    if vendor_like:
        out.append({"kind": "heading", "level": 2,
                    "text": "Third-party components (OCA) and templates"})
        out.append({"kind": "para", "text":
                    "Vendored or reference-only. Counted in the total so the figures "
                    "reconcile, but not described in depth — they are not features "
                    "delivered to a tenant."})
        out.append({"kind": "list", "items": [
            f"`{m['name']}` {m['manifest']['version']} — {m['manifest']['summary'] or m['manifest']['name']}"
            for m in sorted(vendor_like, key=lambda x: x["name"])]})
    return out


def _appendix_entry(m, brand_by_id):
    man, k, src = m["manifest"], m["knowledge"], m["source"]
    out = [{"kind": "heading", "level": 3, "text": f"{m['name']} — {man['name']}"}]

    facts = [
        ["Path", f"`{m['relpath']}`"],
        ["Version", man["version"] or "—"],
        ["Scope", scope_label(m) + (
            f" ({', '.join(brand_by_id[t] for t in m['tenants'])})" if m["tenants"] else "")],
        ["Maturity / confidence",
         f"{MATURITY_LABEL.get(m['maturity'], m['maturity'])} / {CONFIDENCE_LABEL[m['confidence']]}"],
        ["Depends", ", ".join(f"`{d}`" for d in man["depends"]) or "—"],
        ["Models / routes / tests",
         f"{len(src['models_own'])} / {len(src['routes'])} / {src['test_files']}"],
    ]
    if man["capability_tags"]:
        facts.append(["Tags", ", ".join(man["capability_tags"])])
    out.append({"kind": "table", "head": ["", ""], "rows": facts,
                "widths": ["24%", "76%"], "compact": True, "headless": True})

    if not k["present"]:
        out.append({"kind": "note", "text":
                    "No module knowledge file exists. The summary below is derived from the "
                    "manifest; treat it as an index entry, not a specification."})
    elif k["status"] == "draft":
        out.append({"kind": "note", "text":
                    "Knowledge file is generator output, not human-reviewed."
                    + (f" Written against version {k['manifest_version_at_gen']}, "
                       f"module is now {man['version']}." if k["version_drift"] else "")})

    if k["purpose"]:
        out.append({"kind": "para", "text": k["purpose"]})
    if k["business_flow"]:
        out.append({"kind": "para", "text": "**How it works**"})
        out.append({"kind": "list", "items": k["business_flow"]})
    if k["key_models"]:
        out.append({"kind": "para", "text": "**Key models**"})
        out.append({"kind": "list", "items": [km["desc"] for km in k["key_models"]]})
    elif src["models_own"]:
        out.append({"kind": "para", "text": "**Declared models**: "
                    + ", ".join(f"`{x}`" for x in src["models_own"])})
    if k["important_fields"]:
        out.append({"kind": "para", "text": "**Important fields**"})
        out.append({"kind": "list", "items": [f["desc"] for f in k["important_fields"]]})
    if src["routes"]:
        out.append({"kind": "para", "text": "**Endpoints**: "
                    + ", ".join(f"`{r}`" for r in src["routes"])})
    return out


# --- narrative assembly -----------------------------------------------------


def _parse_front(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    meta = {}
    for line in raw[3:end].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    rest = raw.find("\n", end + 4)
    return meta, raw[rest + 1:] if rest != -1 else ""


def _markdown_to_blocks(text: str) -> list[dict]:
    """Convert the hand-written prose into the block list.

    Only the subset the chapters actually use: ATX headings, paragraphs,
    ``- `` lists, ``> `` notes and pipe tables. Keeping the converter this small
    is deliberate — the renderers stay honest about what they can lay out on A4.
    """
    blocks: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            blocks.append({"kind": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue
        img = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", line)
        if img:
            blocks.append({"kind": "figure", "alt": img.group(1), "src": img.group(2)})
            i += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_pipe_table(table_lines))
            continue
        if line.lstrip().startswith("> "):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            blocks.append({"kind": "note", "text": " ".join(x for x in buf if x)})
            continue
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
            items: list[str] = []
            while i < len(lines) and (re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[i])
                                      or (items and lines[i].startswith((" ", "\t")) and lines[i].strip())):
                if re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[i]):
                    items.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", lines[i]).strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            blocks.append({"kind": "list", "items": items})
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", ">")) \
                and not re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        blocks.append({"kind": "para", "text": " ".join(buf)})
    return blocks


def _pipe_table(rows: list[str]) -> dict:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head = cells[0]
    body = [r for r in cells[1:] if not all(set(c) <= set("-: ") for c in r)]
    return {"kind": "table", "head": head, "rows": body, "widths": None}


def build_document(cat) -> list[dict]:
    """Ordered block list for the whole document."""
    domain_title = {d["id"]: d["title_id"] for d in cat["domains"]}
    brand_by_id = {t["id"]: t["brand"] for t in cat["tenants"]}

    blocks: list[dict] = []
    for fname in sorted(os.listdir(NARRATIVE)):
        if not fname.endswith(".md"):
            continue
        with open(os.path.join(NARRATIVE, fname), "r", encoding="utf-8") as fh:
            meta, body = _parse_front(fh.read())
        body = substitute(body, cat)
        domain_id = meta.get("domain") or ""
        if domain_id and domain_id not in domain_title:
            raise KeyError(f"{fname}: unknown domain '{domain_id}'")

        for raw_block in re.split(r"(?m)^(\{\{[A-Z_]+\}\})\s*$", body):
            if not raw_block.strip():
                continue
            directive = DIRECTIVE.match(raw_block.strip())
            if not directive:
                blocks.extend(_markdown_to_blocks(raw_block))
                continue
            name = directive.group(1)
            if name == "TABEL_MODUL":
                if not domain_id:
                    raise KeyError(f"{fname}: {{{{TABEL_MODUL}}}} needs a `domain:` front-matter key")
                blocks.append(table_modules(cat, domain_id, brand_by_id))
            elif name == "KHUSUS_BRAND":
                blocks.extend(block_tenant_specific(cat, domain_id, brand_by_id))
            elif name == "TABEL_GRUP":
                blocks.append(table_groups(cat))
            elif name == "TABEL_DOMAIN":
                blocks.append(table_domains(cat))
            elif name == "TABEL_TENANT":
                blocks.append(table_tenants(cat))
            elif name == "TABEL_KESENJANGAN":
                blocks.extend(block_gaps(cat))
            elif name == "LAMPIRAN":
                blocks.extend(block_appendix(cat, domain_title, brand_by_id))
            else:
                raise KeyError(f"{fname}: unknown directive {{{{{name}}}}}")
    return blocks
