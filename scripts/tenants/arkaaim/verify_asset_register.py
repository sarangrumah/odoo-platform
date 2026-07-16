# -*- coding: utf-8 -*-
"""Reconcile the AIM drone fixed-asset register against the opening-balance GL.

READ-ONLY. Prints:

* register record counts (total / valued / zero-value / with-serial / PO-only);
* register cost (SUM acquisition_value)      vs GL 1205104000;
* register accumulated depreciation          vs GL 1205203000;
* register net book value                    vs GL (cost - accum);
* the list of zero-value (listing-only) units for follow-up.

All three variances are expected to trace to the single +34,976,845 PO-vs-GL cost
difference (see custom_arka_aim_asset_register/MODULE_KNOWLEDGE.md).

USAGE (odoo shell, inside the mgmt container)
---------------------------------------------
    docker exec -i odoo19-platform-odoo-mgmt \
        odoo shell -d trn_arkaaim_begbal --no-http --max-cron-threads=0 \
        --http-port=8987 --gevent-port=8988 < verify_asset_register.py

Swap ``-d trn_arkaaim_begbal`` for ``-d prd_arkaaim`` to check production.
"""

AIM_COMPANY = "PT Aero Inovasi Media"
COST_CODE = "1205104000"
ACCUM_CODE = "1205203000"


def _fmt(n):
    return f"{n:>20,.0f}"


def _gl_balance(env, company, code):
    """Signed posted balance (debit - credit) of an account by code, in company."""
    acc = (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    )
    if not acc:
        return acc, 0.0
    env.cr.execute(
        """
        SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        WHERE aml.account_id = %s AND aml.company_id = %s AND am.state = 'posted'
        """,
        (acc.id, company.id),
    )
    return acc, env.cr.fetchone()[0]


def main(env):
    company = env["res.company"].search([("name", "=", AIM_COMPANY)], limit=1)
    if not company:
        print(f"!! company {AIM_COMPANY!r} not found")
        return
    Asset = env["custom.fixed.asset"].with_company(company)
    assets = Asset.search([("company_id", "=", company.id)])
    if not assets:
        print("!! no AIM fixed assets found")
        return

    valued = assets.filtered(lambda a: a.acquisition_value > 0)
    zero = assets - valued
    with_serial = assets.filtered(lambda a: a.serial_number)
    po_only = assets.filtered(lambda a: (a.source_group or "").startswith("PO-ONLY"))

    reg_cost = sum(assets.mapped("acquisition_value"))
    reg_accum = sum(assets.mapped("accumulated_depreciation"))
    reg_nbv = sum(assets.mapped("net_book_value"))

    _, gl_cost = _gl_balance(env, company, COST_CODE)
    _, gl_accum_signed = _gl_balance(env, company, ACCUM_CODE)
    gl_accum = -gl_accum_signed  # accum sits credit -> report as positive
    gl_nbv = gl_cost - gl_accum

    print("=" * 66)
    print(f"AIM drone fixed-asset register reconciliation  [{company.name}]")
    print("=" * 66)
    print(f"records total        : {len(assets)}")
    print(f"  valued (cost > 0)  : {len(valued)}")
    print(f"  zero-value         : {len(zero)}  (listing-only, no PO price)")
    print(f"  with serial number : {len(with_serial)}")
    print(f"  PO-only spares     : {len(po_only)}")
    print("-" * 66)
    print(f"{'':22}{'REGISTER':>20}{'GL':>20}")
    print(f"{'cost':22}{_fmt(reg_cost)}{_fmt(gl_cost)}   var {_fmt(reg_cost - gl_cost)}")
    print(f"{'accum depreciation':22}{_fmt(reg_accum)}{_fmt(gl_accum)}   var {_fmt(reg_accum - gl_accum)}")
    print(f"{'net book value':22}{_fmt(reg_nbv)}{_fmt(gl_nbv)}   var {_fmt(reg_nbv - gl_nbv)}")
    print("-" * 66)
    print("Expected: all three variances trace to the +34,976,845 PO-vs-GL cost gap")
    print("          (accum ~= 25% of gap, NBV ~= 75%). GL is NOT adjusted here.")
    if zero:
        print("-" * 66)
        print(f"zero-value (listing-only) units to price with Finance ({len(zero)}):")
        for a in zero:
            print(f"    {a.name}  serial={a.serial_number or '-'}")
    print("=" * 66)


main(env)  # noqa: F821 -- `env` is provided by `odoo shell`
