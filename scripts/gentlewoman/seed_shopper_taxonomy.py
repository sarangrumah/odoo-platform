# -*- coding: utf-8 -*-
"""Seed a fashion taxonomy for the AI personal shopper (per-tenant, idempotent).

WHY a script (not module data): per the platform convention, tenant catalog data
is seeded by scripts, never by module `data/` files — otherwise it would be
re-created on every module upgrade. See docs/gentlewoman/04-TSD.md.

WHAT it does (safe to re-run):
  1. Creates namespaced ``product.tag`` records: ``color:*``, ``style:*``,
     ``occasion:*``, ``material:*`` — the vocabulary the shopper maps intents onto
     (see ai-gateway/app/shopper/intent.py).
  2. Auto-tags each published product by scanning its name + descriptions for the
     keyword synonyms below (Bahasa Indonesia + English).
  3. Fills ``custom_material_composition`` when empty and a material was detected.
  4. Ensures a ``Color`` ``product.attribute`` + values exist (variant assignment
     stays manual — we never mutate variants blindly).

RUN (host):
  docker compose exec -T odoo odoo shell -d gentlewoman --no-http \
      < scripts/gentlewoman/seed_shopper_taxonomy.py

Review the printed product list afterwards and refine tags in the Odoo backoffice
(Sales ▸ Products ▸ Product Tags) where the heuristic missed nuance.
"""

import re

# ``env`` is provided by `odoo shell`. Guard so the file can also be imported
# without crashing static analysers.
try:
    env  # type: ignore[name-defined]  # noqa: B018
except NameError:  # pragma: no cover - only when run outside odoo shell
    raise SystemExit("Run this inside `odoo shell` (env is undefined).")


# concept -> {tag value: [keyword synonyms found in name/description]}
TAXONOMY = {
    "color": {
        "hitam": ["hitam", "black"],
        "putih": ["putih", "white"],
        "navy": ["navy", "dongker", "biru tua"],
        "biru": ["biru", "blue"],
        "merah": ["merah", "red"],
        "pink": ["pink", "merah muda"],
        "krem": ["krem", "cream", "beige", "bone"],
        "cokelat": ["cokelat", "coklat", "brown", "tan"],
        "hijau": ["hijau", "green", "sage", "olive"],
        "abu": ["abu", "grey", "gray", "abu-abu"],
        "pastel": ["pastel"],
    },
    "style": {
        "formal": ["formal", "elegan", "elegant", "tailored"],
        "kasual": ["kasual", "casual", "santai", "everyday"],
        "minimalis": ["minimalis", "minimal", "basic", "essential", "considered"],
        "boho": ["boho", "bohemian"],
        "feminin": ["feminin", "feminine", "flowy"],
        "klasik": ["klasik", "classic", "timeless"],
    },
    "occasion": {
        "kerja": ["kerja", "kantor", "office", "work", "workwear"],
        "kondangan": ["kondangan", "wedding", "pesta", "party", "event"],
        "kasual": ["sehari-hari", "daily", "weekend", "errand"],
        "formal": ["formal", "gala", "dinner"],
        "liburan": ["liburan", "holiday", "vacation", "resort", "beach"],
    },
    "material": {
        "katun": ["katun", "cotton"],
        "linen": ["linen"],
        "sutra": ["sutra", "silk", "satin"],
        "rajut": ["rajut", "knit", "knitted"],
        "denim": ["denim", "jeans"],
        "wol": ["wol", "wool"],
        "rayon": ["rayon", "viscose"],
        "poliester": ["poliester", "polyester"],
    },
}

# Default per-language material composition text used to fill an empty
# custom_material_composition when a material is detected.
MATERIAL_TEXT = {
    "katun": {"id": "100% Katun", "en": "100% Cotton"},
    "linen": {"id": "100% Linen", "en": "100% Linen"},
    "sutra": {"id": "100% Sutra", "en": "100% Silk"},
    "rajut": {"id": "Bahan rajut", "en": "Knitted fabric"},
    "denim": {"id": "100% Katun denim", "en": "100% Cotton denim"},
    "wol": {"id": "Campuran wol", "en": "Wool blend"},
    "rayon": {"id": "100% Rayon", "en": "100% Rayon"},
    "poliester": {"id": "100% Poliester", "en": "100% Polyester"},
}

COLOR_ATTRIBUTE_VALUES = list(TAXONOMY["color"].keys())

Tag = env["product.tag"].sudo()
Product = env["product.template"].sudo()
Attribute = env["product.attribute"].sudo()
AttrValue = env["product.attribute.value"].sudo()


def get_or_create_tag(name):
    tag = Tag.search([("name", "=", name)], limit=1)
    if not tag:
        tag = Tag.create({"name": name})
        print(f"  + tag {name!r} (id={tag.id})")
    return tag


def main():
    # 1. taxonomy tags ------------------------------------------------------------
    print("== Ensuring taxonomy tags ==")
    tag_index = {}  # (concept, value) -> tag record
    for concept, values in TAXONOMY.items():
        for value in values:
            tag_index[(concept, value)] = get_or_create_tag(f"{concept}:{value}")

    # 2. Color attribute + values -------------------------------------------------
    print("== Ensuring Color attribute ==")
    color_attr = Attribute.search([("name", "=", "Color")], limit=1)
    if not color_attr:
        color_attr = Attribute.create({"name": "Color", "display_type": "color"})
        print(f"  + attribute Color (id={color_attr.id})")
    for value in COLOR_ATTRIBUTE_VALUES:
        if not AttrValue.search([("name", "=", value), ("attribute_id", "=", color_attr.id)], limit=1):
            AttrValue.create({"name": value, "attribute_id": color_attr.id})
            print(f"  + Color value {value!r}")

    # 3. auto-tag published products ---------------------------------------------
    print("== Auto-tagging products ==")
    products = Product.search([("sale_ok", "=", True), ("is_published", "=", True)])
    if not products:
        print("  (no published products found — publish products first)")

    def matches(synonym, haystack):
        # Whole-word match so short tokens like "red"/"tan"/"blue" don't fire
        # inside unrelated words ("covered", "important", …).
        return re.search(r"\b" + re.escape(synonym) + r"\b", haystack) is not None

    for p in products:
        haystack = " ".join(filter(None, [p.name or "", p.description_sale or "", p.website_description or ""])).lower()
        matched_tags = env["product.tag"]
        detected_material = None
        for concept, values in TAXONOMY.items():
            for value, synonyms in values.items():
                if any(matches(s, haystack) for s in synonyms):
                    matched_tags |= tag_index[(concept, value)]
                    if concept == "material" and detected_material is None:
                        detected_material = value
        # Idempotent: drop previously-applied namespaced tags, keep any manual
        # (non-namespaced) tags like "Bestseller", then apply the fresh match set.
        kept = p.product_tag_ids.filtered(lambda t: ":" not in (t.name or ""))
        p.product_tag_ids = [(6, 0, (kept | matched_tags).ids)]
        # fill material composition only when empty
        if detected_material and not (p.custom_material_composition or "").strip():
            txt = MATERIAL_TEXT.get(detected_material)
            if txt:
                p.with_context(lang="id_ID").custom_material_composition = txt["id"]
                p.with_context(lang="en_US").custom_material_composition = txt["en"]
        names = ", ".join(matched_tags.mapped("name")) or "(none matched — tag manually)"
        print(f"  [{p.id}] {p.name} -> {names}")

    env.cr.commit()
    print("== Done. Committed. Review tags in the backoffice where needed. ==")


main()
