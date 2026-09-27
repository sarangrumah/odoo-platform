"""Give every store the short name the EBR workbook calls it by.

    docker exec -i <odoo container> odoo shell -c /etc/odoo/odoo.conf -d <db> \
        < scripts/tenants/levis/125_seed_ebr_store_labels.py

The ``REMARKS`` column of the recon export reads ``BIP CEK (BCA)`` — the label
Finance has always written, which exists in no Odoo field and cannot be derived:
the warehouse code is a number (34885) and the store name is the full mall name.
So ``stock.warehouse.levis_ebr_label`` holds it, and this seeds it once from the
mapping read out of the client's own August-2026 workbook (the store code and the
remark sit on the same statement row, so the pairing is theirs, not a guess).

Idempotent, and it never overwrites a label somebody has already set by hand.
Stores that are not in the table are left empty rather than given an invented
short name — an empty label falls back to the store code, which is at least a
number Finance keys on.
"""

# store code -> the short name the workbook writes, majority vote over every
# statement row of August 2026 (two single-row typos in their file discarded:
# 80437 appeared once as "PIM 1" against 101 "CP", 80447 once against 105 "PS").
LABELS = {
    "80129": "TP3",
    "80130": "BIP",
    "80431": "PIM 2",
    "80432": "PIM 1",
    "80433": "MKG",
    "80434": "SENCY",
    "80435": "GI",
    "80436": "TSM BANDUNG",
    "80437": "CP",
    "80438": "LOTTE",
    "80439": "GMB",
    "80440": "AEON",
    "80441": "PVJ",
    "80442": "PKWN",
    "80443": "TSM CIBUBUR",
    "80444": "GALAXY",
    "80445": "MMB",
    "80446": "MOI",
    "80447": "PS",
    "80448": "PASKAL",
    "80449": "GANCIT",
    "80450": "SMB",
    "80748": "PANAKKUKANG",
}

warehouses = env["stock.warehouse"].search([("l10n_store_code", "in", list(LABELS))])
by_code = {warehouse.l10n_store_code: warehouse for warehouse in warehouses}

set_now = kept = 0
for code, label in sorted(LABELS.items()):
    warehouse = by_code.get(code)
    if not warehouse:
        print("  no warehouse for store code %s (%s)" % (code, label))
        continue
    if warehouse.levis_ebr_label:
        kept += 1
        if warehouse.levis_ebr_label != label:
            print("  %s already labelled %r, workbook says %r — left alone" % (code, warehouse.levis_ebr_label, label))
        continue
    warehouse.levis_ebr_label = label
    set_now += 1

missing = env["stock.warehouse"].search([("l10n_store_code", "!=", False), ("levis_ebr_label", "=", False)])
print("labels set: %d, already set: %d, still without one: %d" % (set_now, kept, len(missing)))
for warehouse in missing:
    print("  %s %s" % (warehouse.l10n_store_code, warehouse.display_name))
env.cr.commit()
