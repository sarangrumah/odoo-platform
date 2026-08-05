# -*- coding: utf-8 -*-
"""Shared fixture: a company with two advance types wired to their own accounts."""

from odoo.tests import TransactionCase


class PettyCashCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]

        def _acc(code, name, atype, reconcile=False):
            return Account.create({"code": code, "name": name, "account_type": atype, "reconcile": reconcile})

        # Two distinct advance accounts, mirroring the ARKA-AIM mapping:
        # cash advance = a receivable, petty cash = a prepayment.
        cls.advance_ca = _acc("PCT1001", "Uang Muka Karyawan", "asset_receivable", reconcile=True)
        cls.advance_pc = _acc("PCT1002", "Uang Muka Operasional", "asset_prepayments", reconcile=True)
        cls.bank_acc = _acc("PCT1101", "Bank Advance", "asset_cash")
        cls.cash_acc = _acc("PCT1102", "Kas Advance", "asset_cash")
        cls.expense = _acc("PCT6001", "Advance Expense", "expense")

        Journal = cls.env["account.journal"]
        cls.bank_journal = Journal.create(
            {"name": "CA Bank", "type": "bank", "code": "CABK", "default_account_id": cls.bank_acc.id}
        )
        cls.cash_journal = Journal.create(
            {"name": "CA Cash", "type": "cash", "code": "CACS", "default_account_id": cls.cash_acc.id}
        )
        # Dedicated: posting a third-party realization rewrites this journal's
        # payment-method outstanding accounts.
        cls.pay_journal = Journal.create(
            {"name": "CA Pay", "type": "cash", "code": "CAPY", "default_account_id": cls.bank_acc.id}
        )
        cls.gen_journal = Journal.create({"name": "CA Misc", "type": "general", "code": "CAMS"})

        Type = cls.env["petty.cash.type"]
        cls.type_ca = Type.create(
            {
                "name": "Cash Advance",
                "code": "CA",
                "kind": "cash_advance",
                "is_default": True,
                "company_id": cls.company.id,
                "advance_account_id": cls.advance_ca.id,
                "bank_out_journal_id": cls.bank_journal.id,
                "payment_journal_id": cls.pay_journal.id,
                "expense_journal_id": cls.gen_journal.id,
            }
        )
        cls.type_pc = Type.create(
            {
                "name": "Petty Cash",
                "code": "PC",
                "kind": "petty_cash",
                "company_id": cls.company.id,
                "advance_account_id": cls.advance_pc.id,
                "bank_out_journal_id": cls.cash_journal.id,
                "payment_journal_id": cls.pay_journal.id,
                "expense_journal_id": cls.gen_journal.id,
            }
        )

        cls.partner_emp = cls.env["res.partner"].create({"name": "Advance Holder"})
        cls.job = cls.env["hr.job"].create({"name": "CA Supervisor"})
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Advance Employee", "work_contact_id": cls.partner_emp.id, "job_id": cls.job.id}
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Toko ATK"})

    def _new_request(self, amount=1000.0, advance_type=None, currency=None):
        vals = {
            "employee_id": self.employee.id,
            "advance_type_id": (advance_type or self.type_ca).id,
            "amount_requested": amount,
            "purpose": "Verification",
        }
        if currency:
            vals["currency_id"] = currency.id
        return self.env["petty.cash.request"].create(vals)

    def _full_cycle(self, amount=1000.0, advance_type=None):
        request = self._new_request(amount, advance_type)
        request.action_submit()
        request.action_approve()
        request.action_disburse()
        return request
