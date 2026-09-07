# custom_arka_aim_seed

Chart of accounts, taxes and fiscal positions for the ARKA-AIM tenant, plus the
post-init hook that wires the freshly loaded accounts into the module defaults
Odoo will actually read at runtime. Tenant-scoped — install only on ARKA-AIM
databases.

## Why this exists

Loading 548 accounts is the easy half. The half that bites is that Odoo does not
consult the chart directly: it reads a company field, an `ir.default`, a product
category, or a journal default. Load a chart without wiring those, and every
document quietly falls back to the generic accounts that shipped with `account`
— which are archived the moment a real chart replaces them, and an archived
account makes core refuse **every write** to the move, not just the posting.

So the data files load the chart, and `post_init_hook` points the runtime at it.

## What the hook sets

| # | Target | Value |
|---|---|---|
| 1 | `res.company` | currency IDR, country/fiscal country Indonesia, forex gain `7607000000` / loss `7704000000` |
| 1b | `product.pricelist` | each company's pricelist re-stamped to that company's currency |
| 2 | `ir.default` on `res.partner` | receivable `1106000001`, payable `2103100001` |
| 3 | root `product.category` + `ir.default` | income `5199000000`, expense `6199000000`, and stock input/output/valuation when `stock` is present |
| 4 | `account.journal` | default cash `1102000001` and bank `1103019300`, only for journals that have none |

Accounts are resolved through this module's own external ids (`ACCOUNT_REFS`), so
a reloaded chart keeps working. A missing xmlid warns and is skipped rather than
raising — the seed must not half-install.

## Step 1b: why the pricelist is re-stamped

`sale.order` takes its currency from the **pricelist**, not the company:

```python
# sale/models/sale_order.py::_compute_currency_id
order.currency_id = order.pricelist_id.currency_id or order.company_id.currency_id
```

`product` creates `product.list0` at install time in the then-current base
currency (USD on a fresh DB), and this module depends on `product` — so that
pricelist already exists by the time step 1 flips the company to IDR. Nothing
used to re-stamp it, so every AIM sales order came out USD while the company was
IDR. The figures were rupiah all along; the derived company-currency values were
not, and a draft invoice of Rp 120.000.000 carried Rp 2,13 triliun in the ledger.

Two details worth keeping:

- **Every company, not `base.main_company`.** ARKA-AIM runs two (AIM and ARKA),
  and steps 1–4 only ever touched the main one. Step 1b deliberately loops over
  all of them.
- **Empty pricelists only.** One carrying price rules is left alone and logged:
  changing its currency would silently reprice every rule in it.

## Repairing a database that predates step 1b

The hook only runs at install, so databases seeded earlier keep the stale
pricelist. Two idempotent scripts fix them, both preview-first:

- `scripts/tenants/arkaaim/fix_pricelist_currency.py` — re-stamps the pricelist,
  the sales orders that inherited it, and any draft invoice still on the old
  currency. It asserts that **no amount moves** and refuses to touch a posted
  move or a genuine foreign-currency bill.
- `scripts/tenants/arkaaim/fix_product_income_accounts.py` — gives every product
  template a category, which is what step 3's wiring needs in order to apply.

`scripts/tenants/arkaaim/audit_finance_parity.py` reports both gaps (blocks [8]
and [9]) on any ARKA database.

## Open items for Finance (do not auto-decide)

- Company 1's `6122000000` (COGS-Rental Asset) and `6199000000` (COGS-Others) are
  typed `income`, while company 2's equivalents are `expense_direct_cost`. Step
  3 therefore points the expense default at an income-typed account. Correcting
  an account type touches existing balances, so it is left to Accounting.
- The hook does not set `downpayment_account_id`; see
  `scripts/tenants/arkaaim/setup_downpayment_account.py`.

## Related

- `custom_arka_aim_asset_register` — the drone fixed-asset subledger built on this chart.
