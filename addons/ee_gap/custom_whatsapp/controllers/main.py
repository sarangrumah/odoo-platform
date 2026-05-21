# -*- coding: utf-8 -*-
"""Meta WhatsApp Cloud API webhook endpoints.

Two methods on the same path::

    GET  /custom_whatsapp/webhook/<account_id>  — verify-token handshake
    POST /custom_whatsapp/webhook/<account_id>  — status + inbound message events

Both endpoints are public (``auth='public'``) because Meta cannot
authenticate against Odoo; the verify-token (GET) and the inbound
payload's own ``account_id`` segment + downstream lookups provide the
security boundary.
"""

from __future__ import annotations

import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WhatsappWebhookController(http.Controller):

    @http.route(
        "/custom_whatsapp/webhook/<int:account_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def webhook_verify(self, account_id, **kwargs):
        """Meta verify-token handshake.

        Meta calls this once when the webhook URL is registered.
        Query params: ``hub.mode``, ``hub.verify_token``, ``hub.challenge``.
        We must echo ``hub.challenge`` if the token matches.
        """
        mode = kwargs.get("hub.mode") or request.params.get("hub.mode")
        token = kwargs.get("hub.verify_token") or request.params.get("hub.verify_token")
        challenge = kwargs.get("hub.challenge") or request.params.get("hub.challenge")

        account = request.env["whatsapp.account"].sudo().browse(account_id).exists()
        if not account:
            _logger.warning("[whatsapp webhook] verify: unknown account_id=%s", account_id)
            return Response("account not found", status=404)

        expected = account.webhook_verify_token or ""
        if mode == "subscribe" and token and token == expected:
            _logger.info("[whatsapp webhook] verify ok for account=%s", account.name)
            return Response(challenge or "", status=200, content_type="text/plain")

        _logger.warning(
            "[whatsapp webhook] verify FAILED for account=%s (mode=%s)",
            account.name, mode,
        )
        return Response("forbidden", status=403)

    @http.route(
        "/custom_whatsapp/webhook/<int:account_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_event(self, account_id, **kwargs):
        """Inbound event: status updates + new messages.

        Meta payload shape (abridged)::

            {"object": "whatsapp_business_account",
             "entry": [{"id": "...", "changes": [{"value": {
                 "messaging_product": "whatsapp",
                 "metadata": {...},
                 "contacts": [...],
                 "messages": [...],   # inbound
                 "statuses": [...],   # delivery updates
             }, "field": "messages"}]}]}
        """
        account = request.env["whatsapp.account"].sudo().browse(account_id).exists()
        if not account:
            _logger.warning("[whatsapp webhook] event: unknown account_id=%s", account_id)
            return Response("account not found", status=404)

        try:
            raw = request.httprequest.get_data() or b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError) as e:
            _logger.warning("[whatsapp webhook] bad json: %s", e)
            return Response("bad request", status=400)

        try:
            self._dispatch_payload(account, payload)
        except Exception:
            # Never 500 back to Meta — they retry aggressively and
            # we'd rather see the log than be barraged.
            _logger.exception("[whatsapp webhook] dispatch failed for account=%s", account.name)

        # Always 200 so Meta marks the event delivered.
        return Response("ok", status=200, content_type="text/plain")

    # ----- internals -----

    def _dispatch_payload(self, account, payload: dict):
        Message = request.env["whatsapp.message"].sudo()
        for entry in (payload.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}

                # 1) Delivery / read / failure status updates
                for st in (value.get("statuses") or []):
                    try:
                        Message._apply_status_update(st)
                    except Exception:
                        _logger.exception(
                            "[whatsapp webhook] status update failed: %s", st,
                        )

                # 2) Inbound messages from end-users
                contacts = value.get("contacts") or []
                for idx, msg in enumerate(value.get("messages") or []):
                    contact = contacts[idx] if idx < len(contacts) else None
                    try:
                        Message._record_inbound(account, msg, contact)
                    except Exception:
                        _logger.exception(
                            "[whatsapp webhook] inbound record failed: %s", msg,
                        )
