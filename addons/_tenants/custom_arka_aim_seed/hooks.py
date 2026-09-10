"""Post-init hook: wire ARKA-AIM CoA into module defaults.

Runs once after this addon installs. Sets:
- Company currency (IDR) and fiscal country (Indonesia)
- Forex gain/loss accounts on company
- Default partner receivable/payable via ir.default
- Default product.category income/expense (and stock if available) on root category
- Default journal accounts for existing cash/bank journals
"""

import logging

_logger = logging.getLogger(__name__)


# Role -> external_id (this module's namespace)
ACCOUNT_REFS = {
    "default_receivable": "custom_arka_aim_seed.account_arka_1106000001",
    "default_payable": "custom_arka_aim_seed.account_arka_2103100001",
    "default_income": "custom_arka_aim_seed.account_arka_5199000000",
    "default_expense": "custom_arka_aim_seed.account_arka_6199000000",
    "stock_input": "custom_arka_aim_seed.account_arka_2103109199",
    "stock_output": "custom_arka_aim_seed.account_arka_2103109199",
    "stock_valuation": "custom_arka_aim_seed.account_arka_1113100099",
    "forex_gain": "custom_arka_aim_seed.account_arka_7607000000",
    "forex_loss": "custom_arka_aim_seed.account_arka_7704000000",
    "default_cash": "custom_arka_aim_seed.account_arka_1102000001",
    "default_bank": "custom_arka_aim_seed.account_arka_1103019300",
}


def _ref(env, xid):
    rec = env.ref(xid, raise_if_not_found=False)
    if not rec:
        _logger.warning("ARKA seed: missing external id %s", xid)
    return rec


def post_init_hook(env):
    company = env.ref("base.main_company", raise_if_not_found=False)
    if not company:
        _logger.warning("ARKA seed: base.main_company not found, skipping wiring")
        return

    accounts = {role: _ref(env, xid) for role, xid in ACCOUNT_REFS.items()}

    # 1. Company-level
    idr = env.ref("base.IDR", raise_if_not_found=False)
    indonesia = env.ref("base.id", raise_if_not_found=False)
    co_vals = {}
    if idr:
        # currency must be active before assigning to company
        if not idr.active:
            idr.active = True
        co_vals["currency_id"] = idr.id
    if indonesia:
        co_vals["country_id"] = indonesia.id
        co_vals["account_fiscal_country_id"] = indonesia.id
    if accounts["forex_gain"]:
        co_vals["income_currency_exchange_account_id"] = accounts["forex_gain"].id
    if accounts["forex_loss"]:
        co_vals["expense_currency_exchange_account_id"] = accounts["forex_loss"].id
    if co_vals:
        company.write(co_vals)
        _logger.info("ARKA seed: company defaults set: %s", list(co_vals))

    # 1b. Re-stamp the auto-created pricelists to their company's currency.
    #
    # `product` creates the "Default" pricelist (product.list0) at install time
    # in whatever the base currency then is — USD on a fresh DB. This module
    # depends on `product`, so that pricelist already exists by the time step 1
    # above flips the company to IDR, and nothing else ever re-stamps it.
    #
    # That matters because sale.order takes its currency from the pricelist,
    # not the company (sale/models/sale_order.py::_compute_currency_id ->
    # `pricelist_id.currency_id or company_id.currency_id`), so a stale USD
    # pricelist silently stamps every sales order USD. On prd_arkaaim that
    # produced a draft invoice of Rp 120.000.000 worth Rp 2,13 triliun in the
    # ledger. See scripts/tenants/arkaaim/fix_pricelist_currency.py, which
    # repairs databases created before this block existed.
    #
    # Every company is covered, not just base.main_company: ARKA-AIM runs two.
    # An empty pricelist is pure currency, so re-stamping is lossless; one that
    # already carries price rules is left alone, since changing its currency
    # would reprice them.
    Pricelist = env["product.pricelist"].sudo()
    for target in env["res.company"].sudo().search([]):
        if not target.currency_id:
            continue
        stale = Pricelist.with_company(target).search(
            [
                ("company_id", "=", target.id),
                ("currency_id", "!=", target.currency_id.id),
            ]
        )
        for pricelist in stale:
            if pricelist.item_ids:
                _logger.warning(
                    "ARKA seed: pricelist %s (company %s) is %s not %s but carries %d price "
                    "rule(s); left alone to avoid repricing them",
                    pricelist.id,
                    target.id,
                    pricelist.currency_id.name,
                    target.currency_id.name,
                    len(pricelist.item_ids),
                )
                continue
            _logger.info(
                "ARKA seed: pricelist %s (company %s): %s -> %s",
                pricelist.id,
                target.id,
                pricelist.currency_id.name,
                target.currency_id.name,
            )
            pricelist.currency_id = target.currency_id.id

    # 2. Default partner receivable/payable via ir.default (covers company_dependent fields)
    IrDefault = env["ir.default"].sudo()
    if accounts["default_receivable"]:
        IrDefault.set(
            "res.partner", "property_account_receivable_id", accounts["default_receivable"].id, company_id=company.id
        )
    if accounts["default_payable"]:
        IrDefault.set(
            "res.partner", "property_account_payable_id", accounts["default_payable"].id, company_id=company.id
        )

    # 3. Default product.category accounts on the root "All" category
    Category = env["product.category"]
    # Odoo 19 dropped the product.product_category_all external id; fall back to
    # the topmost parent-less category, or create one if none exist.
    root_cat = env.ref("product.product_category_all", raise_if_not_found=False)
    if not root_cat:
        root_cat = Category.search([("parent_id", "=", False)], limit=1, order="id")
        if not root_cat:
            root_cat = Category.create({"name": "All"})
    cat_vals = {}
    if accounts["default_income"] and "property_account_income_categ_id" in Category._fields:
        cat_vals["property_account_income_categ_id"] = accounts["default_income"].id
    if accounts["default_expense"] and "property_account_expense_categ_id" in Category._fields:
        cat_vals["property_account_expense_categ_id"] = accounts["default_expense"].id
    if "property_stock_account_input_categ_id" in Category._fields:
        if accounts["stock_input"]:
            cat_vals["property_stock_account_input_categ_id"] = accounts["stock_input"].id
        if accounts["stock_output"]:
            cat_vals["property_stock_account_output_categ_id"] = accounts["stock_output"].id
        if accounts["stock_valuation"]:
            cat_vals["property_stock_valuation_account_id"] = accounts["stock_valuation"].id
    if cat_vals and root_cat:
        root_cat.with_company(company).write(cat_vals)
        # Also set defaults for fresh categories created later.
        for fname, val in cat_vals.items():
            IrDefault.set("product.category", fname, val, company_id=company.id)
        _logger.info("ARKA seed: product.category defaults set: %s", list(cat_vals))

    # 4. Default Cash/Bank journal accounts for existing journals lacking one
    Journal = env["account.journal"]
    if accounts["default_cash"]:
        Journal.search(
            [
                ("company_id", "=", company.id),
                ("type", "=", "cash"),
                ("default_account_id", "=", False),
            ]
        ).write({"default_account_id": accounts["default_cash"].id})
    if accounts["default_bank"]:
        Journal.search(
            [
                ("company_id", "=", company.id),
                ("type", "=", "bank"),
                ("default_account_id", "=", False),
            ]
        ).write({"default_account_id": accounts["default_bank"].id})

    _logger.info("ARKA seed: post_init_hook done")
