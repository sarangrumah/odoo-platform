"""Align every POS-side name with the canonical Operating-Unit naming.

``41_normalize_ou.py`` renamed the warehouse, the Operating-Unit analytic, the
per-store purchase journal and the ``pos.config``. Three layers copied the store
name at seed/import time and were left behind:

  1. the per-store POS **cash journal** (``Cash - OLS SCU - PONDOK INDAH MALL 1``)
     and, where it mirrors the journal, its default account;
  2. every journal's ``check_sequence_id`` name, which embeds the journal name;
  3. the POS **documents** — ``pos.session.name``, ``pos.order.name`` and the
     ``ref``/``memo`` fields the accounting entries copied them into.

Run against the config-only layer first, then the documents::

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/43_align_pos_naming.py

Dry-run by default (``RUN_DRY=1``): prints the plan and rolls back.

Idempotent: every write is guarded by a "does it already match" check, so a
second run is a no-op.

NOT touched, deliberately:

  * ``product.template.name`` — real product names contain the substring
    ``OLS `` (``GRAPHIC CREWNECK TEE TOOLS PEWTER``, ``Original Cut  OLS TS
    SCU``). This is why nothing here matches on ``LIKE '%OLS %'``; renames are
    driven by an explicit per-record old -> new map built from ``pos.config``.
  * ``mail_message.body`` / ``mail_tracking_value`` — chatter is an audit trail
    of what the record was called at the time. Rewriting it would be falsifying
    history.
"""

import os
import sys

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")

# (table, column) pairs that copied a pos.session name into a document field.
SESSION_REF_COLUMNS = [
    ("account_move", "ref"),
    ("account_move_line", "name"),
    ("account_move_line", "ref"),
    ("account_analytic_line", "ref"),
    ("account_payment", "memo"),
]

env = env  # noqa: F821  injected by `odoo shell`
cr = env.cr
log = []
out = sys.stderr


def _rename(record, field, value):
    if not record or record[field] == value:
        return False
    log.append("  %-26s %-5s %s -> %s" % (record._name, record.id, record[field], value))
    record.write({field: value})
    return True


# --------------------------------------------------------------------------
# 1. Cash journals (+ their default account) follow the pos.config name
# --------------------------------------------------------------------------
log.append("== POS cash journals ==")
configs = env["pos.config"].with_context(active_test=False).search([])
for config in configs.sorted("id"):
    for method in config.payment_method_ids.filtered("is_cash_count"):
        journal = method.journal_id
        if not journal:
            continue
        target = "Cash - %s" % config.name
        account = journal.default_account_id
        # Only rename the account when it actually mirrored the journal name.
        # Some stores reuse a shared account ("Cash on hand USD"), which must
        # keep its own name.
        if account and account.name == journal.name:
            _rename(account, "name", target)
        _rename(journal, "name", target)

# --------------------------------------------------------------------------
# 2. Check-number sequences embed the journal name at creation time
# --------------------------------------------------------------------------
log.append("== Check-number sequences ==")
for journal in env["account.journal"].with_context(active_test=False).search([]):
    seq = journal.check_sequence_id
    if seq:
        _rename(seq.sudo(), "name", "%s: Check Number Sequence" % journal.name)

# --------------------------------------------------------------------------
# 3. POS documents
# --------------------------------------------------------------------------
log.append("== POS documents ==")
Session = env["pos.session"].with_context(active_test=False)
sessions = Session.search([])

# old -> new session name, computed BEFORE anything is written, because the
# accounting refs below are matched on the OLD string.
renames = {}
for s in sessions:
    if "/" not in s.name:
        out.write("!! session %s has no '/' suffix: %r\n" % (s.id, s.name))
        continue
    new = "%s/%s" % (s.config_id.name, s.name.rsplit("/", 1)[1])
    if new != s.name:
        renames[s.name] = new

log.append("  %d/%d sessions to rename" % (len(renames), len(sessions)))

# 3a. Documents that embedded a session name. Done first, while the old names
#     are still the ones stored on pos.session.
for old, new in renames.items():
    for table, column in SESSION_REF_COLUMNS:
        cr.execute(
            "UPDATE %s SET %s = replace(%s, %%s, %%s) WHERE %s LIKE %%s" % (table, column, column, column),
            (old, new, "%" + old + "%"),
        )
        if cr.rowcount:
            log.append("  %-22s %-6s %4d rows  (%s)" % (table, column, cr.rowcount, old))

# 3b. pos.session.name  — "<config>/<nnnnn>"
cr.execute(
    """
    UPDATE pos_session s
       SET name = c.name || '/' || split_part(s.name, '/', 2)
      FROM pos_config c
     WHERE c.id = s.config_id
       AND s.name <> c.name || '/' || split_part(s.name, '/', 2)
    """
)
log.append("  pos_session            name   %4d rows" % cr.rowcount)

# 3c. pos.order.name — "<config> - <n>". The tail is the running number; every
#     row was verified to end in " - <digits>", and the config name itself may
#     contain " - ", hence split_part(..., -1).
cr.execute(
    """
    UPDATE pos_order o
       SET name = c.name || ' - ' || split_part(o.name, ' - ', -1)
      FROM pos_session s, pos_config c
     WHERE s.id = o.session_id
       AND c.id = s.config_id
       AND split_part(o.name, ' - ', -1) ~ '^[0-9]+$'
       AND o.name <> c.name || ' - ' || split_part(o.name, ' - ', -1)
    """
)
log.append("  pos_order              name   %4d rows" % cr.rowcount)

cr.execute("SELECT count(*) FROM pos_order WHERE split_part(name, ' - ', -1) !~ '^[0-9]+$'")
odd = cr.fetchone()[0]
if odd:
    out.write("!! %d pos.order names do not end in ' - <digits>' and were skipped\n" % odd)

env.invalidate_all()

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
out.write("\n".join(log) + "\n\n")

cr.execute(
    """
    SELECT 'pos_config',  count(*) FROM pos_config  WHERE name  NOT LIKE 'OLS SES - %' AND name NOT LIKE 'EBR%'
    UNION ALL SELECT 'pos_session',  count(*) FROM pos_session  WHERE name  NOT LIKE 'OLS SES - %'
    UNION ALL SELECT 'pos_order',    count(*) FROM pos_order    WHERE name  NOT LIKE 'OLS SES - %'
    UNION ALL SELECT 'account_journal', count(*) FROM account_journal WHERE name::text LIKE '%OLS %' AND name::text NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'ir_sequence',  count(*) FROM ir_sequence  WHERE name LIKE '%OLS %' AND name NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_move.ref', count(*) FROM account_move WHERE ref LIKE '%OLS %' AND ref NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_move_line.ref', count(*) FROM account_move_line WHERE ref LIKE '%OLS %' AND ref NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_move_line.name', count(*) FROM account_move_line WHERE name LIKE '%OLS %' AND name NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_analytic_line.ref', count(*) FROM account_analytic_line WHERE ref LIKE '%OLS %' AND ref NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_payment.memo', count(*) FROM account_payment WHERE memo LIKE '%OLS %' AND memo NOT LIKE '%OLS SES - %'
    UNION ALL SELECT 'account_account.name', count(*) FROM account_account WHERE name::text LIKE '%Cash - OLS %' AND name::text NOT LIKE '%OLS SES - %'
    """
)
out.write("Residual stale names (expect 0 everywhere):\n")
for label, n in cr.fetchall():
    out.write("  %-28s %d%s\n" % (label, n, "" if n == 0 else "   <-- STILL STALE"))

if DRY:
    cr.rollback()
    out.write("\nDRY RUN — rolled back. Re-run with RUN_DRY=0 to apply.\n")
else:
    cr.commit()
    out.write("\nCOMMITTED.\n")
out.flush()
