"""Build the metric bundle to send to ai-gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .prom_client import PromClient

# Metric specs: PromQL query, friendly name, unit, capacity reference
SPECS = [
    {
        "name": "cpu_usage_percent",
        "query": "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
        "unit": "percent",
        "max": 100.0,
    },
    {
        "name": "memory_used_percent",
        "query": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
        "unit": "percent",
        "max": 100.0,
    },
    {
        "name": "disk_used_percent",
        "query": "(1 - (node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes{mountpoint='/'})) * 100",
        "unit": "percent",
        "max": 100.0,
    },
    {
        "name": "pg_active_connections",
        "query": "sum(pg_stat_activity_count)",
        "unit": "count",
        "max": None,
    },
    {
        "name": "redis_memory_used_bytes",
        "query": "redis_memory_used_bytes",
        "unit": "bytes",
        "max": None,
    },
    {
        "name": "odoo_request_rate",
        "query": "sum(rate(odoo_http_requests_total[5m]))",
        "unit": "rps",
        "max": None,
    },
]


@dataclass(slots=True)
class Bundle:
    metrics: list[dict[str, Any]]


async def build_bundle(prom: PromClient, window_seconds: int = 7 * 24 * 3600) -> Bundle:
    metrics: list[dict[str, Any]] = []
    for spec in SPECS:
        try:
            series = await prom.query_range(spec["query"], window_seconds=window_seconds, step_seconds=900)
        except Exception:
            series = None
        metrics.append(
            {
                "name": spec["name"],
                "unit": spec["unit"],
                "current_max_capacity": spec["max"],
                "series": series.points if series else [],
            }
        )
    return Bundle(metrics=metrics)
