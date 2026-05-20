# -*- coding: utf-8 -*-
"""Landing admin shell routes.

The ``/landing`` family of URLs renders the OWL single-page console.
Every sub-path collapses to the same shell template — the client-side
router decides which OWL component to mount based on ``window.location``.

Auth is ``user`` and an additional admin-group check is delegated to the
client (the OWL bootstrap calls ``ir.model.access.check`` before showing
sensitive panels). For MVP we trust the standard ``base.group_user``
gate — odoo-mgmt itself is firewalled.
"""
from __future__ import annotations

from odoo import http
from odoo.http import request


class LandingAdminController(http.Controller):
    @http.route(
        ["/landing", "/landing/", "/landing/<path:subpath>"],
        type="http",
        auth="user",
        website=False,
        csrf=False,
    )
    def landing_shell(self, subpath: str = "", **_kwargs):
        """Render the OWL shell.

        Any sub-path under ``/landing/...`` returns the same HTML
        document; the client-side router inspects ``location.hash`` (or
        ``location.pathname``) to decide which view to mount.
        """
        values = {
            "subpath": subpath or "",
            "user_name": request.env.user.name,
            "user_login": request.env.user.login,
            "uid": request.env.user.id,
        }
        return request.render(
            "custom_landing_admin.app_root", values
        )
