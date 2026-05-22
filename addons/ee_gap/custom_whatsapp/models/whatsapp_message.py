# -*- coding: utf-8 -*-
"""WhatsApp message queue with real Meta Cloud API dispatch + inbound storage."""

from __future__ import annotations

import logging
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Map template categories to the consent purpose code that must be active
# on the recipient partner before the message may be sent.
_CATEGORY_PURPOSE = {
    "marketing": "whatsapp_marketing",
    "utility": "whatsapp_utility",
    "authentication": "whatsapp_utility",
}

# Above this count, action_send_bulk dispatches via queue_job instead of
# blocking the calling request.
_BULK_ASYNC_THRESHOLD = 5


class WhatsappMessage(models.Model):
    _name = "whatsapp.message"
    _description = "WhatsApp Message"
    _inherit = ["mail.thread", "pdp.audited.mixin"]
    _order = "create_date desc"

    account_id = fields.Many2one(
        "whatsapp.account",
        string="Account",
        required=True,
        ondelete="restrict",
        index=True,
    )
    template_id = fields.Many2one(
        "whatsapp.template",
        string="Template",
        ondelete="set null",
    )
    to_phone = fields.Char(
        string="To (Phone)",
        required=True,
        help="E.164 formatted recipient number, e.g. +6281234567890.",
    )
    to_partner_id = fields.Many2one(
        "res.partner",
        string="Recipient",
        ondelete="set null",
        index=True,
    )
    body = fields.Text()
    direction = fields.Selection(
        [
            ("outbound", "Outbound"),
            ("inbound", "Inbound"),
        ],
        default="outbound",
        required=True,
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("failed", "Failed"),
            ("received", "Received"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    error_message = fields.Text(readonly=True)
    sent_at = fields.Datetime(readonly=True)
    provider_message_id = fields.Char(
        string="Provider Message ID",
        readonly=True,
        index=True,
        help="Upstream wamid/message SID returned by the provider on accept.",
    )
    consent_verified = fields.Boolean(default=False, readonly=True)

    # ---------- public API ----------

    def action_send(self):
        """Verify PDP consent, then HTTP-POST to the Meta Cloud API.

        Failures are recorded on the record (state='failed' +
        error_message) and never re-raised to the caller — bulk
        dispatch must keep going if one recipient fails.
        """
        Consent = self.env["pdp.consent"]
        for rec in self:
            if rec.direction == "inbound":
                # Inbound rows are informational only.
                continue

            category = rec.template_id.category if rec.template_id else None
            purpose_code = _CATEGORY_PURPOSE.get(category)

            consent_ok = True
            if purpose_code:
                if not rec.to_partner_id:
                    consent_ok = False
                else:
                    consent_ok = Consent.check_consent(rec.to_partner_id, purpose_code)

            if not consent_ok and category == "marketing":
                raise UserError(
                    _("Cannot send marketing WhatsApp to %s: no active PDP consent for purpose 'whatsapp_marketing'.")
                    % (rec.to_partner_id.display_name or rec.to_phone)
                )

            if not consent_ok:
                _logger.warning(
                    "whatsapp.message %s: sending %s without verified consent (purpose=%s)",
                    rec.id,
                    category,
                    purpose_code,
                )

            rec.consent_verified = consent_ok
            rec._do_send()
        return True

    def action_send_bulk(self):
        """Dispatch many records.

        If the recordset is larger than ``_BULK_ASYNC_THRESHOLD`` and
        ``queue_job`` is available, enqueue one job per message on the
        ``root.whatsapp`` channel. Otherwise send inline.
        """
        if not self:
            return True

        if len(self) <= _BULK_ASYNC_THRESHOLD:
            return self.action_send()

        # queue_job is a hard dependency, so with_delay is always available.
        for rec in self:
            try:
                rec.with_delay(
                    channel="root.whatsapp",
                    description=f"WhatsApp send {rec.id} -> {rec.to_phone}",
                ).action_send()
            except Exception as e:
                # Fall back to inline send if the queue is unavailable.
                _logger.warning(
                    "queue_job dispatch failed for whatsapp.message %s: %s — sending inline",
                    rec.id,
                    e,
                )
                rec.action_send()
        return True

    # ---------- internal: build payload + dispatch ----------

    def _do_send(self):
        """Single-record send. Catches all exceptions and records failure."""
        self.ensure_one()
        account = self.account_id
        if not account.is_active:
            self.write({"state": "failed", "error_message": "Account is inactive."})
            return

        # Sandbox mode: synthesise a message id and short-circuit.
        if account.sandbox_mode:
            fake_id = f"sandbox-{uuid.uuid4().hex[:16]}"
            _logger.info(
                "[whatsapp sandbox] account=%s to=%s template=%s body=%s -> %s",
                account.name,
                self.to_phone,
                self.template_id.name if self.template_id else None,
                (self.body or "")[:120],
                fake_id,
            )
            self.write(
                {
                    "state": "sent",
                    "sent_at": fields.Datetime.now(),
                    "provider_message_id": fake_id,
                    "error_message": False,
                }
            )
            return

        payload = self._build_payload()
        try:
            response = account._post("messages", payload)
            messages = response.get("messages") or []
            provider_id = messages[0].get("id") if messages else None
            if not provider_id:
                raise RuntimeError(f"Meta response missing messages[0].id: {response!r}")
            self.write(
                {
                    "state": "sent",
                    "sent_at": fields.Datetime.now(),
                    "provider_message_id": provider_id,
                    "error_message": False,
                }
            )
        except Exception as e:
            _logger.exception("whatsapp.message %s send failed", self.id)
            self.write(
                {
                    "state": "failed",
                    "error_message": str(e)[:2000],
                }
            )

    def _build_payload(self) -> dict:
        """Return a Meta Cloud API messages payload for this record.

        - If ``template_id`` is set and approved, send as ``template``.
        - Otherwise send as plain ``text``.
        """
        self.ensure_one()
        # Strip leading '+' for Meta E.164 (they accept either, but the
        # docs example omits the plus).
        to = (self.to_phone or "").lstrip("+").strip()

        if self.template_id and self.template_id.status == "approved":
            tpl = self.template_id
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": tpl.name,
                    "language": {"code": tpl.language_code or "id"},
                },
            }
            return payload

        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": self.body or ""},
        }

    # ---------- webhook update entry-points (called from controller) ----------

    @api.model
    def _apply_status_update(self, status_payload: dict) -> bool:
        """Apply a Meta webhook ``statuses`` entry to a stored message.

        Expected shape per Meta docs::

            {"id": "<wamid>", "status": "delivered"|"read"|"sent"|"failed",
             "timestamp": "...", "errors": [...]}
        """
        wamid = status_payload.get("id")
        status = (status_payload.get("status") or "").lower()
        if not wamid or not status:
            return False

        msg = self.sudo().search([("provider_message_id", "=", wamid)], limit=1)
        if not msg:
            _logger.info("whatsapp webhook: no message for wamid=%s", wamid)
            return False

        # Map Meta lifecycle to our state enum.
        state_map = {
            "sent": "sent",
            "delivered": "delivered",
            "read": "read",
            "failed": "failed",
        }
        new_state = state_map.get(status)
        if not new_state:
            return False

        vals: dict = {"state": new_state}
        if status == "failed":
            errs = status_payload.get("errors") or []
            if errs:
                vals["error_message"] = str(errs[0])[:2000]
        msg.write(vals)
        return True

    @api.model
    def _record_inbound(self, account, message_payload: dict, contact_payload: dict | None = None) -> "WhatsappMessage":
        """Create a whatsapp.message row for an inbound Meta message.

        ``message_payload`` is one entry of ``value.messages``::

            {"from": "62812...", "id": "wamid....", "timestamp": "...",
             "text": {"body": "..."}, "type": "text"}
        """
        from_phone = message_payload.get("from") or ""
        msg_id = message_payload.get("id")
        msg_type = message_payload.get("type") or "text"

        body = ""
        if msg_type == "text":
            body = (message_payload.get("text") or {}).get("body", "")
        else:
            body = f"[{msg_type} message]"

        # Try to resolve the partner by phone.
        partner = (
            self.env["res.partner"]
            .sudo()
            .search(
                ["|", ("phone", "ilike", from_phone[-9:]), ("mobile", "ilike", from_phone[-9:])],
                limit=1,
            )
        )

        vals = {
            "account_id": account.id,
            "to_phone": from_phone,
            "to_partner_id": partner.id if partner else False,
            "body": body,
            "direction": "inbound",
            "state": "received",
            "provider_message_id": msg_id,
            "sent_at": fields.Datetime.now(),
        }
        return self.sudo().create(vals)
