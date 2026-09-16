"""Add new Levi's stores — Operating Unit plus every record that hangs off one.

    RUN_DRY=0 docker exec -i odoo19-platform-odoo-mgmt odoo shell \
        -d prd_levis_begbal --no-http < scripts/tenants/levis/108_add_stores.py

Dry-run by default (``RUN_DRY=1``): prints the plan and rolls back. Idempotent —
a second run with the same STORES table writes nothing.

WHAT A "STORE" IS MADE OF HERE
------------------------------
A Levi's store is not one record. Adding one means creating, in this order:

  1. ``stock.warehouse``            — core cascades locations, picking types,
     routes, rules and the 9 sequences.
  2. ``account.account`` + ``account.journal`` (cash) — a DEDICATED cash account
     at the next free ``1102`` code. Never let ``point_of_sale`` pick a default:
     it walks the 1102 block and collides with EBR's own cash accounts
     (that is the bug ``44_fix_cash_journal_accounts.py`` had to undo).
  3. ``pos.payment.method`` "CASH"  — one per store, pointing at (2).
  4. ``pos.config``                 — cloned field-by-field from a live store,
     plus every shared tender method so X24 orders can be paid.
  5. ``account.analytic.account``   — the Operating Unit dimension (plan
     "Operating Unit"), linked via ``warehouse.l10n_ou_analytic_id``.
  6. ``account.journal`` (purchase) — "Pembelian - <store>", linked via
     ``warehouse.l10n_purchase_journal_id``.
  7. ``operating.unit``             — via the bridge's idempotent migration, so
     the unit is wired to warehouse + analytic + purchase journal + cash journal
     exactly like the existing 23, plus the client's postal address.
  8. ``ir.model.data`` ``posconfig_<STORE CODE>`` — the key the X24DN/X70D
     import joins on. Written explicitly rather than left to the importer's
     name-based auto-map.
  9. ``petty.cash.float``           — one per Operating Unit, at the tenant plafon.

The cash journal is created BEFORE the purchase journal on purpose: both want a
5-character code derived from the store code, and the existing 23 stores have
cash=``14696`` / purchase=``14691``. Creating them the other way round would
invert that everywhere.

STORE CODE vs SHIP-TO CODE
--------------------------
The X24DN file carries both: ``STORE CODE`` (5 digits, e.g. 80741) and
``SAP STORE CODE`` (the 10-digit ship-to, e.g. 0020080741). The importer keys on
STORE CODE, and that is what goes into ``stock.warehouse.code`` and
``operating.unit.code`` here — never change it afterwards.

The 23 existing stores carry LEGACY XStore numbers (14696, 33267…) from the
pre-SES store master; new stores have no such number, so their warehouse code is
the current STORE CODE. That also makes warehouse code == posconfig code, which
is one fewer thing to look up.
"""

import os

DRY = os.environ.get("RUN_DRY", "1") not in ("0", "false", "False")

# The pos.config whose settings every new store copies (a live SES store).
TEMPLATE_WH_CODE = "33267"  # OLS SES - PASKAL BANDUNG

CASH_CODE_BLOCK = "1102"  # EBR cash-on-hand block

# store code -> everything the client gave us.
# ``ship_to`` is kept for traceability only; the importer never uses it.
STORES = [
    {
        "code": "80680",
        "ship_to": "0020080680",
        "name": "OLS SES - DR RATULANGI MAKASSAR",
        "street": "Jl. DR. Ratulangi RT.06 RW 04",
        "street2": "Dr Ratulangi Makassar - No.62, Kunjung Mae, Mariso",
        "city": "Makassar",
        "state": "Sulawesi Selatan",
        "zip": "90125",
    },
    {
        "code": "80741",
        "ship_to": "0020080741",
        "name": "OLS SES - BALIKPAPAN SUPERBLOCK",
        "street": "Jl. Jendral Sudirman No. 47",
        "street2": "Balikpapan Superblock - Lt.UG-27",
        "city": "Balikpapan",
        "state": "Kalimantan Timur",
        "zip": "76114",
    },
    {
        "code": "80742",
        "ship_to": "0020080742",
        "name": "OLS SES - BIG MALL SAMARINDA",
        "street": "Jl. Untung Suropati No.8",
        "street2": "Big Mall Samarinda - Lt UG-35, Sungai Kunjang",
        "city": "Samarinda",
        "state": "Kalimantan Timur",
        "zip": "75125",
    },
    {
        "code": "80743",
        "ship_to": "0020080743",
        "name": "OLS SES - DUTA MALL BANJARMASIN",
        "street": "Jl. A.Yani KM.2 Duta Mall Banjarmasin No 17 - 19",
        "street2": "Duta Mall Banjarmasin - Lt.2 Blok C No.17-19, Banjarmasin Selatan",
        "city": "Banjarmasin",
        "state": "Kalimantan Selatan",
        "zip": "70241",
    },
    {
        "code": "80744",
        "ship_to": "0020080744",
        "name": "OLS SES - MANADO TOWN SQUARE",
        "street": "Jl. Piere Tendean/Boulevard",
        "street2": "Manado Town Square 2 - Lt. GF, Wanea",
        "city": "Manado",
        "state": "Sulawesi Utara",
        "zip": "95112",
    },
    {
        "code": "80745",
        "ship_to": "0020080745",
        "name": "OLS SES - Q MALL BANJARBARU",
        "street": "Jl. A Yani Km.36,8",
        "street2": "Q Mall Banjarbaru - Lt.UG No.46, Komet",
        "city": "Banjarbaru",
        "state": "Kalimantan Selatan",
        "zip": "70714",
    },
    {
        "code": "80746",
        "ship_to": "0020080746",
        "name": "OLS SES - TRANS STUDIO MAKASSAR",
        "street": "Jl. Hm Dg. Patompo",
        "street2": "Trans Studio Makassar - Lt.1 Unit I-18, Metro Tanjung Bunga",
        "city": "Makassar",
        "state": "Sulawesi Selatan",
        "zip": "90134",
    },
    {
        "code": "80747",
        "ship_to": "0020080747",
        "name": "OLS SES - THE PARK KENDARI",
        "street": "Jl. Brigjend M Yoenoes",
        "street2": "The Park Kendari - Lt. GF-0070, Bende",
        "city": "Kendari",
        "state": "Sulawesi Tenggara",
        "zip": "93232",
    },
    {
        "code": "80748",
        "ship_to": "0020080748",
        "name": "OLS SES - MALL PANAKKUKANG",
        "street": "Jl. Boulevard Komp. Panakukang Mas No 15",
        "street2": "Panakukang Mas Gedung Blt.1 Unit BE-2, Panakukang",
        "city": "Makassar",
        "state": "Sulawesi Selatan",
        "zip": "90231",
    },
]

# pos.config settings copied from the template store. Everything else keeps the
# Odoo default: these are the only fields the Levi's stores actually differ on.
CONFIG_COPY_FIELDS = (
    "journal_id",
    "invoice_journal_id",
    "pricelist_id",
    "use_pricelist",
    "iface_tax_included",
    "rounding_method",
    "cash_rounding",
    "only_round_cash_method",
    "picking_policy",
    "iface_print_skip_screen",
    "manual_discount",
    "auto_validate_terminal_payment",
    "show_product_images",
    "show_category_images",
    "limit_categories",
)

# x2many pos.config settings copied from the template (``pricelist_id`` is
# refused unless it is also in ``available_pricelist_ids``).
CONFIG_COPY_M2M = ("available_pricelist_ids",)

env = env  # noqa: F821  injected by `odoo shell`
log = []


def say(line):
    log.append(line)
    print(line)


def _wh(code):
    return env["stock.warehouse"].with_context(active_test=False).search([("code", "=", code)], limit=1)


def _next_cash_code(company):
    """First unused account code in the 1102 block (codes are company-dependent)."""
    Account = env["account.account"].with_company(company)
    used = set()
    for acc in Account.with_context(active_test=False).search([("code", "=like", CASH_CODE_BLOCK + "%")]):
        used.add(acc.with_company(company).code)
    n = 1
    while True:
        code = "%s%06d" % (CASH_CODE_BLOCK, n)
        if code not in used:
            return code
        n += 1
        if n > 999999:
            raise RuntimeError("no free account code in the %s block" % CASH_CODE_BLOCK)


def _unique_journal_code(company, base):
    """A free <=5-char journal code near ``base``.

    ``custom_levis_localization``'s own helper keeps only ``base[:4]`` and appends
    ``n``, so from n=10 it re-emits the same five characters forever — with nine
    consecutive store codes in one batch that is an infinite loop. Shrink the
    stem as the counter grows instead.
    """
    Journal = env["account.journal"]

    def taken(code):
        return bool(Journal.search_count([("code", "=", code), ("company_id", "=", company.id)]))

    if not taken(base[:5]):
        return base[:5]
    for n in range(1, 100000):
        suffix = str(n)
        code = (base[: max(0, 5 - len(suffix))] + suffix)[:5]
        if not taken(code):
            return code
    raise RuntimeError("no free journal code near %r" % base)


def _safe_xid(prefix, value):
    return prefix + "".join(c if c.isalnum() else "_" for c in str(value)).upper()


def _xid_get(module, name, model):
    data = env["ir.model.data"].search([("module", "=", module), ("name", "=", name), ("model", "=", model)], limit=1)
    return data.res_id if data else False


def _xid_set(module, name, model, res_id):
    if _xid_get(module, name, model):
        return False
    env["ir.model.data"].create({"module": module, "name": name, "model": model, "res_id": res_id, "noupdate": True})
    return True


# ---------------------------------------------------------------------------
template_wh = _wh(TEMPLATE_WH_CODE)
if not template_wh:
    raise RuntimeError("template warehouse %s not found" % TEMPLATE_WH_CODE)
template_cfg = (
    env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", template_wh.id)], limit=1)
)
if not template_cfg:
    raise RuntimeError("template pos.config for warehouse %s not found" % TEMPLATE_WH_CODE)
company = template_wh.company_id

# Shared (non per-store) tender methods: everything on the template config that
# is not its own cash method.
shared_methods = template_cfg.payment_method_ids.filtered(lambda m: not m.is_cash_count)

say("=" * 78)
say("Add Levi's stores — %s" % ("DRY RUN (rolled back)" if DRY else "COMMIT"))
say("company        : %s (id %s)" % (company.display_name, company.id))
say("template store : %s (pos.config %s)" % (template_wh.name, template_cfg.id))
say("shared tenders : %s" % ", ".join(sorted(shared_methods.mapped("name"))))
say("=" * 78)

# --- 1. warehouses ---------------------------------------------------------
made_wh = []
for spec in STORES:
    wh = _wh(spec["code"])
    if wh:
        say("wh   %-6s exists  %s (id %s)" % (spec["code"], wh.name, wh.id))
        if wh.name != spec["name"]:
            say("     !! name differs from the sheet: %r" % wh.name)
        continue
    wh = env["stock.warehouse"].create({"name": spec["name"], "code": spec["code"], "company_id": company.id})
    made_wh.append(wh)
    say("wh   %-6s CREATE  %s (id %s)" % (spec["code"], wh.name, wh.id))

# --- 2+3+4. cash account, cash journal, CASH method, pos.config ------------
for spec in STORES:
    wh = _wh(spec["code"])
    name = wh.name

    cash_journal = env["account.journal"].search(
        [("type", "=", "cash"), ("company_id", "=", company.id), ("name", "=", "Cash - %s" % name)],
        limit=1,
    )
    if not cash_journal:
        acc_code = _next_cash_code(company)
        account = (
            env["account.account"]
            .with_company(company)
            .create(
                {
                    "name": "Cash - %s" % name,
                    "code": acc_code,
                    "account_type": "asset_cash",
                    "reconcile": False,
                    "company_ids": [(4, company.id)],
                }
            )
        )
        cash_journal = env["account.journal"].create(
            {
                "name": "Cash - %s" % name,
                "type": "cash",
                "code": _unique_journal_code(company, wh.code),
                "company_id": company.id,
                "default_account_id": account.id,
            }
        )
        say("cash %-6s CREATE  journal %s / account %s" % (spec["code"], cash_journal.code, acc_code))
    else:
        say("cash %-6s exists  journal %s (id %s)" % (spec["code"], cash_journal.code, cash_journal.id))

    method = (
        env["pos.payment.method"]
        .with_context(active_test=False)
        .search(
            [("company_id", "=", company.id), ("is_cash_count", "=", True), ("journal_id", "=", cash_journal.id)],
            limit=1,
        )
    )
    if not method:
        method = env["pos.payment.method"].create(
            {"name": "CASH", "company_id": company.id, "journal_id": cash_journal.id, "is_cash_count": True}
        )
        say("meth %-6s CREATE  CASH (id %s)" % (spec["code"], method.id))

    config = env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", wh.id)], limit=1)
    if not config:
        vals = {
            "name": name,
            "company_id": company.id,
            "warehouse_id": wh.id,
            "picking_type_id": wh.pos_type_id.id,
            "payment_method_ids": [(6, 0, (shared_methods | method).ids)],
        }
        for field in CONFIG_COPY_FIELDS:
            value = template_cfg[field]
            vals[field] = value.id if hasattr(value, "id") else value
        for field in CONFIG_COPY_M2M:
            vals[field] = [(6, 0, template_cfg[field].ids)]
        config = env["pos.config"].create(vals)
        say("pos  %-6s CREATE  pos.config %s" % (spec["code"], config.id))
    else:
        missing = (shared_methods | method) - config.payment_method_ids
        if missing:
            config.write({"payment_method_ids": [(4, m.id) for m in missing]})
            say("pos  %-6s +tender %s" % (spec["code"], ", ".join(missing.mapped("name"))))
        else:
            say("pos  %-6s exists  pos.config %s" % (spec["code"], config.id))

# --- 5+6. OU analytic + purchase journal -----------------------------------
# AFTER the cash journal, so the cash journal keeps the bare store code the
# existing 23 stores use and the purchase journal takes the +1 variant — the
# same shape as 14696 (cash) / 14691 (purchase).
#
# Same search/create semantics as ``custom_levis_localization``'s
# ``seed_trade_ou``, deliberately NOT delegated: that function allocates the
# journal code through its own helper, which keeps a 4-character stem and
# appends the counter, so it re-emits the same five characters from n=10 on and
# spins forever once a batch of consecutive store codes has filled 8074x.
plan = env["account.analytic.plan"].search([("name", "=", "Operating Unit")], limit=1)
if not plan:
    raise RuntimeError('no analytic plan named "Operating Unit"')
Analytic = env["account.analytic.account"]
Journal = env["account.journal"]
for spec in STORES:
    wh = _wh(spec["code"])
    name = wh.name

    if not wh.l10n_ou_analytic_id:
        analytic = Analytic.with_context(active_test=False).search(
            [("name", "=", name), ("plan_id", "=", plan.id), ("company_id", "=", company.id)], limit=1
        )
        if analytic:
            say("ana  %-6s reuse   analytic %s" % (spec["code"], analytic.id))
        else:
            analytic = Analytic.create({"name": name, "plan_id": plan.id, "company_id": company.id})
            say("ana  %-6s CREATE  analytic %s" % (spec["code"], analytic.id))
        wh.l10n_ou_analytic_id = analytic.id

    if not wh.l10n_purchase_journal_id:
        journal = Journal.search(
            [("type", "=", "purchase"), ("company_id", "=", company.id), ("name", "=", "Pembelian - %s" % name)],
            limit=1,
        )
        if not journal:
            journal = Journal.create(
                {
                    "name": "Pembelian - %s" % name,
                    "type": "purchase",
                    # "P" + the store's last 4 digits. The stem+counter codes
                    # the localization would hand out here (80749, 80710, …)
                    # read exactly like neighbouring STORE codes, which is a
                    # trap on a batch of consecutive stores.
                    "code": _unique_journal_code(company, "P%s" % wh.code[-4:]),
                    "company_id": company.id,
                }
            )
            say("purc %-6s CREATE  journal %s (%s)" % (spec["code"], journal.id, journal.code))
        else:
            say("purc %-6s reuse   journal %s (%s)" % (spec["code"], journal.id, journal.code))
        wh.l10n_purchase_journal_id = journal.id

# --- 7. operating.unit (delegated, idempotent) -----------------------------
from odoo.addons.custom_levis_operating_unit.models import setup as ou_setup  # noqa: E402

created, existing = ou_setup.migrate_levis_operating_units(env)
say("operating.unit: %d created, %d already present" % (created, existing))

# --- 7b. the address the client supplied, on the unit ----------------------
Partner = env["res.partner"]
country = env["res.country"].search([("code", "=", "ID")], limit=1)
for spec in STORES:
    wh = _wh(spec["code"])
    unit = (
        env["operating.unit"]
        .with_context(active_test=False)
        .search([("code", "=", spec["code"]), ("company_id", "=", company.id)], limit=1)
    )
    if not unit:
        say("ou   %-6s !! no operating.unit" % spec["code"])
        continue
    if unit.partner_id:
        continue
    state = env["res.country.state"].search([("name", "=", spec["state"]), ("country_id", "=", country.id)], limit=1)
    partner = Partner.search([("name", "=", spec["name"]), ("parent_id", "=", company.partner_id.id)], limit=1)
    if not partner:
        partner = Partner.create(
            {
                "name": spec["name"],
                "parent_id": company.partner_id.id,
                "type": "delivery",
                "ref": spec["ship_to"],
                "street": spec["street"],
                "street2": spec["street2"],
                "city": spec["city"],
                "zip": spec["zip"],
                "state_id": state.id or False,
                "country_id": country.id or False,
                "company_id": company.id,
            }
        )
    unit.partner_id = partner.id
    say("ou   %-6s address -> res.partner %s (%s)" % (spec["code"], partner.id, spec["city"]))

# --- 8. posconfig_<STORE CODE> xid (the X24/X70D join key) -----------------
profile = env["retail.import.profile"].search([("file_type", "=", "x24")], limit=1)
ns = profile.namespace if profile else "levis"
for spec in STORES:
    wh = _wh(spec["code"])
    config = env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", wh.id)], limit=1)
    xname = _safe_xid("posconfig_", spec["code"])
    current = _xid_get(ns, xname, "pos.config")
    if current == config.id:
        say("xid  %-6s exists  %s.%s -> %s" % (spec["code"], ns, xname, config.id))
    elif current:
        say("xid  %-6s !! %s.%s already points at pos.config %s" % (spec["code"], ns, xname, current))
    else:
        _xid_set(ns, xname, "pos.config", config.id)
        say("xid  %-6s CREATE  %s.%s -> %s" % (spec["code"], ns, xname, config.id))

# --- 8b. stock.warehouse.l10n_store_code ------------------------------------
# The X24 STORE CODE promoted from the xid onto the warehouse. The cash-deposit
# matcher, the bank matcher and the daily-closing report all read it from there
# (``_levis_store_code_index``), NOT from the xid — a store without it resolves
# to nothing and its bank credits stay unattributed.
from odoo.addons.custom_levis_localization.models.setup import seed_store_codes  # noqa: E402

seed_store_codes(env)
for spec in STORES:
    wh = _wh(spec["code"])
    say("code %-6s l10n_store_code=%s" % (spec["code"], wh.l10n_store_code or "-- KOSONG"))

# --- 9. petty cash float per Operating Unit --------------------------------
if "petty.cash.float" in env:
    Param = env["ir.config_parameter"].sudo()
    plafon = float(Param.get_param("custom_petty_cash.initial_amount") or 1000000)
    Float = env["petty.cash.float"]
    for spec in STORES:
        wh = _wh(spec["code"])
        analytic = wh.l10n_ou_analytic_id
        if not analytic:
            continue
        existing_float = Float.with_context(active_test=False).search(
            [("l10n_ou_analytic_id", "=", analytic.id), ("company_id", "=", company.id)], limit=1
        )
        if existing_float:
            say("pcf  %-6s exists  petty.cash.float %s" % (spec["code"], existing_float.id))
            continue
        rec = Float.create({"company_id": company.id, "l10n_ou_analytic_id": analytic.id, "amount_plafon": plafon})
        say("pcf  %-6s CREATE  petty.cash.float %s (plafon %s)" % (spec["code"], rec.id, f"{plafon:,.0f}"))

# --- verification ----------------------------------------------------------
say("-" * 78)
say("%-6s %-34s %-4s %-4s %-4s %-6s %-6s %-6s" % ("CODE", "NAME", "WH", "OU", "ANA", "PURCH", "CASH", "POS"))
for spec in STORES:
    wh = _wh(spec["code"])
    unit = (
        env["operating.unit"]
        .with_context(active_test=False)
        .search([("code", "=", spec["code"]), ("company_id", "=", company.id)], limit=1)
    )
    config = env["pos.config"].with_context(active_test=False).search([("warehouse_id", "=", wh.id)], limit=1)
    say(
        "%-6s %-34s %-4s %-4s %-4s %-6s %-6s %-6s"
        % (
            spec["code"],
            spec["name"][:34],
            wh.id or "-",
            unit.id or "-",
            wh.l10n_ou_analytic_id.id or "-",
            wh.l10n_purchase_journal_id.id or "-",
            unit.journal_id.id or "-",
            config.id or "-",
        )
    )
say("-" * 78)
say(
    "active operating units: %d | store warehouses: %d | pos.config: %d"
    % (
        env["operating.unit"].search_count([]),
        env["stock.warehouse"].search_count([]),
        env["pos.config"].search_count([]),
    )
)

if DRY:
    env.cr.rollback()
    say("DRY RUN — rolled back. Re-run with RUN_DRY=0 to apply.")
else:
    env.cr.commit()
    say("COMMITTED.")
