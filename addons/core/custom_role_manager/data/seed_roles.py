# -*- coding: utf-8 -*-
"""The shipped role catalogue — standard Head Office and retail positions.

Why Python and not an XML data file: ``noupdate="1"`` would freeze these roles
forever (a corrected group list would never reach an installed tenant), while
``noupdate="0"`` would clobber whatever an administrator adjusted locally.
Neither is right. ``sync_seed_roles`` therefore refreshes only the roles nobody
has edited (``customized = False``), and skips group xml-ids that do not exist
on the database it runs against — which is what lets one catalogue serve a POS
retail tenant and a services tenant alike.

Adding a position: append a dict here and bump the module version. The sync
runs from ``post_init_hook`` and from every post-migration.
"""

import logging

from odoo.fields import Command

_logger = logging.getLogger(__name__)


# Each entry: code, name, role_domain, level, scope, groups (xml-ids), implies (codes).
SEED_ROLES = [
    # ------------------------------------------------------------------
    # Head Office — Accounting & Finance
    # ------------------------------------------------------------------
    {
        "code": "hq_acc_staff_ap",
        "name": "Accounting Staff - AP",
        "role_domain": "accounting",
        "level": "staff",
        "scope": "head_office",
        "description": "Enters vendor bills and payment requests. Cannot post to "
        "locked periods or change the chart of accounts.",
        "groups": [
            "custom_core.group_custom_user",
            "account.group_account_invoice",
            "purchase.group_purchase_user",
        ],
    },
    {
        "code": "hq_acc_staff_ar",
        "name": "Accounting Staff - AR",
        "role_domain": "accounting",
        "level": "staff",
        "scope": "head_office",
        "description": "Customer invoices, receipts and receivable follow-up.",
        "groups": [
            "custom_core.group_custom_user",
            "account.group_account_invoice",
        ],
    },
    {
        "code": "hq_tax_officer",
        "name": "Tax Officer",
        "role_domain": "accounting",
        "level": "staff",
        "scope": "head_office",
        "description": "e-Faktur, Coretax and withholding (PPh / bupot) handling.",
        "groups": [
            "custom_core.group_custom_user",
            "account.group_account_invoice",
            "custom_coretax.group_user",
            "custom_coretax_bupot.group_bupot_user",
            "custom_pph_witholding.group_witholding_user",
        ],
    },
    {
        "code": "hq_treasury",
        "name": "Treasury / Cashier",
        "role_domain": "accounting",
        "level": "staff",
        "scope": "head_office",
        "description": "Bank and cash journals, payment execution, petty cash.",
        "groups": [
            "custom_core.group_custom_user",
            "account.group_account_invoice",
            "custom_petty_cash.group_petty_cash_finance",
        ],
    },
    {
        "code": "hq_acc_supervisor",
        "name": "Accounting Supervisor",
        "role_domain": "accounting",
        "level": "supervisor",
        "scope": "head_office",
        "description": "Reviews and posts what the staff prepared; runs the standard accounting reports.",
        "groups": [
            "account.group_account_user",
            "custom_accounting_reports.group_report_user",
        ],
        "implies": ["hq_acc_staff_ap", "hq_acc_staff_ar"],
    },
    {
        "code": "hq_acc_manager",
        "name": "Finance & Accounting Manager",
        "role_domain": "accounting",
        "level": "manager",
        "scope": "head_office",
        "description": "Full accounting rights including chart of accounts, lock "
        "dates and approval of finance documents.",
        "groups": [
            "account.group_account_manager",
            "custom_accounting_reports.group_report_admin",
            "custom_approval_engine.group_approval_manager",
        ],
        "implies": ["hq_acc_supervisor", "hq_treasury", "hq_tax_officer"],
    },
    {
        "code": "hq_auditor",
        "name": "Internal Auditor (Read-only)",
        "role_domain": "audit",
        "level": "readonly",
        "scope": "both",
        "description": "Reads the ledger and the reports; creates and edits nothing.",
        "groups": [
            "custom_core.group_custom_user",
            "account.group_account_readonly",
            "custom_accounting_reports.group_report_user",
        ],
    },
    # ------------------------------------------------------------------
    # Head Office — Supply chain & commercial
    # ------------------------------------------------------------------
    {
        "code": "hq_purchase_staff",
        "name": "Purchasing Staff",
        "role_domain": "purchase",
        "level": "staff",
        "scope": "head_office",
        "description": "Raises purchase orders and follows up vendors.",
        "groups": ["custom_core.group_custom_user", "purchase.group_purchase_user"],
    },
    {
        "code": "hq_purchase_manager",
        "name": "Purchasing Manager",
        "role_domain": "purchase",
        "level": "manager",
        "scope": "head_office",
        "description": "Approves purchase orders, manages vendor pricing.",
        "groups": ["purchase.group_purchase_manager"],
        "implies": ["hq_purchase_staff"],
    },
    {
        "code": "hq_sales_admin",
        "name": "Sales Admin / Merchandising",
        "role_domain": "sales",
        "level": "staff",
        "scope": "head_office",
        "description": "Sales orders and product master maintenance.",
        "groups": [
            "custom_core.group_custom_user",
            "sales_team.group_sale_salesman_all_leads",
        ],
    },
    {
        "code": "hq_sales_manager",
        "name": "Sales Manager",
        "role_domain": "sales",
        "level": "manager",
        "scope": "head_office",
        "description": "Full sales rights including pricing and discounts.",
        "groups": ["sales_team.group_sale_manager"],
        "implies": ["hq_sales_admin"],
    },
    {
        "code": "hq_inventory_manager",
        "name": "Inventory Manager",
        "role_domain": "inventory",
        "level": "manager",
        "scope": "head_office",
        "description": "Warehouse configuration, valuation and inventory adjustments.",
        "groups": ["stock.group_stock_manager"],
        "implies": ["store_stock_keeper"],
    },
    {
        "code": "hq_it_admin",
        "name": "IT / System Administrator",
        "role_domain": "it",
        "level": "manager",
        "scope": "head_office",
        "description": "Technical administration. Deliberately kept separate from "
        "the business roles: nobody should acquire Settings access as a side "
        "effect of a job title.",
        "groups": ["base.group_system", "custom_core.group_custom_admin"],
    },
    # ------------------------------------------------------------------
    # Retail — store positions
    # ------------------------------------------------------------------
    {
        "code": "store_cashier",
        "name": "Store Staff / POS Cashier",
        "role_domain": "pos",
        "level": "operator",
        "scope": "retail",
        "description": "Operates the point of sale. No accounting, no stock configuration.",
        "groups": ["custom_core.group_custom_user", "point_of_sale.group_pos_user"],
    },
    {
        "code": "store_stock_keeper",
        "name": "Stock Keeper",
        "role_domain": "inventory",
        "level": "operator",
        "scope": "both",
        "description": "Receives and ships goods, counts stock. No accounting.",
        "groups": ["custom_core.group_custom_user", "stock.group_stock_user"],
    },
    {
        "code": "store_supervisor",
        "name": "Store Supervisor",
        "role_domain": "pos",
        "level": "supervisor",
        "scope": "retail",
        "description": "Opens and closes POS sessions, supervises stock counts.",
        "groups": [],
        "implies": ["store_cashier", "store_stock_keeper"],
    },
    {
        "code": "store_manager",
        "name": "Store Manager",
        "role_domain": "pos",
        "level": "manager",
        "scope": "retail",
        "description": "Runs one store: POS configuration, stock, store reports and first-level approvals.",
        "groups": [
            "point_of_sale.group_pos_manager",
            "custom_accounting_reports.group_report_user",
            "custom_approval_engine.group_approval_user",
        ],
        "implies": ["store_supervisor"],
    },
    {
        "code": "area_manager",
        "name": "Area Manager",
        "role_domain": "pos",
        "level": "supervisor",
        "scope": "retail",
        "description": "Supervises several stores. Give this role the relevant "
        "Operating Units — an area OU automatically covers the stores under it.",
        "groups": ["purchase.group_purchase_user"],
        "implies": ["store_manager"],
    },
]


def sync_seed_roles(env):
    """Create or refresh the shipped roles. Idempotent.

    * missing roles are created;
    * roles an administrator has edited (``customized``) are left alone;
    * group xml-ids absent from this database are skipped, so the same
      catalogue works on a tenant without POS, without Coretax, etc.
    """
    Role = env["custom.security.role"].with_context(role_seed_sync=True)
    by_code = {}
    skipped = set()

    for spec in SEED_ROLES:
        group_ids = []
        for xmlid in spec.get("groups", []):
            group = env.ref(xmlid, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
            else:
                skipped.add(xmlid)
        vals = {
            "name": spec["name"],
            "role_domain": spec["role_domain"],
            "level": spec.get("level", "staff"),
            "scope": spec.get("scope", "both"),
            "description": spec.get("description"),
            "is_seed": True,
            "group_ids": [Command.set(group_ids)],
        }
        role = Role.with_context(active_test=False).search([("code", "=", spec["code"])], limit=1)
        if not role:
            role = Role.create(dict(vals, code=spec["code"]))
        elif not role.customized:
            role.write(vals)
        by_code[spec["code"]] = role

    # Second pass: implied roles can only be linked once every role exists.
    for spec in SEED_ROLES:
        role = by_code[spec["code"]]
        if role.customized:
            continue
        implied = [by_code[c].id for c in spec.get("implies", []) if c in by_code]
        if set(implied) != set(role.implied_role_ids.ids):
            role.write({"implied_role_ids": [Command.set(implied)]})

    if skipped:
        _logger.info(
            "Seed roles: %d group xml-id(s) not present on this database, skipped: %s",
            len(skipped),
            ", ".join(sorted(skipped)),
        )

    # Push the refreshed composition to everyone already holding a seed role.
    holders = env["res.users"].search([("role_ids", "in", [r.id for r in by_code.values()])])
    if holders:
        holders._apply_security_roles()
    _logger.info("Seed roles synced: %d role(s), %d holder(s) re-applied.", len(by_code), len(holders))
    return by_code
