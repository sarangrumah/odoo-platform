"""Minimal Odoo exporter.

Exposes:
- odoo_http_up{}             — 1 if HTTP endpoint reachable
- odoo_longpoll_up{}         — 1 if longpolling reachable
- odoo_http_request_duration_seconds{le="..."} histogram from probe
- odoo_db_count               — number of databases listed (only if list_db)
"""

from __future__ import annotations

import os
import time

import httpx
from prometheus_client import Counter, Gauge, Histogram, start_http_server

ODOO_BASE_URL = os.environ.get("ODOO_BASE_URL", "http://odoo:8069")
ODOO_LONGPOLL_URL = os.environ.get("ODOO_LONGPOLL_URL", "http://odoo:8072")
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))

http_up = Gauge("odoo_http_up", "Odoo HTTP endpoint reachability (1=up)")
longpoll_up = Gauge("odoo_longpoll_up", "Odoo longpolling endpoint reachability (1=up)")
probe_duration = Histogram(
    "odoo_http_request_duration_seconds",
    "Probe request duration",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)
db_count = Gauge("odoo_db_count", "Number of DBs listed via /web/database/list")
probe_errors = Counter("odoo_probe_errors_total", "Probe error count", ["target"])


def probe_http() -> None:
    try:
        with probe_duration.time():
            with httpx.Client(timeout=httpx.Timeout(5.0)) as c:
                r = c.get(f"{ODOO_BASE_URL}/web/login")
                http_up.set(1.0 if r.status_code in (200, 303, 302) else 0.0)
                # Attempt DB listing (works only when list_db=true)
                try:
                    r2 = c.post(
                        f"{ODOO_BASE_URL}/web/database/list",
                        json={"jsonrpc": "2.0", "method": "call", "params": {}},
                    )
                    if r2.status_code == 200:
                        data = r2.json().get("result", [])
                        if isinstance(data, list):
                            db_count.set(len(data))
                except httpx.HTTPError:
                    pass
    except httpx.HTTPError:
        http_up.set(0.0)
        probe_errors.labels(target="http").inc()


def probe_longpoll() -> None:
    try:
        with httpx.Client(timeout=httpx.Timeout(3.0)) as c:
            r = c.get(f"{ODOO_LONGPOLL_URL}/longpolling/poll", params={"channels": "[]"})
            # 200 / 401 / 404 all indicate server is up; only connection error = down
            longpoll_up.set(1.0 if r.status_code < 500 else 0.0)
    except httpx.HTTPError:
        longpoll_up.set(0.0)
        probe_errors.labels(target="longpoll").inc()


def main() -> None:
    start_http_server(9200)
    while True:
        probe_http()
        probe_longpoll()
        time.sleep(SCRAPE_INTERVAL)


if __name__ == "__main__":
    main()
