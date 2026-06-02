"""Async client for the public Odoo storefront catalog API.

Reuses the *existing* endpoints in ``custom_storefront_api`` — no new Odoo route
is needed. The tenant DB is selected per request via the ``X-Odoo-Database``
header (Odoo 19), matching how the Next.js BFF resolves tenants.

Responses are wrapped by Odoo as ``{"ok": true, "data": ...}`` (see
``custom_storefront_api/controllers/cors.py``); this client unwraps ``data``.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger()

# Tag taxonomy changes rarely; cache it per (tenant, lang) for a few minutes so
# a multi-turn conversation doesn't re-fetch it on every message.
_TAG_TTL_SECONDS = 300


class OdooCatalog:
    def __init__(self, tenant: str, lang: str = "id") -> None:
        s = get_settings()
        self._base = s.odoo_storefront_url.rstrip("/")
        self._tenant = tenant
        self._lang = lang
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-Odoo-Database": self._tenant,
            "X-Tenant-Slug": self._tenant,
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base}/storefront/api/{path}"
        params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
        params.setdefault("lang", self._lang)
        r = await self._client.get(url, params=params, headers=self._headers())
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict) or not body.get("ok"):
            raise RuntimeError(f"catalog error for {path}: {body}")
        return body.get("data")

    async def search_products(
        self,
        *,
        q: str | None = None,
        tag: str | None = None,
        category: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        sort: str | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        return await self._get(
            "products",
            {
                "q": q,
                "tag": tag,
                "category": category,
                "price_min": price_min,
                "price_max": price_max,
                "sort": sort,
                "limit": limit,
            },
        )

    async def get_product(self, product_id: int) -> dict[str, Any]:
        return await self._get(f"products/{product_id}")

    async def tags(self) -> list[dict[str, Any]]:
        cached = _TAG_CACHE.get((self._tenant, self._lang))
        if cached and (time.monotonic() - cached[0]) < _TAG_TTL_SECONDS:
            return cached[1]
        data = await self._get("tags")
        tags = data if isinstance(data, list) else []
        _TAG_CACHE[(self._tenant, self._lang)] = (time.monotonic(), tags)
        return tags

    async def categories(self) -> list[dict[str, Any]]:
        cached = _CAT_CACHE.get((self._tenant, self._lang))
        if cached and (time.monotonic() - cached[0]) < _TAG_TTL_SECONDS:
            return cached[1]
        data = await self._get("categories")
        cats = data if isinstance(data, list) else []
        _CAT_CACHE[(self._tenant, self._lang)] = (time.monotonic(), cats)
        return cats

    async def aclose(self) -> None:
        await self._client.aclose()


# module-level caches: {(tenant, lang): (monotonic_ts, [...])}
_TAG_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
_CAT_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
