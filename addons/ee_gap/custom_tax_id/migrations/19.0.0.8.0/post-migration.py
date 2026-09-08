# -*- coding: utf-8 -*-
"""Collapse the two NPWP fields onto one number.

``vat`` and ``x_custom_npwp`` were independent columns for the same DJP
identity: the partner form edits ``vat``, every Coretax/e-Faktur export reads
``x_custom_npwp``. A Tax ID corrected on the form therefore left the exports
emitting the stale number. From this version on ``res.partner`` keeps the two
in sync on write; this script aligns what is already stored.

``vat`` wins where both are filled and differ — it is the field operators
actually edit, so it holds the more recent correction.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Partner = env["res.partner"]

    cr.execute(
        """
        SELECT id, vat, x_custom_npwp
          FROM res_partner
         WHERE COALESCE(vat, '') <> '' OR COALESCE(x_custom_npwp, '') <> ''
        """
    )
    fixed = 0
    for pid, vat, npwp in cr.fetchall():
        wanted = Partner._npwp_normalize(vat) or Partner._npwp_normalize(npwp)
        if not wanted or (wanted == vat and wanted == npwp):
            continue
        # write() re-runs the sync and refreshes the stored NPWP-status compute.
        Partner.browse(pid).write({"vat": wanted})
        _logger.info(
            "custom_tax_id: partner %s NPWP aligned (vat=%r, npwp=%r) -> %s",
            pid,
            vat,
            npwp,
            wanted,
        )
        fixed += 1
    _logger.info("custom_tax_id: %s partner(s) had vat/NPWP drift, now aligned", fixed)
