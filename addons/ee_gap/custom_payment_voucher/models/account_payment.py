# -*- coding: utf-8 -*-
"""Payment Voucher / Payment Receipt helpers on ``account.payment``.

The printout renders a payment as an accounting voucher: a meta header (voucher
number + source bank), the payment's own journal entry as a COA / DEBIT /
CREDIT table with the reconciled AP/AR document and counterparty invoice
reference per line, the amount in words, and the counterparty bank block. The
same body serves both directions — outbound prints as "Payment Voucher",
inbound as "Payment Receipt".

Tenant-neutral extraction of ``custom_levis_localization/models/account_payment.py``.
The Operating-Unit stamping of the original is deliberately left out: it depends
on a Levi's analytic plan. Field prefix is ``pv_`` so both modules could, in
principle, sit on one database without a name clash.
"""

from __future__ import annotations

from odoo import api, fields, models

from .terbilang import terbilang_id

_INVOICE_TYPES = ("in_invoice", "in_refund", "out_invoice", "out_refund")


class AccountPayment(models.Model):
    _inherit = "account.payment"

    pv_note = fields.Char(string="Note", copy=False)
    pv_remark = fields.Char(string="Remark", copy=False)
    pv_override_outstanding_account_id = fields.Many2one(
        "account.account",
        string="Override Outstanding Account",
        copy=False,
        check_company=True,
        help="When set, overrides the outstanding (liquidity) account on the "
        "posted payment instead of the one from the payment method line.",
    )

    # -- Outstanding-account override (impacts the posted GL) --------------
    # Re-declaring @api.depends REPLACES the inherited set, so the base trigger
    # (payment_method_line_id) is relisted alongside the override field.
    @api.depends("payment_method_line_id", "pv_override_outstanding_account_id")
    def _compute_outstanding_account_id(self):
        super()._compute_outstanding_account_id()
        for pay in self:
            if pay.pv_override_outstanding_account_id:
                pay.outstanding_account_id = pay.pv_override_outstanding_account_id.id

    # ------------------------------------------------------------------
    # Source document (reconciled bill/invoice) behind a journal line
    # ------------------------------------------------------------------
    def _pv_line_source_doc(self, line):
        """The invoice/bill this line is reconciled against, if any.

        ``matched_debit_ids`` holds the partials where ``line`` is the CREDIT
        side, so the counterpart is ``debit_move_id`` — and the other way round
        for ``matched_credit_ids``. Core reads them the same way in
        ``_compute_reconciled_lines_ids``. Reading the near side instead just
        returns ``line`` itself, and every voucher row then falls back to the
        payment's own number instead of showing the bill.
        """
        counterparts = line.matched_debit_ids.mapped("debit_move_id.move_id")
        counterparts |= line.matched_credit_ids.mapped("credit_move_id.move_id")
        bills = counterparts.filtered(lambda m: m.move_type in _INVOICE_TYPES)
        return bills[:1]

    def _pv_voucher_rows(self):
        """One dict per journal item of the payment's move — the voucher table."""
        self.ensure_one()
        rows = []
        move = self.move_id
        if not move:
            return rows
        lines = move.line_ids.filtered(lambda l: l.display_type not in ("line_section", "line_note"))
        for line in lines:
            src = self._pv_line_source_doc(line)
            orig = abs(line.amount_currency) if line.amount_currency else abs(line.balance)
            rate = 1.0
            if line.amount_currency and line.balance:
                rate = abs(line.balance) / abs(line.amount_currency)
            rows.append(
                {
                    "coa": line.account_id.name or line.name or "",
                    "desc": line.name or "",
                    "doc_ap": (src.name if src else self.name) or "",
                    "ref_vendor": (src.ref if src else (self.payment_reference or self.memo or "")) or "",
                    "vendor": (line.partner_id or self.partner_id).name or "",
                    "currency": self.currency_id.name or "",
                    "orig_amount": orig,
                    "rate": rate,
                    "debit": line.debit,
                    "credit": line.credit,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Counterparty bank block
    # ------------------------------------------------------------------
    def _pv_recipient_bank(self):
        self.ensure_one()
        bank = self.partner_bank_id
        return {
            "bank_name": bank.bank_id.name if bank else "",
            "acc_number": bank.acc_number if bank else "",
            "acc_holder": (bank.acc_holder_name or (bank.partner_id.name if bank else "")) if bank else "",
            "branch": (getattr(bank.bank_id, "street", "") or "") if bank else "",
            "swift": (bank.bank_id.bic or "") if bank else "",
        }

    def _pv_source_bank_account(self):
        """The company bank account funding the payment (header 'Account No.')."""
        self.ensure_one()
        acc = self.journal_id.bank_account_id
        if not acc:
            return ""
        parts = [acc.acc_number]
        if acc.bank_id:
            parts.append(acc.bank_id.name)
        return " - ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Amount in words
    # ------------------------------------------------------------------
    def _pv_amount_in_words(self):
        self.ensure_one()
        suffix = "Rupiah" if self.currency_id.name == "IDR" else (self.currency_id.currency_unit_label or "")
        return terbilang_id(self.amount, suffix=suffix)
