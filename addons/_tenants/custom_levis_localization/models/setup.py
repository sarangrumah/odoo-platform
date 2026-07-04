# -*- coding: utf-8 -*-
"""Idempotent seeding for the Trade/Non-Trade + Operating-Unit feature (#9).

Provisions, per company that has Levi's stores:

* an "Operating Unit" analytic plan + one analytic account per store
  (``stock.warehouse``), linked via ``warehouse.l10n_ou_analytic_id``;
* a dedicated purchase journal per store, linked via
  ``warehouse.l10n_purchase_journal_id``;
* the ``levis.purchase.account.map`` rows (trade / non-trade) resolved by
  account *code* (company-dependent, read with ``with_company``).

Safe to run repeatedly: everything is guarded by the link fields / existing
records. Called from the module ``post_init_hook`` and from
``scripts/tenants/levis/40_setup_trade_ou.py``.
"""

import logging

_logger = logging.getLogger(__name__)

OU_PLAN_NAME = "Operating Unit"

# Account codes in the EBR chart of accounts (company-dependent → resolve with
# ``with_company``). Trade GR/IR stays per product category, so no code here.
ACCOUNT_CODES = {
    "trade": {"payable": "2103100001"},
    "non_trade": {"payable": "2103300001", "grir": "2103300008", "expense": "6120010001"},
}


def _find_account(env, company, code):
    return (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code)], limit=1)
    )


def _ensure_payable(account):
    """Coerce an AP control account to payable type + reconcilable."""
    if not account:
        return
    fix = {}
    if account.account_type != "liability_payable":
        fix["account_type"] = "liability_payable"
    if not account.reconcile:
        fix["reconcile"] = True
    if fix:
        _logger.info("Levi's Trade/OU: coercing AP account %s -> %s", account.code, fix)
        account.write(fix)


def _ensure_ou_plan(env):
    Plan = env["account.analytic.plan"]
    plan = Plan.search([("name", "=", OU_PLAN_NAME)], limit=1)
    if not plan:
        plan = Plan.create({"name": OU_PLAN_NAME})
    return plan


def _unique_journal_code(env, company, base):
    """Return a <=5-char purchase-journal code unique within the company."""
    Journal = env["account.journal"]
    code = base[:5]
    n = 0
    while Journal.search_count(
        [("code", "=", code), ("company_id", "=", company.id)]
    ):
        n += 1
        code = ("%s%d" % (base[:4], n))[:5]
    return code


def seed_trade_ou(env):
    warehouses = env["stock.warehouse"].search([])
    if not warehouses:
        return
    plan = _ensure_ou_plan(env)
    Analytic = env["account.analytic.account"]
    Journal = env["account.journal"]

    made_analytic = made_journal = 0
    for idx, wh in enumerate(warehouses, start=1):
        company = wh.company_id or env.company
        wh_name = wh.display_name

        # Operating-Unit analytic account
        if not wh.l10n_ou_analytic_id:
            analytic = Analytic.search(
                [("name", "=", wh_name), ("plan_id", "=", plan.id),
                 ("company_id", "=", company.id)],
                limit=1,
            ) or Analytic.create({
                "name": wh_name,
                "plan_id": plan.id,
                "company_id": company.id,
            })
            wh.l10n_ou_analytic_id = analytic.id
            made_analytic += 1

        # Per-store purchase journal
        if not wh.l10n_purchase_journal_id:
            code = _unique_journal_code(env, company, wh.code or ("P%03d" % idx))
            journal = Journal.search(
                [("type", "=", "purchase"), ("company_id", "=", company.id),
                 ("name", "=", "Pembelian - %s" % wh_name)],
                limit=1,
            ) or Journal.create({
                "name": "Pembelian - %s" % wh_name,
                "type": "purchase",
                "code": code,
                "company_id": company.id,
            })
            wh.l10n_purchase_journal_id = journal.id
            made_journal += 1

    # Trade / Non-Trade account mapping, one pair per company that has stores
    AccountMap = env["levis.purchase.account.map"]
    companies = warehouses.mapped("company_id") or env.company
    made_map = 0
    for company in companies:
        for ptype, codes in ACCOUNT_CODES.items():
            mapping = AccountMap._get_map(company, ptype)
            if not mapping:
                mapping = AccountMap.create(
                    {"company_id": company.id, "purchase_type": ptype}
                )
                made_map += 1
            vals = {}
            if not mapping.payable_account_id:
                acc = _find_account(env, company, codes.get("payable"))
                if acc:
                    vals["payable_account_id"] = acc.id
            if not mapping.grir_account_id and codes.get("grir"):
                acc = _find_account(env, company, codes["grir"])
                if acc:
                    vals["grir_account_id"] = acc.id
            if not mapping.expense_account_id and codes.get("expense"):
                acc = _find_account(env, company, codes["expense"])
                if acc:
                    vals["expense_account_id"] = acc.id
            if vals:
                mapping.write(vals)
            # An AP control account must be payable-typed and reconcilable for
            # Odoo to use it on the vendor-bill payment-term line
            # (account.move.line._check_payable_receivable). The EBR CoA
            # designates these accounts as payable; correct the type here if the
            # import stored one as a plain current liability. Runs every time so
            # already-mapped accounts are also normalised.
            _ensure_payable(mapping.payable_account_id)

    _logger.info(
        "Levi's Trade/OU seeding: %d analytic, %d journals, %d mappings",
        made_analytic, made_journal, made_map,
    )
    return {"analytic": made_analytic, "journals": made_journal, "mappings": made_map}
