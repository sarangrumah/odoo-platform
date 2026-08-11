"""Provision the monthly POS clearing on an already-installed database.

``levis.clearing.config`` and the per-journal narrative formats are seeded by the
module ``post_init_hook``, which only runs on a fresh install. Existing Levi's
databases get them from here — the same split as
``scripts/tenants/levis/40_setup_trade_ou.py``.

    CLR_APPLY=1 docker exec -i odoo19-platform-odoo \
        odoo shell -d prd_levis_begbal --no-http < 96_setup_pos_clearing.py

Without ``CLR_APPLY=1`` it reports what it would set and rolls back. Idempotent:
an existing configuration is only topped up where a field is still empty, so a
deliberate manual override is never overwritten.

What it does NOT do is create the MID mapping. That needs a human to say which
store each merchant id belongs to — use the "Map Unmapped Settlements" button on
a clearing run, which lists what is missing for a period, biggest amount first.
"""

import os

env = env  # noqa: F821  (injected by `odoo shell`)

APPLY = os.environ.get("CLR_APPLY") == "1"
tag = "APPLY" if APPLY else "DRY"
log = lambda m: print("[%s] %s" % (tag, m))  # noqa: E731

from odoo.addons.custom_levis_localization.models.setup import (  # noqa: E402
    CLEARING_CODES,
    CLEARING_POSREC_CODES,
    seed_clearing_config,
)

result = seed_clearing_config(env)
log(
    "config created=%(created)s topped_up=%(updated)s journal_formats=%(formats)s" % result
)

for journal in env["account.journal"].search([("type", "=", "bank")], order="code"):
    log(
        "journal %-6s format=%-8s suspense=%s"
        % (
            journal.code,
            journal.levis_clearing_format or "(none)",
            journal.suspense_account_id.code or "(none)",
        )
    )

missing = []
for config in env["levis.clearing.config"].search([]):
    company = config.company_id
    log("company %s -> journal %s" % (company.name, config.journal_id.code or "(none)"))
    for field in CLEARING_CODES:
        account = config[field]
        log("  %-24s %s" % (field, account.code or "(EMPTY)"))
        if not account:
            missing.append("%s.%s (code %s)" % (company.name, field, CLEARING_CODES[field]))
    found = set(config.pos_receivable_account_ids.mapped("code"))
    log("  pos_receivable_accounts   %d of %d" % (len(found), len(CLEARING_POSREC_CODES)))
    absent = [code for code in CLEARING_POSREC_CODES if code not in found]
    if absent:
        log("  MISSING tender accounts:   %s" % ", ".join(absent))
        missing.append("%s: tender accounts %s" % (company.name, ", ".join(absent)))
    log("  bank_journals             %s" % ", ".join(config.bank_journal_ids.mapped("code")) or "(none)")
    unparsed = config.bank_journal_ids.filtered(
        lambda j: j.levis_clearing_format in (False, "none")
    )
    if unparsed:
        log("  WARNING no narrative format: %s" % ", ".join(unparsed.mapped("code")))

    mapped = env["levis.bank.mid.map"].search_count([("company_id", "=", company.id)])
    log("  mid_mapping_rules         %d" % mapped)
    if not mapped:
        log("  -> run the \"Map Unmapped Settlements\" wizard before the first clearing")

if missing:
    log("INCOMPLETE — the clearing will refuse to run until these are set:")
    for item in missing:
        log("  * %s" % item)

if APPLY:
    env.cr.commit()
    log("committed")
else:
    env.cr.rollback()
    log("rolled back — set CLR_APPLY=1 to keep the changes")
