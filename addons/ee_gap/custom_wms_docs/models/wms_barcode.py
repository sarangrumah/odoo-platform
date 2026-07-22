# -*- coding: utf-8 -*-
"""Barcode image URL helper.

Barcode images are rendered by the core web route
``/report/barcode/<Type>/<value>`` (``odoo.addons.web.controllers.report``).
Supported symbologies include ``Code128``, ``QR`` and ``datamatrix``; the core
controller silently falls back to ``Code128`` for anything reportlab cannot
draw, so an unknown symbology never breaks a print job.

The value is URL-quoted with ``safe=""`` because product / package references
routinely contain ``/`` (e.g. ``WH/OUT/00007``) and the route uses a
``<path:value>`` converter that would otherwise swallow the slashes.
"""

from __future__ import annotations

from urllib.parse import quote

#: Symbologies offered to the user in the label wizard.
WMS_BARCODE_TYPES = ("Code128", "QR", "datamatrix")


def wms_barcode_url(
    value: str,
    barcode_type: str = "Code128",
    width: int = 600,
    height: int = 100,
    humanreadable: bool = False,
) -> str:
    """Return the ``<img src>`` URL rendering ``value`` as a barcode image.

    :param value: the human readable payload (may be empty → empty string).
    :param barcode_type: ``Code128`` / ``QR`` / ``datamatrix`` / any reportlab type.
    :param width: pixel width requested from the core controller.
    :param height: pixel height requested from the core controller.
    :param humanreadable: render the value underneath the bars.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    return "/report/barcode/%s/%s?width=%s&height=%s&humanreadable=%s" % (
        quote(str(barcode_type or "Code128"), safe=""),
        quote(text, safe=""),
        int(width),
        int(height),
        1 if humanreadable else 0,
    )
