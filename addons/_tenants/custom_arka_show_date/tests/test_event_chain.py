# -*- coding: utf-8 -*-
"""The event has to survive the whole chain: ARKA sale -> ARKA purchase -> AIM sale.

Two companies are set up as the client runs them: the buyer (PT ARKA, which
sells the show to the customer and buys it from its sister) and the seller
(PT AIM). An intercompany rule ties them, exactly as
``custom_intercompany_procurement`` expects.
"""

from datetime import date

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install", "custom_arka_show_date")
class TestArkaEventChain(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = cls.company_data["company"]  # "PT ARKA"
        cls.seller = cls.setup_other_company(name="Sister Co")["company"]  # "PT AIM"
        cls.buyer.x_custom_show_date_enabled = True
        cls.buyer.x_custom_event_tracking_enabled = True
        cls.seller.x_custom_event_tracking_enabled = True
        cls.env.user.company_ids = [(4, cls.buyer.id), (4, cls.seller.id)]

        cls.product = cls.product_a
        cls.product.write({"purchase_ok": True, "sale_ok": True})
        # March 2026 on purpose. The event analytic account is shared across
        # companies (company_id = False), so a test running against a clone of a
        # tenant DB sees that tenant's real events too: "Soekarno Cup" on
        # 2026-08-24 exists in prd_arkaaim, and a test dated there would resolve
        # to the client's own account and join the client's events in any
        # period-based allocation. A date no real show falls on keeps the
        # fixture to itself. It stays in the PAST because action_post() posts
        # softly — a future-dated invoice would quietly stay in draft.
        cls.show = date(2026, 3, 10)

        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.seller.id)], limit=1)
        cls.rule = (
            cls.env["account.intercompany.rule"]
            .sudo()
            .create(
                {
                    "name": "ARKA -> AIM",
                    "company_from_id": cls.buyer.id,
                    "company_to_id": cls.seller.id,
                    "mirror_purchase_order": True,
                    "target_warehouse_id": cls.warehouse.id,
                }
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _sale(self, **overrides):
        vals = {
            "partner_id": self.partner_a.id,
            "company_id": self.buyer.id,
            "x_custom_show_date": self.show,
            "x_custom_event_name": "Soekarno Cup",
            "x_custom_event_location": "Stadion Gelora Bung Tomo Surabaya",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 2})],
        }
        vals.update(overrides)
        return self.env["sale.order"].with_company(self.buyer).sudo().create(vals)

    def _purchase(self, company=None, **overrides):
        company = company or self.buyer
        vals = {
            "partner_id": self.seller.partner_id.id,
            "company_id": company.id,
            "x_custom_show_date": self.show,
            "x_custom_event_name": "Soekarno Cup",
            "x_custom_event_location": "Stadion Gelora Bung Tomo Surabaya",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_qty": 2, "price_unit": 100.0})],
        }
        vals.update(overrides)
        return self.env["purchase.order"].with_company(company).sudo().create(vals)

    def _account_of(self, record):
        return record._custom_event_analytic_account(create=False)

    # ------------------------------------------------------------------
    # Layer 1 — the event on the buying leg
    # ------------------------------------------------------------------
    def test_purchase_order_carries_event_to_the_vendor_bill(self):
        purchase = self._purchase()
        values = purchase._prepare_invoice()
        self.assertEqual(values["x_custom_show_date"], self.show)
        self.assertEqual(values["x_custom_event_name"], "Soekarno Cup")
        self.assertEqual(values["x_custom_event_location"], "Stadion Gelora Bung Tomo Surabaya")

    def test_sale_order_carries_event_to_the_customer_invoice(self):
        values = self._sale()._prepare_invoice()
        self.assertEqual(values["x_custom_show_date"], self.show)
        self.assertEqual(values["x_custom_event_name"], "Soekarno Cup")

    # ------------------------------------------------------------------
    # Layer 3 — one analytic account per event
    # ------------------------------------------------------------------
    def test_label_concatenates_event_location_and_date(self):
        self.assertEqual(
            self._sale()._custom_event_label(),
            "Soekarno Cup - Stadion Gelora Bung Tomo Surabaya - 10.03.26",
        )

    def test_label_skips_what_was_not_filled_in(self):
        order = self._sale(x_custom_event_location=False)
        self.assertEqual(order._custom_event_label(), "Soekarno Cup - 10.03.26")

    def test_document_without_event_data_has_no_analytic_account(self):
        order = self._sale(x_custom_show_date=False, x_custom_event_name=False, x_custom_event_location=False)
        self.assertFalse(order._custom_event_analytic_account())
        self.assertFalse(order._custom_event_apply_analytic())

    def test_sale_and_purchase_of_one_event_share_one_account(self):
        sale = self._sale()
        purchase = self._purchase()
        account = sale._custom_event_analytic_account()
        self.assertTrue(account)
        self.assertEqual(purchase._custom_event_analytic_account(), account)

    def test_the_event_account_is_shared_across_companies(self):
        # A per-company account would split one show in two and defeat the
        # whole point: ARKA's revenue and AIM's cost must meet on one account.
        self.assertFalse(self._sale()._custom_event_analytic_account().company_id)

    def test_retyped_spacing_and_case_still_resolve_to_one_account(self):
        account = self._sale()._custom_event_analytic_account()
        retyped = self._sale(
            x_custom_event_name="SOEKARNO   CUP",
            x_custom_event_location="stadion gelora bung tomo surabaya",
        )
        self.assertEqual(retyped._custom_event_analytic_account(), account)

    def test_a_different_show_date_is_a_different_event(self):
        first = self._sale()._custom_event_analytic_account()
        second = self._sale(x_custom_show_date=date(2026, 9, 30))._custom_event_analytic_account()
        self.assertNotEqual(first, second)

    def test_confirming_a_sale_tags_its_lines(self):
        sale = self._sale()
        sale.action_confirm()
        account = self._account_of(sale)
        self.assertTrue(account)
        self.assertEqual(sale.order_line.analytic_distribution, {str(account.id): 100.0})

    def test_confirming_a_purchase_tags_its_lines(self):
        purchase = self._purchase()
        purchase.button_confirm()
        account = self._account_of(purchase)
        self.assertEqual(purchase.order_line.analytic_distribution, {str(account.id): 100.0})

    def test_a_manual_split_across_events_is_never_overwritten(self):
        sale = self._sale()
        other = self.env["account.analytic.account"].create(
            {"name": "Split by hand", "plan_id": self.env.ref("custom_arka_show_date.analytic_plan_arka_event").id}
        )
        sale.order_line.analytic_distribution = {str(other.id): 100.0}
        sale.action_confirm()
        self.assertEqual(sale.order_line.analytic_distribution, {str(other.id): 100.0})

    def test_tagging_is_inert_until_the_company_opts_in(self):
        self.buyer.x_custom_event_tracking_enabled = False
        sale = self._sale()
        sale.action_confirm()
        self.assertFalse(sale.order_line.analytic_distribution)
        with self.assertRaises(UserError):
            sale.action_custom_event_apply_analytic()

    def test_tag_event_button_on_a_bill_tags_only_the_product_lines(self):
        bill = (
            self.env["account.move"]
            .with_company(self.buyer)
            .sudo()
            .create(
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": self.show,
                    "x_custom_show_date": self.show,
                    "x_custom_event_name": "Soekarno Cup",
                    "x_custom_event_location": "Stadion Gelora Bung Tomo Surabaya",
                    "invoice_line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": 100.0})],
                }
            )
        )
        bill.action_custom_event_apply_analytic()
        account = self._account_of(bill)
        product_lines = bill.line_ids.filtered(lambda line: line.display_type == "product")
        self.assertTrue(product_lines)
        self.assertEqual(product_lines.analytic_distribution, {str(account.id): 100.0})
        # The payable counterpart must stay untagged or the event doubles up.
        payable = bill.line_ids.filtered(lambda line: line.display_type == "payment_term")
        self.assertFalse(any(payable.mapped("analytic_distribution")))

    # ------------------------------------------------------------------
    # Layer 2 — the purchase order raised from the sale
    # ------------------------------------------------------------------
    def test_purchase_raised_from_the_sale_inherits_the_event(self):
        sale = self._sale()
        sale.action_confirm()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(purchase.partner_id, self.seller.partner_id)
        self.assertEqual(purchase.company_id, self.buyer)
        self.assertEqual(purchase.state, "draft")
        self.assertEqual(purchase.x_custom_show_date, self.show)
        self.assertEqual(purchase.x_custom_event_name, "Soekarno Cup")
        self.assertEqual(purchase.x_custom_event_location, "Stadion Gelora Bung Tomo Surabaya")
        self.assertEqual(purchase.x_custom_event_source_so_id, sale)
        self.assertEqual(purchase.order_line.product_id, self.product)
        self.assertEqual(purchase.order_line.product_qty, 2)
        self.assertEqual(sale.x_custom_event_po_count, 1)

    def test_purchase_raised_from_the_sale_is_tagged_with_the_event(self):
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        account = self._account_of(sale)
        self.assertEqual(purchase.order_line.analytic_distribution, {str(account.id): 100.0})

    def test_purchase_price_is_not_the_customer_price(self):
        # AIM's cost is not ARKA's margin: the line price comes from the
        # vendor's own supplier info, not from the sale.
        sale = self._sale()
        sale.order_line.price_unit = 999_999.0
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertNotEqual(purchase.order_line.price_unit, 999_999.0)

    def test_no_intercompany_rule_says_so_plainly(self):
        self.rule.active = False
        sale = self._sale()
        self.assertFalse(sale.x_custom_ic_purchase_available)
        with self.assertRaises(UserError):
            sale.action_custom_create_ic_purchase_order()

    # ------------------------------------------------------------------
    # The sister company reads the event as data, not as a note
    # ------------------------------------------------------------------
    def test_the_mirrored_sale_carries_the_event_fields(self):
        purchase = self._purchase()
        purchase.button_confirm()
        purchase.invalidate_recordset()
        mirror = purchase.x_custom_ic_mirror_so_id
        self.assertTrue(mirror, "the intercompany mirror did not run")
        self.assertEqual(mirror.company_id, self.seller)
        self.assertEqual(mirror.x_custom_show_date, self.show)
        self.assertEqual(mirror.x_custom_event_name, "Soekarno Cup")
        self.assertEqual(mirror.x_custom_event_location, "Stadion Gelora Bung Tomo Surabaya")

    def test_the_mirrored_sale_lands_on_the_same_event_account(self):
        purchase = self._purchase()
        purchase.button_confirm()
        purchase.invalidate_recordset()
        mirror = purchase.x_custom_ic_mirror_so_id
        account = self._account_of(purchase)
        self.assertEqual(mirror.order_line.analytic_distribution, {str(account.id): 100.0})

    # ------------------------------------------------------------------
    # Reading it back: Profit & Loss per Event
    # ------------------------------------------------------------------
    def test_profit_loss_per_event_has_a_column_for_the_event(self):
        account = self._sale()._custom_event_analytic_account()
        report = self.env["custom.report.profit.loss.event"].with_company(self.buyer)
        columns = report._branch_columns()
        self.assertEqual(columns[0][:2], (report.HQ_KEY, "Unassigned"))
        self.assertIn(account.id, [analytic_id for _key, _label, analytic_id in columns])

    def test_profit_loss_per_event_reads_the_event_plan_not_the_branch_plan(self):
        report = self.env["custom.report.profit.loss.event"]
        self.assertEqual(
            report._branch_plan(),
            self.env.ref("custom_arka_show_date.analytic_plan_arka_event"),
        )

    def test_tagging_survives_auto_locked_sales_orders(self):
        """prd_arkaaim confirms straight into a locked order.

        With "Auto Lock Confirmed Sales Orders" on, core refuses every write to
        the lines of a confirmed order — so the event has to be stamped while
        the order is still a draft.
        """
        # Auto-lock is a FEATURE flag, not a per-user right: core asks
        # res.groups._is_feature_enabled(), which reads what base.group_user
        # implies. Granting the group to the test user alone changes nothing.
        self.env.ref("base.group_user").implied_ids |= self.env.ref("sale.group_auto_done_setting")
        sale = self._sale()
        sale.action_confirm()
        self.assertTrue(sale.locked, "the order should have auto-locked")
        account = self._account_of(sale)
        self.assertEqual(sale.order_line.analytic_distribution, {str(account.id): 100.0})

    def test_a_product_the_sister_cannot_sell_is_flagged_on_the_purchase(self):
        """The mirror will fail on a company-restricted product — say so early.

        In prd_arkaaim every PO that mirrored used a company-less product, and
        the ones that failed used a product scoped to ARKA.
        """
        self.product.company_id = self.buyer
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        bodies = purchase.message_ids.mapped("body")
        self.assertTrue(
            any(self.product.display_name in (body or "") for body in bodies),
            "the buyer was not warned that the mirror cannot carry this product",
        )

    def test_no_warning_when_every_product_is_shared(self):
        self.product.company_id = False
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertFalse(
            any("cannot put them on the mirrored" in (body or "") for body in purchase.message_ids.mapped("body"))
        )

    # ------------------------------------------------------------------
    # Sale product vs purchase product ("Jasa" sold, "Sewa" bought)
    # ------------------------------------------------------------------
    def _rental_twin(self):
        return self.env["product.product"].create(
            {"name": "Sewa Drone Show 250 Unit", "type": "service", "purchase_ok": True}
        )

    def test_purchase_order_carries_the_paired_product(self):
        rental = self._rental_twin()
        self.product.product_tmpl_id.x_custom_ic_purchase_product_id = rental
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(purchase.order_line.product_id, rental)
        # The sale still sells what it sold.
        self.assertEqual(sale.order_line.product_id, self.product)

    def test_quantities_and_the_event_survive_the_swap(self):
        rental = self._rental_twin()
        self.product.product_tmpl_id.x_custom_ic_purchase_product_id = rental
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(purchase.order_line.product_qty, 2)
        self.assertEqual(purchase.order_line.product_uom_id, rental.uom_id)
        self.assertEqual(purchase.x_custom_event_name, "Soekarno Cup")
        account = self._account_of(sale)
        self.assertEqual(purchase.order_line.analytic_distribution, {str(account.id): 100.0})

    def test_an_unpaired_product_is_still_bought_as_itself(self):
        sale = self._sale()
        action = sale.action_custom_create_ic_purchase_order()
        purchase = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(purchase.order_line.product_id, self.product)

    def test_a_product_cannot_be_purchased_as_itself(self):
        with self.assertRaises(ValidationError):
            self.product.product_tmpl_id.x_custom_ic_purchase_product_id = self.product

    def test_the_pairing_is_resolved_one_hop_only(self):
        """A -> B -> C must buy B, never walk on to C."""
        middle = self._rental_twin()
        far = self.env["product.product"].create(
            {"name": "Sewa Something Else", "type": "service", "purchase_ok": True}
        )
        middle.product_tmpl_id.x_custom_ic_purchase_product_id = far
        self.product.product_tmpl_id.x_custom_ic_purchase_product_id = middle
        self.assertEqual(self.product._custom_ic_purchase_product(), middle)

    # ------------------------------------------------------------------
    # Overhead allocation
    # ------------------------------------------------------------------
    def _overhead_bill(self, amount=100.0, ref="Payroll"):
        """A posted expense with nothing tying it to a show."""
        bill = (
            self.env["account.move"]
            .with_company(self.buyer)
            .sudo()
            .create(
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": self.show,
                    "date": self.show,
                    "ref": ref,
                    "invoice_line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": amount})],
                }
            )
        )
        bill.action_post()
        return bill

    def _post_revenue(self, event_account, amount):
        """Revenue booked straight onto an event, as the event chain would."""
        invoice = (
            self.env["account.move"]
            .with_company(self.buyer)
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": self.show,
                    "date": self.show,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": 1,
                                "price_unit": amount,
                                "analytic_distribution": {str(event_account.id): 100.0},
                            },
                        )
                    ],
                }
            )
        )
        invoice.action_post()
        return invoice

    def _allocation(self, **overrides):
        vals = {
            "name": "Overhead test",
            "company_id": self.buyer.id,
            "date_from": self.show.replace(day=1),
            "date_to": self.show,
            "basis": "equal",
        }
        vals.update(overrides)
        return self.env["custom.arka.event.allocation"].sudo().create(vals)

    def _two_events(self):
        first = self._sale()._custom_event_analytic_account()
        second = self._sale(x_custom_event_name="Second Show")._custom_event_analytic_account()
        return first, second

    def _assert_period_holds_only(self, allocation, events):
        """Guard the fixture: the period must contain our events and no others.

        Event analytic accounts are shared across companies, so a clone of a
        tenant database brings that tenant's shows along. If one ever lands in
        the test period, the split changes and the failure should say why.
        """
        self.assertEqual(
            set(allocation._events().ids),
            set(events.ids if hasattr(events, "ids") else [event.id for event in events]),
            "another event fell into the test period",
        )

    def test_equal_basis_splits_overhead_between_the_events_of_the_period(self):
        first, second = self._two_events()
        bill = self._overhead_bill()
        allocation = self._allocation()
        self._assert_period_holds_only(allocation, [first, second])
        allocation.action_compute()
        self.assertEqual(sum(allocation.line_ids.mapped("percentage")), 100.0)
        allocation.action_apply()
        line = bill.line_ids.filtered(lambda aml: aml.display_type == "product")
        self.assertEqual(line.analytic_distribution, {str(first.id): 50.0, str(second.id): 50.0})
        self.assertEqual(line.x_custom_event_allocation_id, allocation)
        self.assertEqual(allocation.state, "applied")

    def test_percentages_always_add_up_to_one_hundred(self):
        """Three events cannot be split into three clean thirds."""
        first = self._sale()._custom_event_analytic_account()
        second = self._sale(x_custom_event_name="Second Show")._custom_event_analytic_account()
        third = self._sale(x_custom_event_name="Third Show")._custom_event_analytic_account()
        self._overhead_bill()
        allocation = self._allocation()
        self._assert_period_holds_only(allocation, [first, second, third])
        allocation.action_compute()
        self.assertEqual(len(allocation.line_ids), 3)
        self.assertEqual(sum(allocation.line_ids.mapped("percentage")), 100.0)

    def test_reset_takes_back_exactly_what_it_wrote(self):
        self._two_events()
        bill = self._overhead_bill()
        allocation = self._allocation()
        allocation.action_compute()
        allocation.action_apply()
        allocation.action_reset()
        line = bill.line_ids.filtered(lambda aml: aml.display_type == "product")
        self.assertFalse(line.analytic_distribution)
        self.assertFalse(line.x_custom_event_allocation_id)
        self.assertEqual(allocation.state, "draft")

    def test_a_line_a_document_already_attributed_is_never_touched(self):
        first, _second = self._two_events()
        bill = self._overhead_bill()
        line = bill.line_ids.filtered(lambda aml: aml.display_type == "product")
        line.analytic_distribution = {str(first.id): 100.0}
        allocation = self._allocation()
        allocation.action_compute()
        with self.assertRaises(UserError):
            allocation.action_apply()  # nothing left to allocate
        self.assertEqual(line.analytic_distribution, {str(first.id): 100.0})
        self.assertFalse(line.x_custom_event_allocation_id)

    def test_revenue_basis_follows_what_each_event_earned(self):
        first, second = self._two_events()
        # Two thirds of the revenue on the first event, one third on the second.
        self._post_revenue(first, 2000.0)
        self._post_revenue(second, 1000.0)
        self._overhead_bill()
        allocation = self._allocation(basis="revenue")
        allocation.action_compute()
        shares = {line.analytic_account_id: line.percentage for line in allocation.line_ids}
        self.assertAlmostEqual(shares[first], 66.67, places=2)
        self.assertAlmostEqual(shares[second], 33.33, places=2)

    def test_a_period_with_no_event_refuses_rather_than_guesses(self):
        self._overhead_bill()
        allocation = self._allocation(date_from="2020-01-01", date_to="2020-01-31")
        with self.assertRaises(UserError):
            allocation.action_compute()

    def test_allocated_cost_never_becomes_the_basis_of_the_next_allocation(self):
        """Otherwise a second run would feed on the first one's output."""
        first, second = self._two_events()
        self._post_revenue(first, 1000.0)
        self._post_revenue(second, 1000.0)
        self._overhead_bill(amount=500.0)
        allocation = self._allocation(basis="equal")
        allocation.action_compute()
        allocation.action_apply()
        second_run = self._allocation(name="Second run", basis="direct_cost")
        weights = second_run._basis_amounts(second_run._events())
        allocated = self.env["account.move.line"].search([("x_custom_event_allocation_id", "=", allocation.id)])
        self.assertTrue(allocated, "the first run should have allocated something")
        self.assertEqual(set(weights.values()), {0.0}, "allocated cost leaked into the basis")
