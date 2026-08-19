# -*- coding: utf-8 -*-
"""Load ``res.currency.rate`` rows for CNY and USD on ARKA-AIM.

WHY
---
On ``prd_arkaaim`` the whole rate table held exactly ONE row (CNY, 2026-07-29,
company 2). Everything else converts at 1.0, silently:

* ``res.currency._convert`` falls back to 1.0 when it finds no rate on or before
  the document date, so a CN¥ 20,000 bill is read as Rp 20,000. This is the
  defect ``custom_arka_fx_header`` warns about in the Register Payment popup
  (``x_fx_rate_missing``) — the warning is a symptom, the empty table is the
  cause.
* The single row carries ``company_id = 2``, so company 1 (PT Aero Inovasi
  Media) sees no CNY rate at all. A rate row with ``company_id = NULL`` is
  shared by every company; per-company rows only make sense when the two
  entities are meant to book different rates for the same day.
* USD is active with ZERO rows. No USD document exists yet, which is exactly
  why now is the cheap moment to seed it.

DIRECTION — read this before touching RATES
-------------------------------------------
Odoo stores ``res.currency.rate.rate`` as *units of the foreign currency per 1
unit of company currency* — with IDR books that is a tiny number
(1 IDR = 0.00037421 CNY). Nobody quotes rates that way, and inverting by hand is
how a rate lands 6 orders of magnitude off. So ``RATES`` below is written in the
readable direction, **IDR per 1 unit of foreign currency** (1 CNY = 2,672.30
IDR), and this script does the inversion.

WHICH DATES
-----------
Odoo picks the newest rate whose date is <= the document date. So one row per
rate-change is enough; you do not need a row per day. Seed at least:

* the opening-balance date (2026-05-31) — otherwise anything backdated to the
  opening period converts at 1.0;
* every date a foreign-currency document is dated (today: 2026-07-27, the two
  CN¥ bills BILL/2026/07/0002 and /0003, 95,000 CNY together);
* the current period, so new documents do not inherit a stale rate.

SOURCE
------
Pick ONE and stay with it — mixing sources inside a period makes the FX
gain/loss unauditable:

* **Kurs Pajak (KMK)** — weekly, mandatory basis for faktur pajak / PPN impor.
* **Kurs tengah BI / JISDOR** — daily, the usual basis for reporting valuation.

Whichever it is, record it in SOURCE_NOTE so the next person knows.

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_arkaaim --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < load_currency_rates.py

Defaults to PREVIEW. Set COMMIT = True to persist. Idempotent: an existing row
for the same (currency, date, company) is updated, never duplicated.
"""

# ----- knobs -------------------------------------------------------------
COMMIT = False

# Where the numbers came from. Printed in the run header.
SOURCE_NOTE = "Kurs Pajak KMK (fiskal.kemenkeu.go.id), KMK 23 s/d 38/MK/EF.2/2026, 27-Mei s/d 25-Agu 2026"

# None  -> one shared row per date, visible to every company (recommended)
# [1,2] -> a separate row per company id
COMPANY_SCOPE = None

# currency -> {date: IDR per 1 unit of that currency}   <-- readable direction
RATES = {
    "CNY": {
        "2026-05-27": 2600.48,  # KMK 23/MK/EF.2/2026
        "2026-06-03": 2627.25,  # KMK 25/MK/EF.2/2026
        "2026-06-10": 2652.06,  # KMK 26/MK/EF.2/2026
        "2026-06-17": 2662.48,  # KMK 27/MK/EF.2/2026
        "2026-06-24": 2626.11,  # KMK 28/MK/EF.2/2026
        "2026-07-01": 2634.29,  # KMK 30/MK/EF.2/2026
        "2026-07-08": 2640.37,  # KMK 31/MK/EF.2/2026
        "2026-07-15": 2652.90,  # KMK 32/MK/EF.2/2026
        "2026-07-22": 2664.80,  # KMK 33/MK/EF.2/2026
        "2026-07-29": 2648.42,  # KMK 34/MK/EF.2/2026
        "2026-08-05": 2671.97,  # KMK 36/MK/EF.2/2026
        "2026-08-12": 2661.06,  # KMK 37/MK/EF.2/2026
        "2026-08-19": 2645.08,  # KMK 38/MK/EF.2/2026
    },
    "USD": {
        "2026-05-27": 17692.00,  # KMK 23/MK/EF.2/2026
        "2026-06-03": 17805.00,  # KMK 25/MK/EF.2/2026
        "2026-06-10": 17968.00,  # KMK 26/MK/EF.2/2026
        "2026-06-17": 18037.00,  # KMK 27/MK/EF.2/2026
        "2026-06-24": 17781.00,  # KMK 28/MK/EF.2/2026
        "2026-07-01": 17910.00,  # KMK 30/MK/EF.2/2026
        "2026-07-08": 17934.00,  # KMK 31/MK/EF.2/2026
        "2026-07-15": 18031.00,  # KMK 32/MK/EF.2/2026
        "2026-07-22": 18056.00,  # KMK 33/MK/EF.2/2026
        "2026-07-29": 17937.00,  # KMK 34/MK/EF.2/2026
        "2026-08-05": 18062.00,  # KMK 36/MK/EF.2/2026
        "2026-08-12": 17960.00,  # KMK 37/MK/EF.2/2026
        "2026-08-19": 17843.00,  # KMK 38/MK/EF.2/2026
    },
}

# A rate row carrying a company_id SHADOWS the shared row for that company. The
# single pre-existing row on prd_arkaaim (CNY, 2026-07-29, company 2, 1 CNY =
# 2,672.30 IDR) is not a KMK figure, so leaving it in place would keep company 2
# on a different rate from company 1 for that week. True = realign it to the KMK
# value; posted documents keep the rate already stored on them either way.
ALIGN_COMPANY_ROWS = False

# Rewrite rows that already exist with a different rate. Off by default: a rate
# that has already been used to post a document is history, not a typo.
OVERWRITE_EXISTING = False

# ----- run ---------------------------------------------------------------
Rate = env["res.currency.rate"]
Currency = env["res.currency"]

print("=" * 72)
print("ARKA-AIM currency rates — %s" % ("COMMIT" if COMMIT else "PREVIEW"))
print("source: %s" % (SOURCE_NOTE or "(not stated — fill SOURCE_NOTE)"))
print("scope : %s" % ("shared (company_id = NULL)" if COMPANY_SCOPE is None else "companies %s" % COMPANY_SCOPE))
print("=" * 72)

companies = [None] if COMPANY_SCOPE is None else list(COMPANY_SCOPE)
created = updated = skipped = 0

for code, by_date in RATES.items():
    if not by_date:
        print("\n%s: nothing to load (RATES empty)" % code)
        continue
    currency = Currency.with_context(active_test=False).search([("name", "=", code)], limit=1)
    if not currency:
        print("\n%s: currency not found — SKIPPED" % code)
        continue
    if not currency.active:
        print("\n%s: currency is ARCHIVED — activate it first, SKIPPED" % code)
        continue
    print("\n%s (id=%s)" % (code, currency.id))
    for date in sorted(by_date):
        idr_per_unit = by_date[date]
        if not idr_per_unit:
            print("  %s  rate is 0/blank — SKIPPED" % date)
            skipped += 1
            continue
        odoo_rate = 1.0 / float(idr_per_unit)
        for cid in companies:
            domain = [("currency_id", "=", currency.id), ("name", "=", date)]
            domain += [("company_id", "=", cid)] if cid else [("company_id", "=", False)]
            existing = Rate.search(domain, limit=1)
            label = "company %s" % cid if cid else "shared"
            if existing:
                same = abs(existing.rate - odoo_rate) < 1e-12
                if same:
                    print("  %s  1 %s = %s IDR  [%s] already correct" % (date, code, f"{idr_per_unit:,.2f}", label))
                    skipped += 1
                elif OVERWRITE_EXISTING:
                    print(
                        "  %s  1 %s = %s IDR  [%s] UPDATE (was 1 %s = %s IDR)"
                        % (
                            date,
                            code,
                            f"{idr_per_unit:,.2f}",
                            label,
                            code,
                            f"{(1.0 / existing.rate) if existing.rate else 0:,.2f}",
                        )
                    )
                    if COMMIT:
                        existing.rate = odoo_rate
                    updated += 1
                else:
                    print(
                        "  %s  [%s] EXISTS with 1 %s = %s IDR — left alone (OVERWRITE_EXISTING=False)"
                        % (date, label, code, f"{(1.0 / existing.rate) if existing.rate else 0:,.2f}")
                    )
                    skipped += 1
                continue
            print("  %s  1 %s = %s IDR  [%s] CREATE" % (date, code, f"{idr_per_unit:,.2f}", label))
            if COMMIT:
                Rate.create(
                    {
                        "currency_id": currency.id,
                        "name": date,
                        "rate": odoo_rate,
                        "company_id": cid or False,
                    }
                )
            created += 1

# ----- company-scoped rows that shadow the shared ones -------------------
print("\n" + "-" * 72)
print("company-scoped rows that override the shared rates above:")
shadow = Rate.search([("company_id", "!=", False)])
if not shadow:
    print("  none")
for row in shadow:
    code = row.currency_id.name
    theirs = (1.0 / row.rate) if row.rate else 0.0
    kmk = RATES.get(code, {}).get(str(row.name))
    verdict = (
        "no KMK row for this date"
        if not kmk
        else ("matches KMK" if abs(theirs - kmk) < 0.005 else "DIFFERS from KMK %s" % f"{kmk:,.2f}")
    )
    print(
        "  %s %s company %s: 1 %s = %s IDR — %s" % (row.name, code, row.company_id.id, code, f"{theirs:,.2f}", verdict)
    )
    if kmk and abs(theirs - kmk) >= 0.005 and ALIGN_COMPANY_ROWS:
        print("    -> realigning to KMK")
        if COMMIT:
            row.rate = 1.0 / kmk
        updated += 1

print("\n" + "-" * 72)
print("created %s, updated %s, skipped %s" % (created, updated, skipped))

if COMMIT:
    env.cr.commit()
    print("COMMITTED")
else:
    env.cr.rollback()
    print("PREVIEW ONLY — nothing written. Set COMMIT = True to persist.")
