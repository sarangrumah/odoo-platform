"""Intent schema + concept→tag mapping for the personal shopper.

The extraction LLM call returns a small JSON object describing what the visitor
wants. We then map the free-text concepts (color/occasion/style/material) onto
the tenant's actual ``product.tag`` ids so the catalog query is grounded in
real, filterable metadata rather than guessed keywords.

Tag taxonomy convention (seeded per tenant): namespaced names like
``color:navy``, ``occasion:kondangan``, ``style:formal``, ``material:katun``.
Mapping degrades gracefully: an un-namespaced or partially-matching tag still
matches by substring, and anything unmatched falls back to the free-text ``q``.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

# Concepts we try to resolve to tag ids, in priority order. ``category`` and
# ``size`` are intentionally excluded: category folds into the free-text query
# and size only filters variants (no template-level filter on /products).
_TAG_CONCEPTS = ("color", "occasion", "style", "material")


class ShopperIntent(BaseModel):
    color: str | None = None
    category: str | None = None
    occasion: str | None = None
    style: str | None = None
    material: str | None = None
    size: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    keywords: str | None = Field(default=None, description="Free-text product keywords")
    need_clarification: bool = False
    clarify_question: str | None = None

    def has_search_signal(self) -> bool:
        """True when there's at least one usable filter to query the catalog."""
        return any(
            getattr(self, f) not in (None, "")
            for f in ("color", "category", "occasion", "style", "material", "keywords", "price_min", "price_max")
        )


def parse_intent(raw_text: str) -> ShopperIntent:
    """Defensively parse the extractor's JSON output into a ShopperIntent."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}
    try:
        return ShopperIntent.model_validate(data)
    except Exception:
        # Never hard-fail extraction; an empty intent triggers a clarify reply.
        return ShopperIntent(need_clarification=True)


def taxonomy_by_concept(tags: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group namespaced tag names into ``{concept: [value, ...]}`` for the prompt."""
    grouped: dict[str, list[str]] = {c: [] for c in _TAG_CONCEPTS}
    for t in tags:
        name = str(t.get("name", ""))
        if ":" in name:
            concept, _, value = name.partition(":")
            concept = concept.strip().lower()
            if concept in grouped:
                grouped[concept].append(value.strip())
    return {c: v for c, v in grouped.items() if v}


# Indonesian product-type words → a token found in the (English) public-category
# name. Bridges the language gap so "rok" finds "Skirts", "atasan" finds "Tops".
_CATEGORY_SYNONYMS = {
    "atasan": "tops",
    "baju": "tops",
    "kaos": "tops",
    "kemeja": "tops",
    "blus": "tops",
    "blouse": "tops",
    "shirt": "tops",
    "tee": "tops",
    "top": "tops",
    "dress": "dresses",
    "gaun": "dresses",
    "terusan": "dresses",
    "gown": "dresses",
    "rok": "skirts",
    "skirt": "skirts",
    "celana": "trousers",
    "celana panjang": "trousers",
    "pants": "trousers",
    "trouser": "trousers",
    "celana pendek": "shorts",
    "hotpants": "shorts",
    "short": "shorts",
    "jumpsuit": "jumpsuits",
    "setelan": "sets",
    "set": "sets",
    "tas": "bags",
    "tote": "tote",
    "selempang": "crossbody",
    "sepatu": "shoes",
    "aksesori": "accessories",
    "aksesoris": "accessories",
    "jaket": "outerwear",
    "luaran": "outerwear",
    "outer": "outerwear",
    "mantel": "outerwear",
    "rajut": "knitwear",
    "sweater": "knitwear",
    "cardigan": "knitwear",
    "syal": "scarves",
    "selendang": "scarves",
    "scarf": "scarves",
    "topi": "hats",
    "perhiasan": "jewelry",
    "kalung": "jewelry",
    "anting": "jewelry",
    "gelang": "jewelry",
}


def resolve_category(word: str | None, categories: list[dict[str, Any]]) -> int | None:
    """Best-effort map a category word onto a real public-category id.

    The /products endpoint uses ``child_of``, so matching a parent (e.g.
    "Dresses") still returns its children. Tries an Indonesian→English synonym
    first, then a direct case-insensitive substring match either way.
    """
    if not word:
        return None
    w = str(word).strip().lower()
    if not w:
        return None
    target = _CATEGORY_SYNONYMS.get(w, w)
    for c in categories:
        name = str(c.get("name", "")).strip().lower()
        if name and (target == name or target in name or name in target):
            return c.get("id")
    return None


def map_to_query(
    intent: ShopperIntent,
    tags: list[dict[str, Any]],
    categories: list[dict[str, Any]] | None = None,
    *,
    limit: int = 6,
) -> dict[str, Any]:
    """Translate an intent into ``OdooCatalog.search_products`` kwargs.

    Concepts resolve to real ``product.tag`` ids; ``category`` resolves to a real
    public-category id. Crucially, an UNMATCHED concept is NOT turned into a
    free-text ``q`` — a name ``ilike`` of an Indonesian concept word ("navy",
    "kondangan") rarely matches English product names and, ANDed with other
    filters, would wrongly zero out good results. The reply step still receives
    the full intent, so it can speak to preferences the catalog can't filter on.
    Only explicit ``keywords`` become ``q``. The router applies a broadening
    fallback (drop tags, then category) when a precise query is empty.
    """
    by_id = {str(t.get("name", "")).lower(): t.get("id") for t in tags}

    tag_ids: list[int] = []
    for concept in _TAG_CONCEPTS:
        value = getattr(intent, concept)
        if not value:
            continue
        value_l = str(value).strip().lower()
        tid = by_id.get(f"{concept}:{value_l}")
        if tid is None:
            for name, ident in by_id.items():
                if value_l and value_l in name:
                    tid = ident
                    break
        if tid is not None:
            tag_ids.append(int(tid))

    return {
        "q": (intent.keywords or "").strip() or None,
        "tag": ",".join(str(i) for i in dict.fromkeys(tag_ids)) or None,
        "category": resolve_category(intent.category, categories or []),
        "price_min": intent.price_min,
        "price_max": intent.price_max,
        "limit": limit,
    }
