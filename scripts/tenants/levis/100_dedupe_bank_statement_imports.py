"""Remove bank statement lines a later import wrote a second time.

August 2026 on prd_levis_begbal: the IBCA statement was imported four times, each
file restarting at the 1st, cumulatively.

    2026-08-07 08:51   386 lines   01-06 Aug
    2026-08-12 03:39   717 lines   01-11 Aug
    2026-08-14 03:34   840 lines   01-13 Aug
    2026-08-19 03:07 1.202 lines   01-18 Aug

3.145 posted rows where 1.202 are real. The bank moved the money once, so the
extra 1.943 rows are journal entries against sales that never happened: IBCA's
August turnover reads Rp 20,98 M instead of ~Rp 8 M and the month's net is out by
Rp 940.983. Everything downstream inherits it — the clearing run reported Rp 10,3 m
of settlements with no receivable left, which was true of the duplicates and
useless as a finding.

    LEVIS_DEDUPE_APPLY=1 docker exec -i odoo19-platform-odoo \
        odoo shell -d prd_levis_begbal --no-http < 100_dedupe_bank_statement_imports.py

Without ``LEVIS_DEDUPE_APPLY=1`` it reports and rolls back. Scope it with
``LEVIS_DEDUPE_JOURNAL`` (default IBCA), ``LEVIS_DEDUPE_FROM`` / ``_TO``
(default 2026-08-01 / 2026-08-31).

**THIS DELETES POSTED ACCOUNTING. Dump the database first** — see
docs/runbooks/backup-restore.md. There is no undo but a restore.

What it will not do, deliberately:

* It keeps the FIRST row of each group and deletes only rows written at least an
  hour later. Two genuine sales can agree on journal, date, narrative and amount;
  rows from one import cannot be an hour apart. Same rule as
  ``levis.pos.clearing._duplicate_groups``, so the readiness check and this script
  can never disagree about what a duplicate is.
* It refuses any row that is reconciled, claimed by a clearing run, or carrying a
  leg that is not the plain Dr bank / Cr suspense pair. A duplicate somebody has
  since worked on is a decision, not a mechanical deletion, and it is listed for a
  person instead.
"""

import os
from collections import defaultdict

env = env  # noqa: F821  (injected by `odoo shell`)

APPLY = os.environ.get("LEVIS_DEDUPE_APPLY") == "1"
CODE = os.environ.get("LEVIS_DEDUPE_JOURNAL", "IBCA")
DATE_FROM = os.environ.get("LEVIS_DEDUPE_FROM", "2026-08-01")
DATE_TO = os.environ.get("LEVIS_DEDUPE_TO", "2026-08-31")
GAP_SECONDS = 3600

tag = "APPLY" if APPLY else "DRY"
log = lambda m: print("[%s] %s" % (tag, m))  # noqa: E731

journal = env["account.journal"].search([("code", "=", CODE), ("type", "=", "bank")], limit=1)
if not journal:
    raise SystemExit("no bank journal %s in this database" % CODE)

env["account.bank.statement.line"].flush_model()
env.cr.execute(
    """
    SELECT array_agg(sl.id ORDER BY sl.create_date, sl.id),
           array_agg(EXTRACT(EPOCH FROM sl.create_date) ORDER BY sl.create_date, sl.id),
           sl.amount
      FROM account_bank_statement_line sl
      JOIN account_move mv ON mv.id = sl.move_id
     WHERE sl.journal_id = %s
       AND mv.state = 'posted'
       AND mv.date BETWEEN %s AND %s
     GROUP BY sl.journal_id, mv.date, sl.payment_ref, sl.amount
    HAVING count(*) > 1
    """,
    (journal.id, DATE_FROM, DATE_TO),
)
extra_ids, extra_amount = [], 0.0
for ids, stamps, amount in env.cr.fetchall():
    later = [line_id for line_id, stamp in zip(ids, stamps) if stamp - stamps[0] >= GAP_SECONDS]
    extra_ids += later
    extra_amount += amount * len(later)

env.cr.execute(
    "SELECT count(*) FROM account_bank_statement_line sl JOIN account_move mv ON mv.id = sl.move_id "
    "WHERE sl.journal_id = %s AND mv.state = 'posted' AND mv.date BETWEEN %s AND %s",
    (journal.id, DATE_FROM, DATE_TO),
)
total = env.cr.fetchone()[0]
log("%s %s..%s: %s posted line(s), %s written by a later import" % (CODE, DATE_FROM, DATE_TO, total, len(extra_ids)))
log("their bank amount totals %s" % round(extra_amount, 2))
if not extra_ids:
    raise SystemExit(0)

lines = env["account.bank.statement.line"].browse(extra_ids)
refused = defaultdict(list)
deletable = env["account.bank.statement.line"]
for line in lines:
    if line.is_reconciled:
        refused["reconciled"].append(line.id)
    elif getattr(line, "levis_clearing_line_id", False):
        refused["claimed by a clearing run"].append(line.id)
    elif len(line.move_id.line_ids) != 2:
        refused["more legs than bank + suspense"].append(line.id)
    else:
        deletable |= line
for reason, ids in refused.items():
    log("REFUSED %s line(s) — %s: %s%s" % (len(ids), reason, ids[:10], " ..." if len(ids) > 10 else ""))
log("%s line(s) are plain duplicates and can go" % len(deletable))

if not APPLY:
    log("dry run — nothing written")
    env.cr.rollback()
    raise SystemExit(0)

moves = deletable.move_id
amls = moves.line_ids
# account_partial_reconcile holds the lines through credit_move_id/debit_move_id,
# so a delete that starts at the move dies on the foreign key.
partials = env["account.partial.reconcile"].search(
    ["|", ("credit_move_id", "in", amls.ids), ("debit_move_id", "in", amls.ids)]
)
log("unwinding %s partial reconcile(s) first" % len(partials))
partials.unlink()
moves.button_draft()
deletable.unlink()
moves.exists().unlink()
log("deleted %s statement line(s) and their entries" % len(extra_ids))
env.cr.commit()
