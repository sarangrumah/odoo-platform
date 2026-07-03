"""Environment configuration for the finance-sap-bridge."""
from __future__ import annotations

import os


class Settings:
    odoo_base_url: str = os.getenv("ODOO_BASE_URL", "http://odoo:8069")
    inbound_secret: str = os.getenv("BRIDGE_INBOUND_SECRET", "")
    outbound_secret: str = os.getenv("BRIDGE_OUTBOUND_SECRET", "")

    kafka_bootstrap: str = os.getenv("KAFKA_BOOTSTRAP", "")
    kafka_group_id: str = os.getenv("KAFKA_GROUP_ID", "finance-sap-bridge")
    topic_prefix_to_sap: str = os.getenv("KAFKA_TOPIC_PREFIX_TO_SAP", "portal.to-sap")
    topic_from_sap: str = os.getenv("KAFKA_TOPIC_FROM_SAP", "sap.to-portal.status")
    topic_from_hris: str = os.getenv("KAFKA_TOPIC_FROM_HRIS", "hris.to-portal.travel")

    hmac_drift_seconds: int = int(os.getenv("HMAC_DRIFT_SECONDS", "300"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def kafka_enabled(self) -> bool:
        return bool(self.kafka_bootstrap)


settings = Settings()
