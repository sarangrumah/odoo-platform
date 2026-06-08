"""Best-effort operational alerts (WhatsApp via the baileys sidecar).

Sending is deliberately fail-safe: any error talking to baileys is logged and
swallowed so an alert-delivery problem can never mask or abort the underlying
operation (e.g. a backup failure) that triggered it.
"""

from __future__ import annotations

import httpx
import structlog

from .config import get_settings

log = structlog.get_logger()


def send_backup_failure_alert(slug: str, kind: str, error: str) -> None:
    """POST a WhatsApp text alert about a failed backup. Never raises."""
    s = get_settings()
    if not s.alert_whatsapp_enabled:
        return
    if not (s.baileys_shared_secret and s.alert_whatsapp_to and s.alert_whatsapp_session):
        log.warning("alert.skipped_misconfigured", reason="missing baileys secret/recipient/session")
        return

    text = (
        "⚠️ Backup GAGAL\n"
        f"Tenant: {slug}\n"
        f"Jenis: {kind}\n"
        f"Error: {error[:400]}"
    )
    url = f"{s.baileys_url.rstrip('/')}/sessions/{s.alert_whatsapp_session}/messages"
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {s.baileys_shared_secret}"},
            json={"to": s.alert_whatsapp_to, "type": "text", "text": text},
            timeout=10.0,
        )
        if r.status_code >= 400:
            log.error("alert.send_failed", status=r.status_code, body=r.text[:300], slug=slug)
        else:
            log.info("alert.sent", channel="whatsapp", slug=slug)
    except Exception as e:  # noqa: BLE001 - alerts must never raise
        log.error("alert.send_exception", err=str(e), slug=slug)
