"""Thin Prometheus query_range client."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class Series:
    name: str
    points: list[tuple[int, float]]


class PromClient:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def query_range(self, query: str, window_seconds: int, step_seconds: int = 300) -> Series:
        end = int(time.time())
        start = end - window_seconds
        r = await self._client.get(
            f"{self._base}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step_seconds},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success" or not data["data"]["result"]:
            return Series(name=query, points=[])
        # Take first series; aggregate-already in PromQL
        values = data["data"]["result"][0]["values"]
        points: list[tuple[int, float]] = []
        for ts, val in values:
            try:
                points.append((int(ts), float(val)))
            except (ValueError, TypeError):
                continue
        return Series(name=query, points=points)

    async def aclose(self) -> None:
        await self._client.aclose()
