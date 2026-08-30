# -*- coding: utf-8 -*-
"""Operating-Unit wiring on the warehouse (store).

Each Levi's store is a ``stock.warehouse``. Feature #9 turns the store into a
posted **Operating Unit** dimension: every store owns

* an ``account.analytic.account`` (in the "Operating Unit" analytic plan) that is
  stamped on PO / bill / GR-journal lines so journals and P&L can be sliced per
  store, and
* a dedicated **purchase journal** so vendor bills are separated per store.

The links are populated idempotently by the module seeding (post-init hook /
``40_setup_trade_ou.py``); the fields here just hold them.

**Store code.** The analytic account is the store's identity in the ledger, but
it is a record id, not something a cashier can type on a transfer memo or a bank
can print on a statement. A textual code did exist — but only inside the X24DN
retail feed, reachable only through ``ir.model.data`` xids named
``posconfig_<CODE>``. ``l10n_store_code`` promotes it to the warehouse so one
code serves the POS feed, the cash-deposit berita acara and bank matching alike.

Deliberately *not* required and *not* tied to the analytic by a constraint: a
warehouse may legitimately exist before either is assigned. A settlement that
resolves to a store with no code raises a clearing diagnostic instead — it shows
up, it does not block.
"""

from odoo import api, fields, models, tools


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    l10n_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit (Analytic)",
        help="Analytic account representing this store as an Operating Unit. "
        "Stamped on purchase / bill / goods-receipt journal lines.",
    )
    l10n_purchase_journal_id = fields.Many2one(
        "account.journal",
        string="Store Purchase Journal",
        domain="[('type', '=', 'purchase')]",
        help="Dedicated purchase journal for vendor bills of this store.",
    )
    l10n_store_code = fields.Char(
        string="Store Code",
        index=True,
        copy=False,
        help="Short code identifying this store outside Odoo — the same code the "
        "X24DN retail feed uses. It is what a cash-deposit transfer memo carries "
        "and what lets a bank credit name its own store.",
    )

    _store_code_uniq = models.Constraint(
        "unique(company_id, l10n_store_code)",
        "Two stores of the same company cannot share a store code.",
    )

    # ------------------------------------------------------------------
    # Resolver
    # ------------------------------------------------------------------
    @api.model
    @tools.ormcache("company_id")
    def _levis_store_code_index(self, company_id):
        """``{CODE: (warehouse_id, analytic_id)}`` for one company.

        One place learns the code -> store rule; the cash deposit, the matcher
        and the closing report all read this. Codes are upper-cased and stripped
        so a memo typed in lower case still resolves.
        """
        warehouses = self.sudo().search([("company_id", "=", company_id), ("l10n_store_code", "!=", False)])
        return {
            (wh.l10n_store_code or "").strip().upper(): (wh.id, wh.l10n_ou_analytic_id.id)
            for wh in warehouses
            if (wh.l10n_store_code or "").strip()
        }

    @api.model
    def _levis_store_by_code(self, company, code):
        """``(warehouse, analytic)`` for ``code``, or empty recordsets."""
        Warehouse = self.env["stock.warehouse"]
        Analytic = self.env["account.analytic.account"]
        key = (code or "").strip().upper()
        if not key or not company:
            return Warehouse, Analytic
        hit = self._levis_store_code_index(company.id).get(key)
        if not hit:
            return Warehouse, Analytic
        return Warehouse.browse(hit[0]), Analytic.browse(hit[1]) if hit[1] else Analytic

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------
    _LEVIS_INDEXED_FIELDS = ("l10n_store_code", "l10n_ou_analytic_id", "company_id")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(f in vals for vals in vals_list for f in self._LEVIS_INDEXED_FIELDS):
            self.env.registry.clear_cache()
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(f in vals for f in self._LEVIS_INDEXED_FIELDS):
            self.env.registry.clear_cache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.registry.clear_cache()
        return result
