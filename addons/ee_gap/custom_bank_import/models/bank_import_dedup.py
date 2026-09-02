# -*- coding: utf-8 -*-
from odoo import fields, models


class BankImportDedup(models.AbstractModel):
    """The per-transaction duplicate guard, shared by every way lines arrive.

    A bank statement reaches this database two ways — an operator uploading a
    file, and an H2H connection fetching a window — and both re-carry
    transactions by their nature. The file hash on ``custom.bank.import.log``
    catches a byte-identical re-upload and nothing else, which is not the shape
    this goes wrong in: four IBCA exports of August 2026 each started at the 1st
    and ran to a later day, so every one was a *different* file carrying every
    earlier transaction again. The hash passed each time and 1.943 duplicate
    statement lines were posted — 3.145 rows where 1.202 were real, and the bank
    GL out by 940.983.

    So the guard is per transaction, and it is deliberately a **count
    difference** rather than "key exists -> skip": two genuine sales can be
    identical — same store, same price, same day, same memo — and dropping the
    second would lose real money as surely as importing it twice invents it.

        create = max(0, times the key appears in the feed
                        - times it already exists in the database)

    A full re-import therefore creates nothing; a feed that genuinely holds two
    twins where the database has one creates exactly one.

    The key matches ``levis.pos.clearing._duplicate_groups`` on purpose, so the
    importer and the clearing's readiness gate cannot disagree about what a
    duplicate is. Inheritors must carry a ``journal_id``.
    """

    _name = "custom.bank.import.dedup"
    _description = "Bank Import Duplicate Guard"

    _DEDUP_PRECISION = 2

    def _dedup_key(self, date, payment_ref, amount):
        """The identity of one bank transaction, as every side must see it.

        The date is normalised because the feeds disagree about its type: an H2H
        payload carries ``"2026-05-01"``, a parsed CSV row carries a ``date``, and
        the database returns a ``date``. Comparing those raw makes every key
        unique and the guard silently useless — which is exactly how it first
        failed here.
        """
        return (
            fields.Date.to_date(date) if date else False,
            (payment_ref or "")[:255],
            round(float(amount or 0.0), self._DEDUP_PRECISION),
        )

    def _existing_line_counts(self, dates):
        """How many times each key is already on this journal, in this range.

        Scoped to the journal and the feed's own date span: a statement says
        nothing about days it does not cover, and widening the search would make
        a large history expensive for no gain.
        """
        self.ensure_one()
        counts = {}
        if not dates:
            return counts
        existing = self.env["account.bank.statement.line"].search(
            [
                ("journal_id", "=", self.journal_id.id),
                ("date", ">=", min(dates)),
                ("date", "<=", max(dates)),
            ]
        )
        for line in existing:
            key = self._dedup_key(line.date, line.payment_ref, line.amount)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _split_already_imported(self, keyed_rows):
        """``(fresh, duplicates)`` out of ``[(key, row)]``, keeping feed order.

        The rows are whatever the caller wants back — this decides which of them
        the journal already holds, and nothing else.
        """
        self.ensure_one()
        already = self._existing_line_counts([key[0] for key, _row in keyed_rows])
        seen = {}
        fresh, duplicates = [], []
        for key, row in keyed_rows:
            seen[key] = seen.get(key, 0) + 1
            if seen[key] <= already.get(key, 0):
                duplicates.append(row)
            else:
                fresh.append(row)
        return fresh, duplicates
