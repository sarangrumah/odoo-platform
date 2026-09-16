# -*- coding: utf-8 -*-
"""Payable-account routing for the Trade / Non-Trade split (feature #9).

The vendor bill's payable (payment-term) line account is computed by core
``account.move.line._compute_account_id``. For Levi's, the payable must follow
the purchase stream carried on the bill (``account.move.l10n_purchase_type``):
Trade Payables vs Non-Trade payable. The accounts come from the per-company
``levis.purchase.account.map`` so no hard ids leak into code.

The stream alone does not decide the account: the EBR chart splits AP again by
counterparty, third party vs **related party** (in-group companies such as PT
Sinar Eka Selaras). Vendors flagged ``l10n_related_party`` take the mapping's
related-party account; before that flag existed every Erajaya-group bill landed
on the third-party control account no matter what the vendor master said.
"""

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # ------------------------------------------------------------------
    # Operating Unit (feature #9) — user-picked on manual bill lines so P&L
    # can be split Head Office vs Store. PO-derived lines get their OU from the
    # PO analytic; this field lets a MANUAL bill line carry one too. The picked
    # OU analytic is merged into the native ``analytic_distribution`` (its own
    # plan), reusing ``purchase.order.line._levis_merge_ou_distribution``.
    # ------------------------------------------------------------------
    l10n_ou_analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Operating Unit",
        domain="[('plan_id.name', '=', 'Operating Unit')]",
        help="Operating Unit (Head Office / Store) this line belongs to. Stamped "
        "onto the line's analytic distribution for per-OU P&L reporting.",
    )

    # Preserve the base dependencies and add the OU field so picking/clearing it
    # (or changing the product) re-stamps the distribution. Re-declaring
    # @api.depends REPLACES the inherited set, so all base triggers are relisted.
    @api.depends("account_id", "partner_id", "product_id", "l10n_ou_analytic_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            ou = line.l10n_ou_analytic_id
            if not ou or line.display_type != "product":
                continue
            line.analytic_distribution = self.env["purchase.order.line"]._levis_merge_ou_distribution(
                line.analytic_distribution, ou.id
            )

    # Base ``_compute_account_id`` carries no @api.depends — it is a
    # precompute-at-create field. ``move_id.l10n_purchase_type`` is already set on
    # the bill at create time (via ``purchase.order._prepare_invoice``), so the
    # precompute pass sees it. We keep the same (dependency-free) semantics and
    # just remap the payable after ``super()``.
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._levis_reroute_imported_grir()
        return lines

    def _levis_reroute_imported_grir(self):
        """Re-apply GR/IR routing to lines that arrived with an account already set.

        ``_compute_account_id`` is a **precompute** field with no
        ``@api.depends`` (see the comment above it). A create that supplies
        ``account_id`` therefore skips the routing entirely — which is exactly
        what the bill importer does, and why imported bills kept landing on
        COGS/expense while the GR/IR accrual stayed open. Row #42 reports the
        symptom; this is the other half of it.

        Deliberately narrow: a line is re-routed only when it has a PO link and
        every other gate already agrees it belongs on GR/IR. A hand-picked
        expense account on a line with no purchase order is never touched.
        """
        # Cheapest gate first: this runs on EVERY account.move.line create in
        # the database, and the overwhelming majority carry no purchase order.
        candidates = self.filtered(lambda line: line.display_type == "product" and line.purchase_line_id)
        if not candidates:
            return
        suppress = (
            self.env["ir.config_parameter"].sudo().get_param("custom_levis_localization.suppress_gr_journal", "0")
        )
        if str(suppress).strip().lower() not in ("0", "false", "", "none"):
            return
        for line in candidates:
            move = line.move_id
            if move.move_type not in ("in_invoice", "in_refund") or move.state != "draft":
                continue
            # An importer that never set the stream leaves the mapping
            # unresolvable, so take it from the order the line already points at.
            if not move.l10n_purchase_type:
                ptype = line.purchase_line_id.order_id.l10n_purchase_type
                if ptype:
                    move.l10n_purchase_type = ptype
            account = line._levis_grir_account()
            if account and line.account_id != account:
                line.account_id = account.id

    def _levis_grir_account(self, mapping=None):
        """The GR/IR account this bill line belongs on, or an empty recordset.

        Extracted because **two** callers must agree on the answer:
        ``_compute_account_id`` routes the line here when the bill is created,
        and ``account.move._levis_reconcile_grir`` has to recognise the same
        line again when the bill is posted. Two copies of five gates would
        drift, and the failure would be silent — a line routed to GR/IR but not
        recognised at post simply never nets.

        The gates, and why each one is load-bearing:

        * a vendor bill or credit note, with ``l10n_purchase_type`` set and a
          stream mapping — without those there is no GR/IR account to speak of;
        * a **product** line linked to a ``purchase_line_id``: a hand-made bill
          posted no GR accrual, so routing it here would strand the clearing
          account;
        * ``product_id.type == "consu"`` — services carry no stock move;
        * the category valued ``real_time`` in this company. **Not**
          ``is_storable``: the imported Levi's catalogue is entirely
          ``consu`` / ``is_storable = False`` and still real-time valued, so an
          ``is_storable`` gate never fires and the accrual never nets.

        The caller checks the suppress switch: in periodic mode the accrual is
        trued up by Inventory Reconciliation, not per bill.
        """
        self.ensure_one()
        move = self.move_id
        if move.move_type not in ("in_invoice", "in_refund"):
            return self.env["account.account"].browse()
        if self.display_type != "product":
            return self.env["account.account"].browse()
        if not self.purchase_line_id or self.product_id.type != "consu":
            return self.env["account.account"].browse()
        if mapping is None:
            ptype = move.l10n_purchase_type
            mapping = self.env["levis.purchase.account.map"]._get_map(move.company_id, ptype) if ptype else None
        if not mapping:
            return self.env["account.account"].browse()
        categ = self.product_id.categ_id.with_company(move.company_id)
        if categ.property_valuation != "real_time":
            return self.env["account.account"].browse()
        # Mirror the receipt's own choice exactly (stock_move.py::
        # _levis_book_valuation_entry): the mapping supplies the non-trade
        # GR/IR account, trade keeps its per-category stock-variation account.
        return mapping.grir_account_id or categ.account_stock_variation_id

    def _compute_account_id(self):
        super()._compute_account_id()
        AccountMap = self.env["levis.purchase.account.map"]
        # GR/IR routing only applies while the goods-receipt accrual is posted
        # per receipt (suppress switch OFF, the default). In periodic mode the
        # accrual is trued up by Inventory Reconciliation, not per bill, so the
        # bill keeps its native/expense account. The switch is the same
        # ir.config_parameter read by stock.move._levis_suppress_gr_journal.
        suppress = (
            self.env["ir.config_parameter"].sudo().get_param("custom_levis_localization.suppress_gr_journal", "0")
        )
        gr_accrual_active = str(suppress).strip().lower() in ("0", "false", "", "none")
        for line in self:
            move = line.move_id
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            ptype = move.l10n_purchase_type
            if not ptype:
                continue
            mapping = AccountMap._get_map(move.company_id, ptype)
            if not mapping:
                continue
            if line.display_type == "payment_term":
                # Route the AP control account per stream (trade vs non-trade)
                # and per counterparty (third vs related party).
                payable = self._levis_stream_payable(mapping, move)
                if payable:
                    line.account_id = payable.id
            elif line.display_type == "product":
                # Storable, real-time products booked a GR/IR accrual on receipt
                #   Dr Stock Valuation / Cr Stock Variation (GR/IR)
                # (see stock_move.py::_levis_book_valuation_entry). The vendor
                # bill must debit that SAME GR/IR account so the accrual nets to
                # zero — Dr GR/IR clearing / Cr AP — instead of posting COGS/
                # expense directly against AP (the reported bug). Mirror the
                # receipt's account choice exactly: mapping.grir_account_id when
                # set (non-trade), else the category's stock-variation account
                # (trade keeps its per-category GR/IR).
                grir_acc = self.browse()
                # Gate on the SAME condition as the receipt-side GR journal
                # (stock_move.py::_levis_book_valuation_entry): the product's
                # category is real-time. NOT on ``is_storable`` — the imported
                # Levi's catalog is entirely ``type='consu', is_storable=False``
                # yet still real-time valued, so an ``is_storable`` gate never
                # fired and the accrual never netted (bill hit COGS instead of
                # GR/IR). Services carry no stock move / GR accrual, so exclude.
                # Also require a PO link: a MANUALLY-created bill (no goods
                # receipt) never posted a GR accrual, so routing its product line
                # to GR/IR would leave the clearing account un-netted and would
                # clobber the user's hand-picked expense account. Manual bills
                # therefore keep AP-payable routing + numbering only.
                if gr_accrual_active:
                    grir_acc = line._levis_grir_account(mapping)
                if grir_acc:
                    line.account_id = grir_acc.id
                elif not line.account_id and mapping.expense_account_id:
                    # Non-trade opex products frequently have no expense account
                    # on their master, which would block bill posting. Fall back
                    # to the stream's default expense account — but ONLY when the
                    # line has no account yet, so a configured product/category
                    # account always wins.
                    line.account_id = mapping.expense_account_id.id

    # ------------------------------------------------------------------
    # Related-party AP routing
    # ------------------------------------------------------------------
    @api.model
    def _levis_stream_payable(self, mapping, move):
        """AP control account for ``move``: stream x counterparty.

        The EBR chart splits AP four ways — trade/non-trade (the purchase
        stream, carried on the bill) crossed with third/related party (a
        property of the *vendor*, flagged as ``l10n_related_party`` on the
        contact). Related parties are in-group companies such as PT Sinar Eka
        Selaras; before this split every Erajaya-group bill silently landed on
        the third-party control account, whatever the vendor master said.

        Falls back to the stream's ordinary payable when the related-party
        account is not configured, so an unconfigured company keeps working.
        """
        # The AP account follows the COMMERCIAL partner, like core
        # ``_compute_account_id`` does: an invoicing child bills to its parent.
        partner = move.commercial_partner_id
        if partner.l10n_related_party and mapping.related_payable_account_id:
            return mapping.related_payable_account_id
        return mapping.payable_account_id
