# -*- coding: utf-8 -*-
"""Create the Giro / Bank Transfer payment methods, skipping any that exist.

``account.payment.method`` is unique on ``(code, payment_type)`` and Levi's
databases already own these four records through
``custom_levis_localization``. Creating them from a hook instead of a data file
is what lets both modules live on the same database.
"""

import logging

_logger = logging.getLogger(__name__)

METHODS = (
    ("Giro", "giro", "inbound"),
    ("Giro", "giro", "outbound"),
    ("Bank Transfer", "bank_transfer", "inbound"),
    ("Bank Transfer", "bank_transfer", "outbound"),
)


def post_init_hook(env):
    Method = env["account.payment.method"].sudo()
    created = []
    for name, code, payment_type in METHODS:
        if Method.search_count([("code", "=", code), ("payment_type", "=", payment_type)]):
            continue
        Method.create({"name": name, "code": code, "payment_type": payment_type})
        created.append("%s/%s" % (code, payment_type))
    if created:
        _logger.info("custom_payment_methods_id: created payment methods %s", ", ".join(created))
    else:
        _logger.info("custom_payment_methods_id: all payment methods already present")
