# -*- coding: utf-8 -*-
"""Write the event onto named documents, so the backfill can carry it to the ledger.

WHY THIS EXISTS AND WHAT IT IS NOT
----------------------------------
``backfill_event_analytic.py`` tags a journal item when a document already names
its event. It refuses to guess which event a document belongs to, and rightly:
inventing one writes a typo into the chart of accounts, and the same show worded
differently twice would create two analytic accounts for one night.

So the missing step is human: someone who knows the shows says "this order is
that event". This script is that statement, written down and reviewable — an
explicit table of document -> event, nothing inferred. It fills the document's
own event fields and stops. The ledger is then reached by re-running
``backfill_event_analytic.py``, which is the only thing that writes analytic
distribution.

Splitting it that way matters: the mapping is a business decision that belongs in
a reviewable diff, while the propagation is mechanical and already tested.

IT WILL NOT INVENT AN EVENT
---------------------------
The event is named by the analytic account that already exists. The script reads
that account's own label back into the document's fields, so the document
resolves to THAT account and no second one can be created. If the account named
below does not exist, the script refuses rather than creating it.

THE MAPPING, AND THE EVIDENCE FOR IT (prd_arkaaim, 8 Sep 2026)
--------------------------------------------------------------
All three point at the Danone show of 07.08.26 (analytic account 11):

* ``INV/ARKA/2026/08/004`` — its Rp 300.000.000 revenue line reads "Lokasi Taman
  Bagawan Bali 07.08.26", which is that show's venue and date. Note the header's
  own show date says 28.08.26: on this database the header date anchors the
  payment term and is NOT a reliable marker of the event, which is why the
  automatic matcher could not use it.
* ``PO/ARKA/2026/08/003`` — note "OPERRATIONAL DRONE SHOW - DANONE BALI";
  Rp 129.200.000, the same amount its bill BILL/2026/08/0001 booked to
  7101007000 Exhibition.
* ``PO/ARKA/2026/08/002`` — note "DANONE - BALI", vendor PT Aero Inovasi Media
  (the sister company), Rp 120.000.000, matching SO/AIM/2026/09/003 which already
  carries the Danone event.

The automatic matcher refused all three because it requires EVERY word of the
event's name to appear in the note, and "BALI DANONE" does not contain
"Nutribaby Royal Plus Launching".

NOT INCLUDED: ``PO/ARKA/2026/08/007`` "AKIRA BACK JAKARTA". That show is not in
the system at all — no sales order, no invoice, no analytic account — so there is
nothing to point it at.

WHY A CUSTOMER INVOICE IS TAGGED DIFFERENTLY
-------------------------------------------
Writing the event onto a **customer invoice** also writes its show date, and for
a company with Show Date enabled that date anchors the payment term: on
INV/ARKA/2026/08/004 it moved the due date of a Rp 166.500.000 receivable from
28.08.26 to 07.08.26, twenty-one days earlier, which would age the invoice
differently for no reason anyone asked for. Measured on a clone before it was
allowed anywhere near production.

Omitting just the show date is not a way out either: the event label is
"<name> - <location> - <dd.mm.yy>", so a document carrying name and location but
no date resolves to a DIFFERENT label — and anything that later resolves it with
create=True would open a second analytic account for the same show.

So a customer invoice is tagged on its journal items directly, exactly what the
backfill would have written, and its header is left alone. Purchase orders have
no such coupling — the show-date anchoring is customer-invoice only — so they
get the event on the document, which is also where a future bill will inherit it
from.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \\
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \\
        --http-port=8987 --gevent-port=8988 < tag_documents_to_event.py

    # then, to carry it into the journal items:
    ... < backfill_event_analytic.py

Defaults to PREVIEW (nothing written). Set COMMIT = True to persist.
"""

# ----- the mapping -------------------------------------------------------
COMMIT = False  # True to persist
EVENT_ANALYTIC_ID = 11  # Danone - Nutribaby Royal Plus Launching - ... - 07.08.26
# (model, document, how)
#   "fields" -> write the event onto the document, and let
#               backfill_event_analytic.py carry it down to the journal items.
#   "lines"  -> tag the journal items directly, touching no header field.
DOCUMENTS = [
    ("account.move", "INV/ARKA/2026/08/004", "lines"),
    ("purchase.order", "PO/ARKA/2026/08/003", "fields"),
    ("purchase.order", "PO/ARKA/2026/08/002", "fields"),
]
# -------------------------------------------------------------------------

env = self.env  # noqa: F821  (provided by odoo shell)

event = env["account.analytic.account"].sudo().browse(EVENT_ANALYTIC_ID).exists()

print("=" * 104)
print("Document -> event mapping — %s   [db=%s]" % ("COMMIT" if COMMIT else "PREVIEW", env.cr.dbname))
print("=" * 104)

if not event or not event.x_custom_event_key:
    raise SystemExit("analytic account %s is not an event account — refusing" % EVENT_ANALYTIC_ID)

# Take the event's fields from a document that ALREADY resolves to this account,
# never by splitting the account's name. The label is "<name> - <location> -
# <date>" and the name itself contains " - " here ("Danone - Nutribaby Royal Plus
# Launching"), so any split of the label puts half the event name into the
# location. Copying a real document keeps name and location as their author
# wrote them, and guarantees the documents resolve to THIS account rather than
# creating a second one.
from odoo.addons.custom_arka_show_date.models.arka_event_mixin import custom_event_key

source = None
for model in ("sale.order", "purchase.order", "account.move"):
    for record in env[model].sudo().search([("x_custom_event_name", "!=", False)]):
        if custom_event_key(record._custom_event_label()) == event.x_custom_event_key:
            source = record
            break
    if source:
        break
if not source:
    raise SystemExit(
        "no document already carries event %s — its name/location split is unknown, refusing to guess"
        % EVENT_ANALYTIC_ID
    )
values = {
    "x_custom_event_name": source.x_custom_event_name,
    "x_custom_event_location": source.x_custom_event_location,
    "x_custom_show_date": event.x_custom_event_show_date,
}
print("fields taken from: %s %s" % (source._name, source.display_name))
print("event   : [%s] %s" % (event.id, event.name or ""))
print(
    "fields  : name=%(x_custom_event_name)r location=%(x_custom_event_location)r show=%(x_custom_show_date)s" % values
)

changed = 0
for model, name_ref, how in DOCUMENTS:
    record = env[model].sudo().search([("name", "=", name_ref)], limit=1)
    if not record:
        print("\n  !! %-16s %-24s NOT FOUND" % (model, name_ref))
        continue

    if how == "lines":
        # Down-payment lines are skipped: they sit on a balance-sheet account
        # where analytic never reaches the P&L per Event.
        lines = record.line_ids.filtered(
            lambda l: l.display_type == "product" and not l.is_downpayment and not l.analytic_distribution
        )
        print(
            "\n  %-16s %-24s state=%s   (tagging %d line(s), header untouched)"
            % (model, name_ref, record.state, len(lines))
        )
        for line in lines:
            print("     line %-6s %-46s %16.2f" % (line.id, (line.name or "").split("\n")[0][:46], -line.balance))
        if lines and COMMIT:
            lines.analytic_distribution = {str(event.id): 100.0}
        changed += len(lines)
        continue
    before = (record.x_custom_event_name, record.x_custom_event_location, record.x_custom_show_date)
    print("\n  %-16s %-24s state=%s" % (model, name_ref, record.state))
    print("     before : %s" % (before,))
    if before == (values["x_custom_event_name"], values["x_custom_event_location"], values["x_custom_show_date"]):
        print("     already carries this event — nothing to do")
        continue
    if before[0]:
        # Never quietly move a document from one event to another.
        print("     !! already carries a DIFFERENT event %r — left alone" % before[0])
        continue
    print(
        "     after  : %s"
        % ((values["x_custom_event_name"], values["x_custom_event_location"], values["x_custom_show_date"]),)
    )
    if COMMIT:
        # A fresh dict per write: account.move.write MUTATES the vals it is given
        # (it injects is_manually_modified), and the next model would then be
        # handed a field it does not have.
        record.write(dict(values))
        resolved = record._custom_event_analytic_account(create=False)
        if resolved != event:
            raise SystemExit(
                "%s resolves to %s, not the intended event — rolling back" % (name_ref, resolved.name or "nothing")
            )
        print("     resolves to [%s] %s" % (resolved.id, resolved.name))
    changed += 1

print("\n" + "=" * 104)
if COMMIT:
    env.cr.commit()
    print("%d document(s) written. NOW RUN backfill_event_analytic.py to reach the journal items." % changed)
else:
    print("%d document(s) would change — set COMMIT = True" % changed)
print("=" * 104)
