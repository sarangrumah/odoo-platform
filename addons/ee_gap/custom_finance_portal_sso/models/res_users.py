# -*- coding: utf-8 -*-
"""Map Keycloak roles → platform roles (and, failing that, groups) on sign-in.

Since ``custom_role_manager`` exists, an incoming role name is first matched
against ``custom.security.role.code``: the identity provider and Odoo then speak
the same vocabulary, and the group composition of a job title lives in exactly
one place. Names that match no role fall back to the original
xmlid map, so a tenant migrates one role at a time rather than in a flag day.

Additive by default, as before — a sign-in never takes rights away. Set
``custom_finance_portal_sso.roles_authoritative`` to ``"1"`` to make the provider
own the role list instead; that is only safe because the role engine revokes
strictly what it granted itself.
"""

from __future__ import annotations

import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

ROLE_MAP_PARAM = "custom_finance_portal_sso.role_group_map"
# "1" makes the identity provider authoritative over custom.security.role
# membership (a role dropped in Keycloak is dropped here on the next sign-in).
# Off by default — see _finance_sso_apply_security_roles.
AUTHORITATIVE_PARAM = "custom_finance_portal_sso.roles_authoritative"

# Keycloak role/group name → Finance Portal group xmlid. Override per tenant via
# the ROLE_MAP_PARAM ir.config_parameter (JSON).
DEFAULT_ROLE_MAP = {
    "finance_manager": "custom_finance_portal.group_finance_manager",
    "finance_officer": "custom_finance_portal.group_finance_officer",
    "finance_tax": "custom_finance_portal.group_finance_tax",
    "finance_requester": "custom_finance_portal.group_finance_user",
    "finance_vendor": "custom_finance_portal.group_finance_vendor",
}


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        login = super()._auth_oauth_signin(provider, validation, params)
        try:
            user = self.sudo().search([("login", "=", login)], limit=1)
            if user:
                user._finance_sso_apply_roles(validation or {})
        except Exception as e:  # never block login on a mapping hiccup
            _logger.warning("Finance SSO role mapping failed for %s: %s", login, e)
        return login

    # ------------------------------------------------------------------
    def _finance_sso_role_map(self) -> dict:
        raw = self.env["ir.config_parameter"].sudo().get_param(ROLE_MAP_PARAM)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                _logger.warning("Invalid %s — using defaults", ROLE_MAP_PARAM)
        return DEFAULT_ROLE_MAP

    @staticmethod
    def _finance_sso_extract_roles(validation: dict) -> set:
        """Collect roles from common Keycloak claim shapes."""
        roles: list = []
        if not isinstance(validation, dict):
            return set()
        roles += list((validation.get("realm_access") or {}).get("roles") or [])
        roles += list(validation.get("groups") or [])
        roles += list(validation.get("roles") or [])
        for _client, acc in (validation.get("resource_access") or {}).items():
            if isinstance(acc, dict):
                roles += list(acc.get("roles") or [])
        # Keycloak group paths arrive as "/finance_vendor" — strip the slash.
        return {r.lstrip("/") for r in roles if r}

    def _finance_sso_apply_security_roles(self, roles: set) -> set:
        """Match incoming role names against ``custom.security.role.code``.

        Returns the role names that were consumed, so the caller only falls back
        to the raw group map for what is left. This is what makes an identity
        provider's role names mean the same thing as the roles an administrator
        sees in Odoo, instead of the two drifting apart.

        Soft-detected: on a database without ``custom_role_manager`` nothing
        changes.
        """
        self.ensure_one()
        if not roles or "custom.security.role" not in self.env:
            return set()
        Role = self.env["custom.security.role"].sudo()
        matched = Role.search([("code", "in", list(roles))])
        if not matched:
            return set()

        authoritative = self.env["ir.config_parameter"].sudo().get_param(AUTHORITATIVE_PARAM, "0") == "1"
        if authoritative:
            # The identity provider owns the role list: a role removed there is
            # removed here on the next sign-in. Safe only because the role engine
            # revokes strictly what it granted itself — groups given by hand
            # survive either way. Off by default: on a tenant whose Keycloak
            # groups are incomplete this would quietly demote everybody.
            self.sudo().write({"role_ids": [(6, 0, matched.ids)]})
        else:
            self.sudo().write({"role_ids": [(4, role.id) for role in matched]})
        _logger.info(
            "Finance SSO: %s roles %s for %s",
            "set" if authoritative else "granted",
            matched.mapped("code"),
            self.login,
        )
        return set(matched.mapped("code"))

    def _finance_sso_apply_roles(self, validation: dict):
        self.ensure_one()
        roles = self._finance_sso_extract_roles(validation)

        # Security roles first — they are the platform's own vocabulary. Only
        # the names they did not claim go through the legacy group map, so a
        # tenant can migrate one role at a time without a flag day.
        consumed = self._finance_sso_apply_security_roles(roles)

        mapping = self._finance_sso_role_map()
        group_ids = []
        for role in roles - consumed:
            xmlid = mapping.get(role)
            if not xmlid:
                continue
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
        if group_ids:
            self.sudo().write({"group_ids": [(4, gid) for gid in group_ids]})
            _logger.info("Finance SSO: granted %s groups %s", self.login, group_ids)
        return True
