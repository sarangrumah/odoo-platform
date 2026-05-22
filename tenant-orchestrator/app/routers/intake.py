"""Public intake bridge.

Sits between the Next.js ``apps/landing-public`` app and odoo-mgmt's
``onboarding.public.submission`` / ``onboarding.journey`` models. All calls in
are HMAC-protected by ``security.HMACMiddleware`` (the landing app signs with
the shared secret); all calls out to Odoo go through ``odoo_jsonrpc.call``
which authenticates server-side — Odoo credentials never reach the browser.

Endpoints
---------
POST /v1/intake/submit
    Body: ``IntakeSubmitRequest``. Optionally verifies the Cloudflare
    Turnstile token via ``TURNSTILE_SECRET`` env. Returns the public
    status token + ready-to-share status URL.

GET  /v1/intake/{token}/status
    Returns ``IntakeStatusResponse`` by pulling submission + journey
    state from odoo-mgmt.

Merge notes (do not edit ``main.py`` from this branch):
    - Register: ``app.include_router(intake.router)``
    - Add CORS middleware allowing the landing origin (see README).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status

from .. import odoo_jsonrpc
from ..validators import (
    IntakeStatusResponse,
    IntakeSubmitRequest,
    IntakeSubmitResponse,
)

log = structlog.get_logger()

router = APIRouter(prefix="/v1/intake", tags=["intake"])

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _verify_turnstile(token: str, source_ip: str | None) -> None:
    """Verify Cloudflare Turnstile token. Skipped (warning logged) when secret unset."""
    secret = os.environ.get("TURNSTILE_SECRET")
    if not secret:
        log.warning(
            "intake.turnstile.skipped",
            reason="TURNSTILE_SECRET not configured — accepting all tokens",
        )
        return
    payload = {"secret": secret, "response": token}
    if source_ip:
        payload["remoteip"] = source_ip
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(TURNSTILE_VERIFY_URL, data=payload)
        result = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("intake.turnstile.error", error=str(e))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Turnstile verification unreachable") from e
    if not result.get("success"):
        log.warning("intake.turnstile.failed", codes=result.get("error-codes"))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Turnstile verification failed: {result.get('error-codes')}",
        )


def _status_url(token: str) -> str:
    base = os.environ.get("LANDING_PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        return f"/status/{token}"
    return f"{base}/status/{token}"


@router.post(
    "/submit",
    response_model=IntakeSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_intake(body: IntakeSubmitRequest, request: Request) -> IntakeSubmitResponse:
    """Create a public submission in odoo-mgmt and return its token."""
    actor = getattr(request.state, "actor", "landing-public")
    _verify_turnstile(body.turnstile_token, body.source_ip)

    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    # Strip the now-validated captcha token before forwarding — Odoo does not need it.
    payload.pop("turnstile_token", None)
    payload["submitted_by"] = actor

    try:
        # Odoo-side helper (provided by custom_onboarding_journey):
        #   @api.model
        #   def create_from_payload(self, payload) -> {'token': str}
        result = odoo_jsonrpc.call(
            "onboarding.public.submission",
            "create_from_payload",
            args=[payload],
        )
    except odoo_jsonrpc.OdooRpcError as e:
        log.error("intake.submit.odoo_error", error=str(e))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Odoo error: {e}") from e

    if not isinstance(result, dict) or not result.get("token"):
        log.error("intake.submit.bad_payload", result=result)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Odoo create_from_payload returned no token",
        )

    token = str(result["token"])
    log.info(
        "intake.submit.ok",
        actor=actor,
        vertical=body.vertical_target,
        company=body.company_name,
        token_prefix=token[:8],
    )
    return IntakeSubmitResponse(token=token, status_url=_status_url(token))


@router.get("/{token}/status", response_model=IntakeStatusResponse)
def get_intake_status(token: str) -> IntakeStatusResponse:
    """Resolve a public token to its submission + journey state."""
    if not token or len(token) < 8 or len(token) > 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token")

    try:
        submissions = odoo_jsonrpc.call(
            "onboarding.public.submission",
            "search_read",
            args=[[("public_token", "=", token)], ["id", "journey_id", "status"]],
            kwargs={"limit": 1},
        )
    except odoo_jsonrpc.OdooRpcError as e:
        log.error("intake.status.odoo_error", error=str(e))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Odoo error: {e}") from e

    if not submissions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")

    sub = submissions[0]
    journey_field = sub.get("journey_id")
    # Odoo returns M2O as [id, display_name] or False
    journey_id = journey_field[0] if isinstance(journey_field, (list, tuple)) and journey_field else None

    stage = "intake"
    target_go_live: str | None = None
    progress_pct: float | None = None

    if journey_id:
        try:
            journeys = odoo_jsonrpc.call(
                "onboarding.journey",
                "read",
                args=[[journey_id], ["stage", "target_go_live", "progress_pct"]],
            )
        except odoo_jsonrpc.OdooRpcError as e:
            log.warning("intake.status.journey_read_failed", error=str(e))
            journeys = []
        if journeys:
            j = journeys[0]
            stage = str(j.get("stage") or stage)
            tgl = j.get("target_go_live")
            target_go_live = str(tgl) if tgl else None
            pp = j.get("progress_pct")
            if isinstance(pp, (int, float)):
                progress_pct = float(pp)

    return IntakeStatusResponse(
        token=token,
        stage=stage,
        status=str(sub.get("status") or "pending"),
        target_go_live=target_go_live,
        progress_pct=progress_pct,
        journey_id=journey_id,
    )
