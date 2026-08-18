# -*- coding: utf-8 -*-
"""Report VAT — the PPN ledger the Tax team pulls, in the Otomotif layout.

WHAT THIS IS
------------
ARKA-AIM asked for "Invoice PPN, ikutin Otomotif" (go-live sheet item 2). The
reference pull they attached is a *ledger of the VAT accounts*, not a per-faktur
summary: every posted move line that touches VAT In / VAT Out, in date order,
with a running balance per account, enriched with the faktur-pajak number and
the counterparty. Header reads "Rincian Buku Besar / REPORT VAT / Dari … s/d …".

That is a different report from :class:`custom.report.faktur.pajak`, which
answers a different question — one row per invoice, DPP and PPN side by side,
feeding SPT 1111. Both are wanted; neither replaces the other.

WHICH ACCOUNTS COUNT AS VAT
---------------------------
Never hardcoded. The accounts are derived from the tax repartition lines of
every sale/purchase tax on the selected companies, minus withholding: a tax
whose name starts with ``PPH`` is PPh, not PPN — the same convention
``custom.report.faktur.pajak._ppn_tax_ids`` and ``custom.report.tax._classify``
already use. On prd_arkaaim this resolves to 1117200001 (VAT In) and 2104300001
(VAT Out), which happen to be the very codes in the client's reference file.

An account the user picks explicitly in the wizard still wins: the two sets are
intersected, so "only VAT Out" is a normal account filter and not a special case.

COLUMN MAPPING, AND WHERE IT IS AN INTERPRETATION
-------------------------------------------------
The reference comes from a different ERP, which numbers a GL voucher separately
from the source document. Odoo has one ``account.move`` carrying one name, so
three reference columns are mapped rather than copied:

===========================  ==================================================
Reference column             Odoo source
===========================  ==================================================
No Bukti #                   ``move.name`` — the journal entry itself
No. Trans #                  ``move.invoice_origin`` else ``move.name``
No Referensi                 ``move.ref`` — vendor's own document number
No Faktur Pajak              ``move.x_custom_nsfp`` (blank without custom_coretax)
Nama Pemasok                 commercial partner of the line
Tipe Transaksi               derived from ``move.move_type``
===========================  ==================================================

If Tax wants No. Trans # to carry something else, that is a one-line change in
:py:meth:`_transaction_no` — the mapping is deliberately isolated there.

LAYOUT
------
Flat table, ordered by account then date, exactly as the reference: the account
code and name repeat on every row rather than becoming section headings. The
running balance restarts per account and opens from the balance carried before
``date_from``, so a mid-year pull still reconciles to the GL.
"""

from __future__ import annotations

from datetime import date as date_cls, timedelta

from odoo import models


# move_type -> the Indonesian transaction label the reference uses.
_TIPE_TRANSAKSI = {
    "in_invoice": "Faktur Pembelian",
    "in_refund": "Nota Retur Pembelian",
    "out_invoice": "Faktur Penjualan",
    "out_refund": "Nota Retur Penjualan",
    "in_receipt": "Bukti Penerimaan",
    "out_receipt": "Bukti Pengeluaran",
    "entry": "Jurnal Umum",
}


class CustomReportVat(models.AbstractModel):
    _name = "custom.report.vat"
    _inherit = "custom.report.engine"
    _description = "Report VAT (Rincian Buku Besar PPN)"

    _report_code = "report_vat"
    _report_title = "Report VAT"

    # ------------------------------------------------------------------
    # Which accounts
    # ------------------------------------------------------------------
    def _vat_account_ids(self, company_ids, vat_side="both"):
        """Accounts posted to by PPN taxes, derived from tax repartition.

        ``vat_side``: ``both`` (default), ``masukan`` (purchase) or
        ``keluaran`` (sale).
        """
        type_tax_use = {
            "masukan": ["purchase"],
            "keluaran": ["sale"],
        }.get(vat_side, ["sale", "purchase"])

        taxes = self.env["account.tax"].search(
            [
                ("type_tax_use", "in", type_tax_use),
                ("company_id", "in", list(company_ids) or [self.env.company.id]),
            ]
        )
        # A tax named "PPh …" is withholding — its account is not a VAT account.
        ppn_taxes = taxes.filtered(lambda t: not (t.name or "").upper().startswith("PPH"))
        if not ppn_taxes:
            return []
        rep_lines = self.env["account.tax.repartition.line"].search(
            [("tax_id", "in", ppn_taxes.ids), ("account_id", "!=", False)]
        )
        return sorted(set(rep_lines.mapped("account_id").ids))

    # ------------------------------------------------------------------
    # Column mapping (isolated on purpose — see module docstring)
    # ------------------------------------------------------------------
    def _transaction_no(self, move):
        if not move:
            return ""
        return self._opt(move, "invoice_origin") or move.name or ""

    def _tipe_transaksi(self, move):
        if not move:
            return ""
        return _TIPE_TRANSAKSI.get(move.move_type, "Jurnal Umum")

    # ------------------------------------------------------------------
    # XLSX layout (generic flat body renders these)
    # ------------------------------------------------------------------
    def _xlsx_columns(self):
        return [
            {"header": "Kode Perkiraan", "field": "account_code", "kind": "text", "width": 16},
            {"header": "Nama", "field": "account_name", "kind": "text", "width": 18},
            {"header": "No Bukti #", "field": "doc_no", "kind": "text", "width": 22},
            {"header": "No. Trans #", "field": "trans_no", "kind": "text", "width": 22},
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "Tipe Transaksi", "field": "tipe", "kind": "text", "width": 18},
            {"header": "Keterangan", "field": "label", "kind": "text", "width": 46},
            {"header": "Debit", "field": "debit", "kind": "number", "width": 18},
            {"header": "Kredit", "field": "credit", "kind": "number", "width": 18},
            {"header": "Saldo Akhir", "field": "balance", "kind": "number", "width": 20},
            {"header": "No Referensi", "field": "reference", "kind": "text", "width": 22},
            {"header": "No Faktur Pajak", "field": "faktur", "kind": "text", "width": 24},
            {"header": "Nama Pemasok", "field": "partner", "kind": "text", "width": 32},
        ]

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _opening_balance_per_account(self, filters):
        """Cumulative balance per account *before* ``date_from``.

        Same idea as the General Ledger's opening: without it a pull that starts
        mid-year shows a running balance that begins at zero and reconciles to
        nothing.
        """
        opening_filters = dict(
            filters,
            date_from=date_cls(1970, 1, 1),
            date_to=filters["date_from"] - timedelta(days=1),
        )
        per_account = self._get_account_balances(filters=opening_filters)
        return {aid: row["balance"] for aid, row in per_account.items()}

    def _build_lines(self, filters):
        vat_ids = self._vat_account_ids(filters["company_ids"], filters.get("vat_side") or "both")
        if not vat_ids:
            return []

        chosen = filters.get("account_ids")
        if chosen:
            # An explicit account filter narrows the VAT set, never widens it.
            vat_ids = [aid for aid in vat_ids if aid in set(chosen)]
            if not vat_ids:
                return []

        scoped = dict(filters, account_ids=vat_ids)
        opening_by_account = self._opening_balance_per_account(scoped)

        query, params = self._get_move_lines_query(scoped)
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        # Batched reads — one browse per model, not one per row.
        accounts = {
            a.id: a for a in self.env["account.account"].browse(sorted({r["account_id"] for r in rows}))
        }
        moves = {
            m.id: m for m in self.env["account.move"].browse(sorted({r["move_id"] for r in rows if r["move_id"]}))
        }
        partners = {
            p.id: p for p in self.env["res.partner"].browse(sorted({r["partner_id"] for r in rows if r["partner_id"]}))
        }

        # The SQL orders by account *id*; the reference groups by account *code*.
        # With two companies the same code exists twice (one account record per
        # company), so ids interleave VAT In / VAT Out and the sheet reads
        # scrambled. Re-sort on the resolved code, keeping each company's own
        # account as its own block.
        code_by_account = {aid: self._account_code(acc) for aid, acc in accounts.items()}
        rows.sort(
            key=lambda r: (
                code_by_account.get(r["account_id"]) or "",
                r["account_id"],
                r["date"],
                r["id"],
            )
        )

        lines = []
        running = {}
        grand_debit = grand_credit = 0.0

        for row in rows:
            aid = row["account_id"]
            account = accounts.get(aid)
            if not account:
                continue
            move = moves.get(row["move_id"])
            partner = partners.get(row["partner_id"])
            if partner:
                partner = partner.commercial_partner_id or partner

            debit = row["debit"] or 0.0
            credit = row["credit"] or 0.0
            if aid not in running:
                running[aid] = opening_by_account.get(aid, 0.0)
            running[aid] += debit - credit

            lines.append(
                {
                    "account_id": aid,
                    "account_code": code_by_account.get(aid) or self._account_code(account),
                    "account_name": account.name or "",
                    "doc_no": (move.name if move else "") or "/",
                    "trans_no": self._transaction_no(move),
                    "date": row["date"],
                    "tipe": self._tipe_transaksi(move),
                    "label": row["name"] or (move.ref if move else "") or "",
                    "debit": debit,
                    "credit": credit,
                    "balance": running[aid],
                    "reference": (move.ref if move else "") or "",
                    "faktur": self._opt(move, "x_custom_nsfp"),
                    "partner": partner.display_name if partner else "",
                }
            )
            grand_debit += debit
            grand_credit += credit

        if lines:
            # ``balance`` is a running figure per account, so a grand total on it
            # would be meaningless — left blank on purpose.
            lines.append(
                {
                    "type": "grand_total",
                    "label": "TOTAL",
                    "account_code": "TOTAL",
                    "debit": grand_debit,
                    "credit": grand_credit,
                }
            )
        return lines
