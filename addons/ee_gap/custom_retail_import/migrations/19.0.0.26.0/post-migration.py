# -*- coding: utf-8 -*-
"""Teach the existing store mailbox and profile to decide by content, not filename.

Both data files carry ``noupdate="1"``, so a tenant where these records already
exist never sees the new fields -- and this is exactly the change that must not
be missed, because the records that exist are the ones already fetching mail.

What it fixes, measured on prd_levis_begbal the day the mailbox was switched on:
19 stores mailed 25 attachments in one afternoon, 20 of them genuine X70D
exports, and the glob ``X70D*.xlsx`` staged only 10. The rest arrived as
"Report Sales OLS SES ...", "LAPORAN X70D ...", "3. X70D_..." -- the same export
under whatever name a person felt like typing. A filename cannot carry this
decision; a sheet's header can.

Only records still holding the old filename glob are re-pointed, so a tenant that
deliberately narrowed its own is left alone. Idempotent.

NOT done here: re-staging the attachments already fetched under the old rule.
Their ledger rows are complete and their backups verified, so rewriting them
would be inventing history. The backlog is a file copy from ``backup_dir`` to
``drop_dir``, done once by hand -- see MODULE_KNOWLEDGE.
"""

import logging

_logger = logging.getLogger(__name__)

SIGNATURE = "TRANSNUM,TENDER AMOUNT"


def migrate(cr, version):
    cr.execute(
        """
        UPDATE retail_import_mailbox b
           SET ingest_glob = '*.xlsx',
               ingest_signature = %s,
               ingest_store_check = TRUE
          FROM ir_model_data d
         WHERE d.module = 'custom_retail_import'
           AND d.name = 'mailbox_levis_store_tender'
           AND d.model = 'retail.import.mailbox'
           AND b.id = d.res_id
           AND b.ingest_signature IS NULL
           AND coalesce(b.ingest_glob, '') IN ('', 'X70D*.xlsx')
        """,
        (SIGNATURE,),
    )
    mailboxes = cr.rowcount

    cr.execute(
        """
        UPDATE retail_import_profile p
           SET header_signature = %s
          FROM ir_model_data d
         WHERE d.module = 'custom_retail_import'
           AND d.name = 'profile_levis_x70d_store'
           AND d.model = 'retail.import.profile'
           AND p.id = d.res_id
           AND p.header_signature IS NULL
        """,
        (SIGNATURE,),
    )
    profiles = cr.rowcount

    # Backfill the sender classification for mail already fetched, so the ledger
    # reads consistently instead of showing a blank column for everything older
    # than this upgrade.
    cr.execute(
        """
        UPDATE retail_import_mail_message
           SET sender_kind = CASE
                   WHEN lower(from_addr) LIKE '%%@levi.com%%' THEN 'auto'
                   WHEN lower(from_addr) LIKE '%%levis.%%@erajaya.com%%' THEN 'store'
                   ELSE 'person' END
         WHERE sender_kind IS NULL
           AND from_addr IS NOT NULL
        """
    )
    labelled = cr.rowcount

    _logger.info(
        "custom_retail_import 19.0.0.26.0: %s mailbox(es) and %s profile(s) now decide by "
        "content; %s ledger row(s) labelled by sender.",
        mailboxes,
        profiles,
        labelled,
    )
