# -*- coding: utf-8 -*-
"""WhatsApp Cloud API account configuration (per-company) + HTTP adapter helpers.

The adapter follows the pattern used by ``custom_coretax_pajakku`` —
retry with exponential backoff up to 3 attempts, honour ``Retry-After``
on 429, and a per-account circuit breaker (10 consecutive failures
opens for 1 hour). Sandbox mode short-circuits real HTTP calls and
returns a synthetic message id so the rest of the pipeline can be
exercised without consuming Meta quota.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Meta Graph API version. v22.0 is the GA version as of 2026.
META_GRAPH_VERSION = "v22.0"
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# ----- Circuit breaker state (module-level, per-account) -----
_CB_STATE: dict[int, dict[str, float]] = {}
_CB_THRESHOLD = 10
_CB_OPEN_SECONDS = 3600

# Retry policy
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds; doubles each attempt
_HTTP_TIMEOUT = 30


def _now() -> float:
    return time.monotonic()


def _circuit_open(account_id: int) -> bool:
    st = _CB_STATE.get(account_id)
    return bool(st and _now() < st.get("open_until", 0))


def _circuit_record_success(account_id: int) -> None:
    _CB_STATE.pop(account_id, None)


def _circuit_record_failure(account_id: int) -> bool:
    st = _CB_STATE.setdefault(account_id, {"fail_streak": 0, "open_until": 0})
    st["fail_streak"] += 1
    if st["fail_streak"] >= _CB_THRESHOLD:
        st["open_until"] = _now() + _CB_OPEN_SECONDS
        return True
    return False


class WhatsappAccount(models.Model):
    _name = "whatsapp.account"
    _description = "WhatsApp Account"
    _order = "name"

    name = fields.Char(required=True)
    provider = fields.Selection(
        [
            ("meta_cloud", "Meta WhatsApp Cloud API"),
            ("twilio", "Twilio WhatsApp"),
        ],
        default="meta_cloud",
        required=True,
    )
    phone_number_id = fields.Char(
        string="Phone Number ID",
        help="Meta Cloud API phone_number_id used as the from-address for outbound messages.",
    )
    business_account_id = fields.Char(
        string="WhatsApp Business Account ID",
        help="Meta WABA ID owning the phone number and approved templates.",
    )
    access_token = fields.Char(
        string="Access Token",
        groups="custom_whatsapp.group_manager",
        help=(
            "System User access token (Meta Cloud) or Auth Token (Twilio). "
            "Stored as plain Char in this phase — move to custom.ir.config encrypted "
            "storage before production rollout."
        ),
    )
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        groups="custom_whatsapp.group_manager",
        help="Shared secret presented by Meta when verifying the webhook callback URL.",
    )
    is_active = fields.Boolean(default=True)
    sandbox_mode = fields.Boolean(
        default=True,
        help="When enabled, outbound sends are stubbed/logged instead of hitting the live Graph API.",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )

    # ----- API URL helpers -----

    def _get_api_url(self, endpoint: str | None = None) -> str:
        """Build the Cloud API URL for a given endpoint on this account.

        ``endpoint`` is the resource appended to the phone-number path,
        e.g. ``"messages"`` -> ``.../{phone_number_id}/messages``.
        If ``endpoint`` is None, returns the phone-number base URL.
        """
        self.ensure_one()
        if not self.phone_number_id:
            raise UserError(_("WhatsApp account '%s' has no phone_number_id configured.") % self.name)
        base = f"{META_GRAPH_BASE}/{self.phone_number_id}"
        return f"{base}/{endpoint}" if endpoint else base

    def _get_waba_url(self, endpoint: str) -> str:
        """Build a WhatsApp Business Account scoped URL."""
        self.ensure_one()
        if not self.business_account_id:
            raise UserError(_("WhatsApp account '%s' has no business_account_id configured.") % self.name)
        return f"{META_GRAPH_BASE}/{self.business_account_id}/{endpoint}"

    def _get_headers(self) -> dict[str, str]:
        self.ensure_one()
        token = self.sudo().access_token or ""
        if not token and not self.sandbox_mode:
            raise UserError(_("WhatsApp account '%s' has no access_token configured.") % self.name)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ----- HTTP -----

    def _request(
        self, method: str, url: str, *, json_body: dict | None = None, params: dict | None = None
    ) -> dict[str, Any]:
        """Perform an HTTP request with retry + circuit breaker.

        Returns the parsed JSON body on success. Raises ``RuntimeError``
        with a sanitised message on failure (access_token is never
        included in the exception text).
        """
        self.ensure_one()
        request_id = uuid.uuid4().hex[:8]

        if _circuit_open(self.id):
            raise RuntimeError(
                f"WhatsApp circuit breaker OPEN for account '{self.name}' (req={request_id}). Auto-resets in ~1h."
            )

        headers = self._get_headers()
        attempt = 0
        last_exc: Exception | None = None
        t0 = time.monotonic()

        while attempt < _MAX_RETRIES:
            attempt += 1
            try:
                _logger.info(
                    "[whatsapp http] req=%s account=%s attempt=%s %s %s",
                    request_id,
                    self.name,
                    attempt,
                    method,
                    url,
                )
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                    timeout=_HTTP_TIMEOUT,
                )
                latency_ms = int((time.monotonic() - t0) * 1000)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    if attempt < _MAX_RETRIES:
                        _logger.warning(
                            "[whatsapp http] req=%s 429 received, sleeping %ss",
                            request_id,
                            retry_after,
                        )
                        time.sleep(min(retry_after, 30))
                        continue

                if resp.status_code >= 500 and attempt < _MAX_RETRIES:
                    _logger.warning(
                        "[whatsapp http] req=%s status=%s, retrying",
                        request_id,
                        resp.status_code,
                    )
                    time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue

                if resp.status_code >= 400:
                    # Don't include token in error text. resp.text is OK; Meta
                    # error bodies do not echo Authorization.
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")

                _circuit_record_success(self.id)
                _logger.info(
                    "[whatsapp http] req=%s ok status=%s latency=%sms",
                    request_id,
                    resp.status_code,
                    latency_ms,
                )
                try:
                    return resp.json() if resp.content else {}
                except ValueError:
                    return {"raw": resp.text}

            except requests.RequestException as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                break

        tripped = _circuit_record_failure(self.id)
        if tripped:
            _logger.error(
                "[whatsapp http] req=%s circuit OPENED for account=%s",
                request_id,
                self.name,
            )
        raise RuntimeError(
            f"WhatsApp request failed after {_MAX_RETRIES} attempts "
            f"(req={request_id}): {last_exc or 'see prior log line'}"
        )

    def _post(self, endpoint: str, payload: dict) -> dict[str, Any]:
        """POST a JSON payload to ``{phone_number_id}/{endpoint}``."""
        self.ensure_one()
        return self._request("POST", self._get_api_url(endpoint), json_body=payload)

    def _get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        """GET an arbitrary Graph URL (used for WABA template polling)."""
        self.ensure_one()
        return self._request("GET", url, params=params)

    # ----- UI action: test connection -----

    def action_test_connection(self):
        """Smoke-test: GET the phone-number resource to validate token + id."""
        self.ensure_one()
        if self.sandbox_mode:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sandbox Mode"),
                    "message": _("Account is in sandbox mode — no real HTTP call performed."),
                    "type": "info",
                    "sticky": False,
                },
            }
        try:
            body = self._get(self._get_api_url())
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection OK"),
                    "message": _("Phone number resource reachable: %s") % body.get("id", "n/a"),
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection Failed"),
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
            }
