# -*- coding: utf-8 -*-
"""Post-init: per-company Trade / Non-Trade PO sequences + account mapping.

Idempotent -- safe to re-run on every upgrade. Sequences are updated in place
(never duplicated) and the running counters are left alone; account mapping rows
are only filled where a field is still empty, so a hand-corrected wiring survives.
"""

import logging

_logger = logging.getLogger(__name__)

# Same monthly tail as ``custom_arka_aim_numbering``: the printed YYYY/MM comes
# from the matched date range, so it always agrees with the counter being reset.
_MONTH_TAIL = "%(range_year)s/%(range_month)s/"

# (purchase type, ir.sequence code, human name, prefix head)
_SEQUENCES = [
    ("trade", "arka_aim.purchase_order_trade", "ARKA-AIM Purchase Order (Trade)", "PO/T"),
    ("non_trade", "arka_aim.purchase_order_nontrade", "ARKA-AIM Purchase Order (Non-Trade)", "PO/NT"),
]

# Account codes from the tenant chart. Both streams clear their goods-receipt
# accrual through a GR/IR account of their own, so a Trade and a Non-Trade
# balance never mix in the same clearing account.
ACCOUNT_CODES = {
    "trade": {
        "payable": "2103100001",
        "grir": "2103109199",
    },
    "non_trade": {
        "payable": "2103300001",
        "grir": "2103300008",
        "expense": "7799000000",
    },
}


def _upsert_sequence(env, code, name, prefix, company):
    Seq = env["ir.sequence"].sudo()
    vals = {
        "name": name,
        "code": code,
        "prefix": prefix,
        "padding": 3,
        "number_increment": 1,
        "implementation": "standard",
        "use_date_range": True,
        "x_monthly_reset": True,
        "company_id": company.id,
    }
    existing = Seq.search([("code", "=", code), ("company_id", "=", company.id)], limit=1)
    if existing:
        # Never write number_next_actual: the counters are already running.
        existing.write(vals)
        return existing
    return Seq.create(vals)


def _find_account(env, company, code):
    """Account by (company-dependent) code, resolved for ``company``.

    Two filters are both needed. ``code`` is company-dependent in Odoo 19, so it
    has to be read in the company's context. And the tenant chart holds one
    account record per company under the SAME code -- ``2103300001`` exists twice,
    once owned by AIM and once by ARKA -- while this hook runs as superuser, where
    the multi-company record rule does not apply. Without the ``company_ids``
    filter the search would return whichever row came first and happily wire AIM's
    payable onto ARKA's bills.
    """
    if not code:
        return env["account.account"].browse()
    return (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    )


def _ensure_payable(account):
    """An AP control account must be payable-typed and reconcilable.

    Core ``account.move.line._check_payable_receivable`` refuses to put anything
    else on a bill's payment-term line. The tenant chart designates these codes as
    payable; correct the type here if the import stored one as a plain liability.
    """
    if not account:
        return
    fix = {}
    if account.account_type != "liability_payable":
        fix["account_type"] = "liability_payable"
    if not account.reconcile:
        fix["reconcile"] = True
    if fix:
        _logger.info("ARKA-AIM purchase type: coercing AP account %s -> %s", account.code, fix)
        account.write(fix)


def _ensure_grir_current(account):
    """A GR/IR clearing account must be a reconcilable CURRENT liability.

    It sits on bill product lines, which carry no due date, and core forbids a
    ``liability_payable`` account there -- a clearing account imported as payable
    would block bill posting outright. Reconcilable so the receipt credit and the
    bill debit can be matched off.
    """
    if not account:
        return
    fix = {}
    if account.account_type != "liability_current":
        fix["account_type"] = "liability_current"
    if not account.reconcile:
        fix["reconcile"] = True
    if fix:
        _logger.info("ARKA-AIM purchase type: coercing GR/IR account %s -> %s", account.code, fix)
        account.write(fix)


def seed_sequences(env):
    """One PO sequence per company and per stream. Gated on ``x_doc_code``."""
    made = 0
    for company in env["res.company"].sudo().search([]):
        code = company.x_doc_code
        if not code:
            # Not an ARKA-AIM company: leave it on core PO numbering.
            continue
        for _ptype, seq_code, name, head in _SEQUENCES:
            prefix = "%s/%s/%s" % (head, code, _MONTH_TAIL)
            _upsert_sequence(env, seq_code, "%s (%s)" % (name, code), prefix, company)
            made += 1
    _logger.info("ARKA-AIM purchase type: %d PO sequence(s) seeded/verified", made)
    return made


def seed_account_map(env):
    """Fill the Trade / Non-Trade account mapping for every ARKA-AIM company."""
    AccountMap = env["arka.purchase.account.map"].sudo()
    companies = env["res.company"].sudo().search([("x_doc_code", "!=", False)])
    made = 0
    for company in companies:
        for ptype, codes in ACCOUNT_CODES.items():
            mapping = AccountMap._get_map(company, ptype)
            if not mapping:
                mapping = AccountMap.create({"company_id": company.id, "purchase_type": ptype})
                made += 1
            vals = {}
            for field, key in (
                ("payable_account_id", "payable"),
                ("grir_account_id", "grir"),
                ("expense_account_id", "expense"),
            ):
                if mapping[field] or not codes.get(key):
                    continue
                account = _find_account(env, company, codes[key])
                if account:
                    vals[field] = account.id
            if vals:
                mapping.write(vals)
            # Run on every upgrade so an already-mapped account is normalised too.
            _ensure_payable(mapping.payable_account_id)
            _ensure_grir_current(mapping.grir_account_id)
    _logger.info(
        "ARKA-AIM purchase type: account mapping verified for %d company/ies (%d row(s) created)",
        len(companies),
        made,
    )
    return made


def post_init_hook(env):
    seed_sequences(env)
    seed_account_map(env)
