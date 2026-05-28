{
    "name": "ARKA-AIM Chart of Accounts Seed",
    "version": "19.0.1.0.0",
    "summary": "Tenant-specific CoA, taxes, and fiscal positions for erp_dev_aimarka.",
    "description": """
ARKA-AIM Chart of Accounts seed.

Loads 548 accounts (10-digit codes) extracted from the ARKA-AIM Master Data
Template, plus PPN/PPh taxes and Indonesian fiscal positions.

INSTALL ONLY ON THE erp_dev_aimarka TENANT DB. The data here is specific to
that tenant and should not be loaded on the generic platform/other tenants.
""",
    "author": "Platform",
    "category": "Tenants/ARKA-AIM",
    "depends": [
        "account",
        "base",
        # Product is needed for the product.category default wiring in the
        # post-init hook. If stock is installed in the tenant DB, the hook will
        # also wire stock valuation/input/output accounts; we don't hard-depend
        # on stock_account so the seed remains installable on accounting-only
        # tenants.
        "product",
    ],
    "data": [
        "data/account.account.csv",
        "data/account.tax.group.csv",
        "data/account.tax.csv",
        "data/account.fiscal.position.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
