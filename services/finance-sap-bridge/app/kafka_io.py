"""Pluggable Kafka layer. Falls back to an in-memory mock when confluent-kafka
is unavailable or KAFKA_BOOTSTRAP is unset, so the Odoo↔bridge REST contract can
be exercised before the real bus exists.

Idempotency and DLQ are sketched here as the integration points a production
build fills in (a real store + a dead-letter topic).
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from .config import settings

_logger = logging.getLogger("finance-sap-bridge.kafka")

try:  # optional dependency
    from confluent_kafka import Consumer, Producer  # type: ignore

    _HAVE_KAFKA = True
except Exception:  # pragma: no cover
    _HAVE_KAFKA = False


class _MockProducer:
    def produce(self, topic, key=None, value=None):
        _logger.info("[mock-kafka] produce topic=%s key=%s value=%s", topic, key, value)

    def flush(self, timeout=5):
        return 0


class KafkaIO:
    """Thin wrapper. Use ``enabled`` to branch; mock mode keeps the API stable."""

    def __init__(self):
        self.enabled = settings.kafka_enabled and _HAVE_KAFKA
        self._seen_keys: set[str] = set()  # idempotency sketch (swap for Redis/db)
        if self.enabled:
            self._producer = Producer({"bootstrap.servers": settings.kafka_bootstrap})
        else:
            if settings.kafka_enabled and not _HAVE_KAFKA:
                _logger.warning("KAFKA_BOOTSTRAP set but confluent-kafka missing → mock mode")
            self._producer = _MockProducer()

    # -- idempotency --
    def already_processed(self, key: str) -> bool:
        if not key:
            return False
        if key in self._seen_keys:
            return True
        self._seen_keys.add(key)
        return False

    # -- produce (Portal → SAP) --
    def produce(self, topic: str, key: str, payload: dict):
        self._producer.produce(topic, key=key, value=json.dumps(payload).encode("utf-8"))
        self._producer.flush(timeout=5)

    # -- consume loop (SAP/HRIS → Portal). Runs in a background thread. --
    def consume_loop(self, topics: list[str], handler: Callable[[str, dict], None]):
        if not self.enabled:
            _logger.info("[mock-kafka] consume_loop skipped (mock mode): %s", topics)
            return
        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap,
                "group.id": settings.kafka_group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        consumer.subscribe(topics)
        _logger.info("kafka consume_loop subscribed: %s", topics)
        try:
            while True:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    _logger.error("kafka error: %s", msg.error())
                    continue
                key = (msg.key() or b"").decode("utf-8", "ignore")
                if self.already_processed(key):
                    continue
                try:
                    payload = json.loads(msg.value() or b"{}")
                    handler(msg.topic(), payload)
                except Exception as e:  # → dead-letter in production
                    _logger.exception("handler failed (would DLQ): %s", e)
        finally:
            consumer.close()


kafka = KafkaIO()
