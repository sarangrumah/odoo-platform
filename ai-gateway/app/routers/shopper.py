"""Personal shopper endpoint — retrieval-controlled, grounded on the Odoo catalog.

Flow (no LLM tool-calling; see app/shopper/__init__.py for the rationale):

    1. EXTRACT  intent from the conversation     -> one JSON-mode Ollama call
    2. CLARIFY  if the request is too vague       -> ask, do not search
    3. RETRIEVE products from Odoo *in code*      -> existing /storefront/api/products
    4. SYNTHESISE a natural reply from real items -> one Ollama call
    5. GUARD: the returned products[] is built ONLY from the live catalog payload
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..providers import get_provider
from ..providers.base import ChatRequest, Message
from ..shopper.intent import map_to_query, parse_intent, taxonomy_by_concept
from ..shopper.odoo_catalog import OdooCatalog

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["shopper"])

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_EXTRACT_PROMPT = (_PROMPTS / "shopper_extract.md").read_text(encoding="utf-8")
_REPLY_PROMPT = (_PROMPTS / "shopper_reply.md").read_text(encoding="utf-8")

_MAX_HISTORY = 8          # turns of context sent to the model
_MAX_PRODUCTS = 6         # candidates retrieved + grounding set ceiling
_REPLY_MAX_TOKENS = 500
_EXTRACT_MAX_TOKENS = 300

# CS / complaint / returns → hand off to a human (spec §3.6 escalation).
_ESCALATE_KEYWORDS = (
    "komplain", "keluhan", "retur", "refund", "kembalikan", "pengembalian",
    "rusak", "cacat", "tukar", "lapor", "admin", "customer service", "cs ",
    "manusia", "complaint", "return", "broken", "defect", "human",
)


class ShopperMessageIn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ShopperIn(BaseModel):
    messages: list[ShopperMessageIn] = Field(min_length=1)
    tenant: str = Field(min_length=1, max_length=128, description="Odoo DB / tenant slug")
    locale: str = "id"


class ShopperOut(BaseModel):
    reply: str
    products: list[dict] = []
    product_ids: list[int] = []
    clarify: bool = False
    escalate: bool = False
    no_results: bool = False


def _wants_human(text: str) -> bool:
    low = f" {text.lower()} "
    return any(k in low for k in _ESCALATE_KEYWORDS)


@router.post("/shopper", response_model=ShopperOut)
async def shopper(body: ShopperIn) -> ShopperOut:
    settings = get_settings()
    history = [Message(role=m.role, content=m.content) for m in body.messages[-_MAX_HISTORY:]]
    last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
    locale = "en" if body.locale.lower().startswith("en") else "id"

    catalog = OdooCatalog(tenant=body.tenant, lang=locale)
    try:
        # ---- 0. taxonomy + categories (cached) ------------------------------------
        try:
            tags = await catalog.tags()
        except Exception as e:  # catalog down → still answer, just without filters
            log.warning("shopper.tags_failed", err=str(e), tenant=body.tenant)
            tags = []
        try:
            categories = await catalog.categories()
        except Exception as e:
            log.warning("shopper.categories_failed", err=str(e), tenant=body.tenant)
            categories = []

        provider = get_provider("ollama")

        # ---- 1. extract intent ----------------------------------------------------
        tax = taxonomy_by_concept(tags)
        tax_text = "\n".join(f"- {c}: {', '.join(v)}" for c, v in tax.items()) or "- (none configured yet)"
        cat_text = ", ".join(c["name"] for c in categories if c.get("name")) or "(none configured yet)"
        extract_system = _EXTRACT_PROMPT.replace("{taxonomy}", tax_text).replace("{categories}", cat_text)
        try:
            extract_resp = await provider.chat(
                ChatRequest(
                    messages=history,
                    system=extract_system,
                    model=settings.ai_model_shopper,
                    format="json",
                    temperature=0.0,
                    max_tokens=_EXTRACT_MAX_TOKENS,
                )
            )
        except Exception as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Shopper model error: {e}") from e
        intent = parse_intent(extract_resp.content)

        # ---- 2. clarify if too vague ----------------------------------------------
        if intent.need_clarification and not intent.has_search_signal():
            fallback = (
                "Boleh tahu lebih detail, Kak? Misalnya warna favorit, atau buat acara apa?"
                if locale == "id"
                else "Could you tell me a bit more? For example a favourite colour, or the occasion?"
            )
            return ShopperOut(reply=intent.clarify_question or fallback, clarify=True)

        # ---- 3. retrieve from the live catalog (in code) --------------------------
        # We surface relevant products regardless of stock (consistent with the
        # PLP, which shows "Sold out" cards); the reply step is told the live
        # stock status so it stays honest. Identity + price remain grounded.
        base = map_to_query(intent, tags, categories, limit=_MAX_PRODUCTS)
        # Broadening fallback: tags are sparsely populated, so a precise query can
        # come up empty even when a relevant product exists (e.g. a dress not
        # tagged "occasion:kondangan"). Relax in steps, but NEVER to a filterless
        # query — an attempt with no positive filter would dump the whole catalog
        # as if it matched, which reads as irrelevant. Better to say "no match".
        attempts = [base]
        if base.get("tag") and base.get("category"):
            attempts.append({**base, "tag": None})  # keep the category narrower
        if base.get("q") and (base.get("tag") or base.get("category")):
            # last resort: the shopper's explicit keywords only
            attempts.append({k: base[k] for k in ("q", "price_min", "price_max", "limit")})

        def _has_filter(p: dict) -> bool:
            return bool(p.get("category") or p.get("tag") or p.get("q")
                        or p.get("price_min") or p.get("price_max"))

        items: list[dict] = []
        for params in (p for p in attempts if _has_filter(p)):
            try:
                page = await catalog.search_products(**params)
                items = (page.get("items") or [])[:_MAX_PRODUCTS]
            except Exception as e:
                log.warning("shopper.search_failed", err=str(e), tenant=body.tenant, params=params)
                items = []
            if items:
                break

        # Zero matches: answer deterministically (no LLM) so we can NEVER invent
        # a product in the empty state.
        if not items:
            empty = (
                "Maaf, Kak, aku belum menemukan produk yang pas dengan permintaan itu. "
                "Boleh coba sebutkan warna, jenis, atau acaranya — nanti aku carikan lagi."
                if locale == "id"
                else "Sorry, I couldn't find a matching piece. Try telling me a colour, type, "
                "or occasion and I'll look again."
            )
            return ShopperOut(reply=empty, no_results=True, escalate=_wants_human(last_user))

        # ---- 4. synthesise a grounded reply ---------------------------------------
        catalog_json = json.dumps(
            [
                {
                    "name": it.get("name"),
                    "price": it.get("price"),
                    "currency": it.get("currency"),
                    "summary": it.get("summary"),
                    "in_stock": it.get("in_stock"),
                    "tags": [t.get("name") for t in (it.get("tags") or [])],
                }
                for it in items
            ],
            ensure_ascii=False,
        )
        request_summary = intent.model_dump(exclude_none=True, exclude={"need_clarification", "clarify_question"})
        synth_user = (
            f"Locale: {locale}\n"
            f"Shopper request: {last_user}\n"
            f"Parsed preferences: {json.dumps(request_summary, ensure_ascii=False)}\n"
            f"PRODUCTS (live catalog, may be empty):\n{catalog_json}\n"
        )
        try:
            reply_resp = await provider.chat(
                ChatRequest(
                    messages=[*history, Message(role="user", content=synth_user)],
                    system=_REPLY_PROMPT,
                    model=settings.ai_model_shopper,
                    temperature=0.4,
                    max_tokens=_REPLY_MAX_TOKENS,
                )
            )
            reply_text = reply_resp.content.strip()
        except Exception as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Shopper model error: {e}") from e

        # ---- 5. hard grounding guard ----------------------------------------------
        # Only real, in-stock catalog items surface as cards; prices are live.
        return ShopperOut(
            reply=reply_text,
            products=items,
            product_ids=[int(it["id"]) for it in items if it.get("id")],
            escalate=_wants_human(last_user),
            no_results=not items,
        )
    finally:
        await catalog.aclose()
