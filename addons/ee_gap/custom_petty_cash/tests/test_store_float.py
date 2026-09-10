# -*- coding: utf-8 -*-
"""Store float: the 1jt revolving balance a store draws its spends from.

Everything here is the 0.6.0 behaviour requested by Finance:

* a store's Petty Cash Awal cannot exceed its plafon;
* a Realisasi reserves the full requested amount **from draft**;
* no Realisasi is possible before the store has an approved float;
* realizing frees exactly what was realized ("saldo pulih sesuai nilai yang
  direalisasikan"), and closing the request releases the remainder;
* a Claim is the escape hatch and is *not* gated by the float.
"""

from odoo.exceptions import UserError

from .common import PettyCashCommon


class TestStoreFloat(PettyCashCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Type = cls.env["petty.cash.type"]
        accounting = {
            "company_id": cls.company.id,
            "advance_account_id": cls.advance_pc.id,
            "bank_out_journal_id": cls.cash_journal.id,
            "payment_journal_id": cls.pay_journal.id,
            "expense_journal_id": cls.gen_journal.id,
        }
        cls.type_initial = Type.create(dict(accounting, name="Petty Cash Awal", code="PCA", kind="pc_initial"))
        cls.type_realization = Type.create(dict(accounting, name="Realisasi", code="PCR", kind="pc_realization"))
        cls.type_claim = Type.create(dict(accounting, name="Claim", code="PCC", kind="pc_claim"))

        plan = cls.env["account.analytic.plan"].create({"name": "Operating Unit"})
        cls.env["ir.config_parameter"].sudo().set_param("custom_petty_cash.ou_plan_name", "Operating Unit")
        cls.env["ir.config_parameter"].sudo().set_param("custom_petty_cash.initial_amount", "1000000")
        cls.store = cls.env["account.analytic.account"].create({"name": "Toko A", "plan_id": plan.id})
        cls.store_b = cls.env["account.analytic.account"].create({"name": "Toko B", "plan_id": plan.id})

    # ------------------------------------------------------------------
    def _request(self, advance_type, amount, store=None):
        return self.env["petty.cash.request"].create(
            {
                "employee_id": self.employee.id,
                "advance_type_id": advance_type.id,
                "l10n_ou_analytic_id": (store or self.store).id,
                "amount_requested": amount,
                "purpose": "Float test",
            }
        )

    def _grant_float(self, amount=1000000.0, store=None):
        """Approve a Petty Cash Awal, which is what materialises the float."""
        initial = self._request(self.type_initial, amount, store=store)
        initial.action_submit()
        initial.action_approve()
        return initial

    def _realize(self, request, amount):
        realization = self.env["petty.cash.realization"].create(
            {
                "request_id": request.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "line_type": "expense",
                            "name": "Beli ATK",
                            "account_id": self.expense.id,
                            "price_unit": amount,
                            "quantity": 1.0,
                        },
                    )
                ],
            }
        )
        realization.action_post()
        return realization

    # ------------------------------------------------------------------
    def test_initial_request_capped_at_plafon(self):
        """The plafon Finance sets is a hard ceiling on Petty Cash Awal."""
        with self.assertRaises(UserError):
            self._request(self.type_initial, 1500000.0)

    def test_initial_grants_float_only_once_approved(self):
        initial = self._request(self.type_initial, 1000000.0)
        self.assertFalse(initial.float_id, "no float should exist before approval")
        initial.action_submit()
        initial.action_approve()
        self.assertTrue(initial.float_id)
        self.assertEqual(initial.float_id.amount_granted, 1000000.0)
        self.assertEqual(initial.float_id.amount_available, 1000000.0)

    def test_second_initial_cannot_exceed_remaining_plafon(self):
        self._grant_float(1000000.0)
        with self.assertRaises(UserError):
            self._request(self.type_initial, 1.0)

    def test_realization_requires_a_granted_float(self):
        with self.assertRaises(UserError):
            self._request(self.type_realization, 100000.0)

    def test_draft_realization_already_reserves(self):
        """ "Mulai draft sudah dihitung sebagai outstanding.\""""
        initial = self._grant_float()
        usage = self._request(self.type_realization, 300000.0)
        self.assertEqual(usage.state, "draft")
        self.assertEqual(usage.amount_float_consumed, 300000.0)
        self.assertEqual(initial.float_id.amount_available, 700000.0)

    def test_reservation_cannot_exceed_available(self):
        self._grant_float()
        self._request(self.type_realization, 900000.0)
        with self.assertRaises(UserError):
            self._request(self.type_realization, 200000.0)

    def test_realizing_restores_exactly_what_was_realized(self):
        """300 reserved, 250 realized -> available climbs 700 -> 950."""
        initial = self._grant_float()
        usage = self._request(self.type_realization, 300000.0)
        usage.action_submit()
        usage.action_approve()
        self.assertEqual(initial.float_id.amount_available, 700000.0)
        self._realize(usage, 250000.0)
        self.assertEqual(usage.amount_realized, 250000.0)
        self.assertEqual(usage.amount_float_consumed, 50000.0)
        self.assertEqual(initial.float_id.amount_available, 950000.0)

    def test_closing_releases_the_unrealized_remainder(self):
        initial = self._grant_float()
        usage = self._request(self.type_realization, 300000.0)
        usage.action_submit()
        usage.action_approve()
        self._realize(usage, 250000.0)
        usage.action_close_release()
        self.assertEqual(usage.state, "settled")
        self.assertEqual(usage.amount_float_consumed, 0.0)
        self.assertEqual(initial.float_id.amount_available, 1000000.0)

    def test_realization_needs_no_disbursement(self):
        """The cash is already in the store's drawer — approval is enough."""
        self._grant_float()
        usage = self._request(self.type_realization, 100000.0)
        usage.action_submit()
        usage.action_approve()
        self.assertEqual(usage.state, "approved")
        self.assertIn("approved", usage._pc_realizable_states())
        self._realize(usage, 100000.0)
        self.assertEqual(usage.state, "in_realization")

    def test_claim_bypasses_the_float(self):
        """A Claim is precisely the spend the float cannot cover."""
        initial = self._grant_float()
        self._request(self.type_realization, 1000000.0)
        self.assertEqual(initial.float_id.amount_available, 0.0)
        claim = self._request(self.type_claim, 750000.0)
        self.assertEqual(claim.amount_float_consumed, 0.0)
        self.assertEqual(initial.float_id.amount_available, 0.0)

    def test_cancelling_frees_the_reservation(self):
        initial = self._grant_float()
        usage = self._request(self.type_realization, 400000.0)
        self.assertEqual(initial.float_id.amount_available, 600000.0)
        usage.action_cancel()
        self.assertEqual(initial.float_id.amount_available, 1000000.0)

    def test_floats_are_per_store(self):
        self._grant_float(store=self.store)
        with self.assertRaises(UserError):
            self._request(self.type_realization, 100000.0, store=self.store_b)

    def test_legacy_kinds_are_untouched(self):
        """The six tenants already on CA/PC types must not see the float at all."""
        request = self._full_cycle(1000.0, self.type_ca)
        self.assertFalse(request.float_id)
        self.assertEqual(request.amount_float_consumed, 0.0)
        self.assertEqual(request.amount_float_granted, 0.0)
