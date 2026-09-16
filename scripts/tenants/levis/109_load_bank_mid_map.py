"""Load the client's ALL_MID_EBR merchant list into ``levis.bank.mid.map``.

    MID_BANKS=bca,bri RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/109_load_bank_mid_map.py

Dry-run by default (``RUN_DRY=1``). Idempotent: a merchant id the resolver would
already answer for is skipped, never duplicated — the check is the model's own
``_competes_with``, not a string compare, because ``4608375`` and
``885004608375`` are one terminal to the resolver and two strings to an index.

KEY SHAPES — these are what the narratives actually print
--------------------------------------------------------
* BCA  ``KR OTOMATIS MID : 885004776763`` and, on the credit feed,
  ``KARTU KREDIT MID:004776750``. The sheet gives the bare 7 digits, so the key
  is stored as ``88500`` + those digits, matching the 22 rules already loaded;
  the shorter credit form still resolves through the >=6-digit suffix rule.
* BRI  ``OnUs 1 260913 001999682593 LEVIS BALIKPA`` — the sheet's 10 digits with
  a ``00`` pad. Stored bare; the pad is normalised away.
* Mandiri ``7222362514099999999000000000000LEVI'S QM`` — the sheet's 11 digits
  lead the narrative.
* BNI  ``... OTOPAY QR 03/09/26 207903028`` — the sheet's 12 digits minus the
  ``100`` prefix, so a suffix match.

WHY ``MID_BANKS`` DEFAULTS TO ``bca,bri``
-----------------------------------------
``levis.bank.narrative._parse_mandiri`` and ``_parse_bni`` are stubs: they
recognise fee rows and nothing else, so they never hand the resolver a ``mid``.
Loading Mandiri/BNI rules today is harmless but INERT — they cannot fire until
those two parsers learn their settlement grammar. Pass
``MID_BANKS=bca,bri,mandiri,bni`` to stage them anyway, with eyes open.

Source: ALL_MID_EBR.xlsx, supplied by the client 2026-09-16. Kept inline rather
than read from the file so the rules that were loaded stay reviewable in git.
"""

import os

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")
BANKS = [b.strip().lower() for b in (os.environ.get("MID_BANKS") or "bca,bri").split(",") if b.strip()]

# (bank key in the table, journal code, match_type, key builder, channel)
BANK_SPECS = {
    "bca": ("IBCA", "mid", lambda v: "88500" + v, "debit"),
    "bri": ("IBRI", "tid", lambda v: v, "debit"),
    "mandiri": ("IMand", "mid", lambda v: v, "qris"),
    "bni": ("IBNI", "mid", lambda v: v, "qris"),
}

STORES = [
    {
        "code": "80440",
        "name": "OLS SES - AEON BSD CITY",
        "bca": "4648627",
        "bri": "1999664886",
        "mandiri": "72139322401",
        "bni": "100214911003",
    },
    {
        "code": "80130",
        "name": "OLS SES - BANDUNG INDAH PLAZA",
        "bca": "4632695",
        "bri": "1999660757",
        "mandiri": "72133022533",
        "bni": "100204905850",
    },
    {
        "code": "80437",
        "name": "OLS SES - CENTRAL PARK",
        "bca": "4608399",
        "bri": "1999632293",
        "mandiri": "72120410918",
        "bni": "100212904216",
    },
    {
        "code": "80444",
        "name": "OLS SES - GALAXY MALL 3",
        "bca": "4632679",
        "bri": "1999660763",
        "mandiri": "72133022161",
        "bni": "100206903645",
    },
    {
        "code": "80449",
        "name": "OLS SES - GANDARIA CITY",
        "bca": "4648615",
        "bri": "1999664883",
        "mandiri": "72139328122",
        "bni": "100210905657",
    },
    {
        "code": "80435",
        "name": "OLS SES - GRAND INDONESIA",
        "bca": "4608375",
        "bri": "1999632287",
        "mandiri": "72146857866",
        "bni": "100210905551",
    },
    {
        "code": "80439",
        "name": "OLS SES - GRAND METROPOLITAN BEKASI",
        "bca": "4648631",
        "bri": "1999664887",
        "mandiri": "72139328594",
        "bni": "100215907048",
    },
    {
        "code": "80433",
        "name": "OLS SES - KELAPA GADING MALL",
        "bca": "4608383",
        "bri": "1999632292",
        "mandiri": "72121374508",
        "bni": "100215907011",
    },
    {
        "code": "80438",
        "name": "OLS SES - LOTTE SHOPPING AVENUE",
        "bca": "4648619",
        "bri": "1999664884",
        "mandiri": "72139328215",
        "bni": "100210905658",
    },
    {
        "code": "80446",
        "name": "OLS SES - MALL OF INDONESIA",
        "bca": "4618292",
        "bri": "1999639781",
        "mandiri": "72124924700",
        "bni": "100215907030",
    },
    {
        "code": "80445",
        "name": "OLS SES - METROPOLITAN MALL BEKASI",
        "bca": "4648623",
        "bri": "1999664885",
        "mandiri": "72139328308",
        "bni": "100215907047",
    },
    {
        "code": "80442",
        "name": "OLS SES - PAKUWON MALL SURABAYA",
        "bca": "4632721",
        "bri": "1999660761",
        "mandiri": "72133022068",
        "bni": "100206903644",
    },
    {
        "code": "80441",
        "name": "OLS SES - PARIS VAN JAVA",
        "bca": "4632683",
        "bri": "1999660760",
        "mandiri": "72133022254",
        "bni": "100204905847",
    },
    {
        "code": "80447",
        "name": "OLS SES - PLAZA SENAYAN",
        "bca": "4608403",
        "bri": "1999632291",
        "mandiri": "72121374601",
        "bni": "100210905553",
    },
    {
        "code": "80432",
        "name": "OLS SES - PONDOK INDAH MALL 1",
        "bca": "4608395",
        "bri": "1999632288",
        "mandiri": "72121375131",
        "bni": "100214910962",
    },
    {
        "code": "80431",
        "name": "OLS SES - PONDOK INDAH MALL 2",
        "bca": "4608391",
        "bri": "1999632289",
        "mandiri": "72121375038",
        "bni": "100214910963",
    },
    {
        "code": "80450",
        "name": "OLS SES - SUMMARECON MALL BANDUNG",
        "bca": "4632687",
        "bri": "1999660759",
        "mandiri": "72133022347",
        "bni": "100204905848",
    },
    {
        "code": "80434",
        "name": "OLS SES - SENAYAN CITY",
        "bca": "4608387",
        "bri": "1999632290",
        "mandiri": "72121374980",
        "bni": "100210905552",
    },
    {
        "code": "80443",
        "name": "OLS SES - TRANS STUDIO CIBUBUR",
        "bca": "4648635",
        "bri": "1999664888",
        "mandiri": "72139328687",
        "bni": "100214911004",
    },
    {
        "code": "80436",
        "name": "OLS SES - TRANS STUDIO MALL BANDUNG",
        "bca": "4632691",
        "bri": "1999660758",
        "mandiri": "72133022440",
        "bni": "100204905849",
    },
    {
        "code": "80129",
        "name": "OLS SES - TUNJUNGAN PLAZA 3",
        "bca": "4632717",
        "bri": "1999660762",
        "mandiri": "72133021910",
        "bni": "72133367965",
    },
    {
        "code": "80448",
        "name": "OLS SES - PASKAL BANDUNG",
        "bca": "4704536",
        "bri": "1999675383",
        "mandiri": "72174692129",
        "bni": "72176227878",
    },
    {
        "code": "80680",
        "name": "OLS SES - DR RATULANGI MAKASSAR",
        "bca": "4776742",
        "bri": "1999682591",
        "mandiri": "72223624331",
        "bni": "",
    },
    {
        "code": "80741",
        "name": "OLS SES - BALIKPAPAN SUPERBLOCK",
        "bca": "4776750",
        "bri": "1999682593",
        "mandiri": "72223624896",
        "bni": "100209904507",
    },
    {
        "code": "80742",
        "name": "OLS SES - BIG MALL SAMARINDA",
        "bca": "4776755",
        "bri": "1999682594",
        "mandiri": "72223624989",
        "bni": "100209904508",
    },
    {
        "code": "80743",
        "name": "OLS SES - DUTA MALL BANJARMASIN",
        "bca": "4776759",
        "bri": "1999682595",
        "mandiri": "72223625047",
        "bni": "100209904509",
    },
    {
        "code": "80744",
        "name": "OLS SES - MANADO TOWN SQUARE",
        "bca": "4776746",
        "bri": "1999682592",
        "mandiri": "72223624703",
        "bni": "100211902409",
    },
    {
        "code": "80745",
        "name": "OLS SES - Q MALL BANJARBARU",
        "bca": "4776763",
        "bri": "1999682596",
        "mandiri": "72223625140",
        "bni": "100209904510",
    },
    {
        "code": "80746",
        "name": "OLS SES - TRANS STUDIO MAKASSAR",
        "bca": "4776479",
        "bri": "1999682589",
        "mandiri": "72223624424",
        "bni": "100207903027",
    },
    {
        "code": "80747",
        "name": "OLS SES - THE PARK KENDARI",
        "bca": "4776483",
        "bri": "1999682590",
        "mandiri": "72223624517",
        "bni": "100207903028",
    },
    {
        "code": "80748",
        "name": "OLS SES - MALL PANAKKUKANG",
        "bca": "4776475",
        "bri": "1999682587",
        "mandiri": "72223624331",
        "bni": "100207903026",
    },
]

env = env  # noqa: F821  injected by `odoo shell`

Map = env["levis.bank.mid.map"]
Warehouse = env["stock.warehouse"].with_context(active_test=False)
Journal = env["account.journal"]
company = env.company

print("=" * 96)
print("levis.bank.mid.map loader — %s | banks: %s" % ("DRY RUN (rolled back)" if DRY else "COMMIT", ", ".join(BANKS)))
print("=" * 96)

# ---------------------------------------------------------------- guard 1: the sheet against itself
seen = {}
conflicted = set()
for spec in STORES:
    for bank in BANKS:
        raw = spec.get(bank)
        if not raw:
            continue
        key = Map._normalise_key(BANK_SPECS[bank][2](raw))
        owner = seen.get((bank, key))
        if owner and owner != spec["code"]:
            conflicted.add((bank, key))
            print("CONFLICT  %-8s %-14s dipakai DUA toko: %s dan %s" % (bank.upper(), key, owner, spec["code"]))
        seen[(bank, key)] = spec["code"]
if conflicted:
    print("          -> baris ini DILEWATI sampai klien menegaskan pemiliknya.\n")

# ---------------------------------------------------------------- load
made = skipped = missing = blocked = 0


def _store(code):
    """The warehouse for an X24 STORE CODE.

    ``l10n_store_code`` is the field that holds it — the 22 stores that predate
    the SES renumbering still carry their LEGACY XStore number in
    ``stock.warehouse.code`` (14696, 33267), so matching on that finds only the
    nine newest stores and silently reports the rest as absent.
    """
    wh = Warehouse.search([("l10n_store_code", "=", code), ("company_id", "=", company.id)], limit=1)
    return wh or Warehouse.search([("code", "=", code), ("company_id", "=", company.id)], limit=1)


for spec in STORES:
    wh = _store(spec["code"])
    analytic = wh.l10n_ou_analytic_id
    if not analytic:
        print("SKIP      toko %-6s %-34s tidak ada di Odoo" % (spec["code"], spec["name"][:34]))
        missing += 1
        continue
    short = spec["name"].replace("OLS SES - ", "")
    for bank in BANKS:
        raw = spec.get(bank)
        journal_code, match_type, build, channel = BANK_SPECS[bank]
        if not raw:
            print("GAP       %-6s %-30s %-8s tidak ada nomor di sheet" % (spec["code"], short[:30], bank.upper()))
            missing += 1
            continue
        key = build(raw)
        if (bank, Map._normalise_key(key)) in conflicted:
            blocked += 1
            continue
        journal = Journal.search([("code", "=", journal_code), ("company_id", "=", company.id)], limit=1)
        candidate = Map.new(
            {
                "name": "%s (%s)" % (short, bank.upper()),
                "company_id": company.id,
                "match_type": match_type,
                "key": key,
                "analytic_account_id": analytic.id,
                "warehouse_id": wh.id,
                "channel": channel,
            }
        )
        # The resolver's own notion of "same terminal", so 4608375 does not get
        # loaded a second time as 885004608375.
        existing = Map.search([("company_id", "=", company.id), ("match_type", "=", match_type)]).filtered(
            lambda other: candidate._competes_with(other)
        )
        if existing:
            hit = existing[0]
            flag = (
                "" if hit.analytic_account_id == analytic else "  !! menunjuk %s" % hit.analytic_account_id.display_name
            )
            print(
                "ada       %-6s %-30s %-8s %-14s -> rule %s%s"
                % (spec["code"], short[:30], bank.upper(), key, hit.id, flag)
            )
            skipped += 1
            continue
        rec = Map.create(
            {
                "name": "%s (%s)" % (short, bank.upper()),
                "company_id": company.id,
                "journal_id": journal.id or False,
                "match_type": match_type,
                "key": key,
                "analytic_account_id": analytic.id,
                "warehouse_id": wh.id,
                "channel": channel,
                "note": "ALL_MID_EBR.xlsx 16-Sep-2026",
            }
        )
        print(
            "BUAT      %-6s %-30s %-8s %-14s -> rule %s (%s)"
            % (spec["code"], short[:30], bank.upper(), key, rec.id, journal.code or "semua feed")
        )
        made += 1

print("-" * 96)
print(
    "dibuat=%d  sudah ada=%d  tanpa nomor/toko=%d  diblokir konflik=%d  total rule=%d"
    % (made, skipped, missing, blocked, Map.search_count([]))
)

if DRY:
    env.cr.rollback()
    print("DRY RUN — dibatalkan. Jalankan ulang dengan RUN_DRY=0 untuk menyimpan.")
else:
    env.cr.commit()
    print("COMMITTED.")
