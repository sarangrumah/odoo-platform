# -*- coding: utf-8 -*-
"""Rekap PPh Pemotongan per Jenis Penghasilan (PPh 23 / 4(2) / 26 / 22).

Reads ``account.move.withholding.line`` (populated on vendor-bill post by the
``custom_tax_id`` withholding engine), grouped by jenis PPh then jenis
penghasilan (``tax.withholding.category``). This is the granular working paper
behind the e-Bupot: it shows *which kind of income* was withheld, per lawan
transaksi, with DPP / tarif / PPh.

The source model is optional; when ``custom_tax_id`` is absent the report
degrades to an informational note.
"""

from __future__ import annotations

from datetime import date as date_cls

from odoo import _, models


_PPH_ORDER = ["pph_22", "pph_23", "pph_4_2", "pph_26", "pph_21"]
_PPH_LABEL = {
    "pph_21": "PPh 21",
    "pph_22": "PPh 22",
    "pph_23": "PPh 23",
    "pph_4_2": "PPh 4 ayat (2)",
    "pph_26": "PPh 26",
}


class CustomReportPphWithholding(models.AbstractModel):
    _name = "custom.report.pph.withholding"
    _inherit = "custom.report.engine"
    _description = "Rekap PPh Pemotongan per Jenis Penghasilan"

    _report_code = "pph_withholding"
    _report_title = "Rekap PPh Pemotongan (per Jenis Penghasilan)"

    def _xlsx_columns(self):
        return [
            {"header": "Tanggal", "field": "date", "kind": "date", "width": 12},
            {"header": "No. Dokumen", "field": "doc_no", "kind": "text", "width": 18},
            {"header": "No. Dokumen Jurnal", "field": "journal_no", "kind": "text", "width": 18},
            {"header": "No. Invoice", "field": "invoice_no", "kind": "text", "width": 18},
            {"header": "Tgl Invoice", "field": "invoice_date", "kind": "date", "width": 12},
            {"header": "NPWP/NIK", "field": "npwp", "kind": "text", "width": 20},
            {"header": "Lawan Transaksi", "field": "partner", "kind": "text", "width": 28},
            {"header": "Kode Objek Pajak", "field": "kode_objek", "kind": "text", "width": 14},
            {"header": "Jenis PPh", "field": "jenis_pph", "kind": "text", "width": 14},
            {"header": "Jenis Penghasilan", "field": "jenis_penghasilan", "kind": "text", "width": 26},
            {"header": "COA Expense", "field": "coa_expense", "kind": "text", "width": 30},
            {"header": "Sumber", "field": "sumber", "kind": "text", "width": 16},
            {"header": "DPP", "field": "dpp", "kind": "number", "width": 18},
            {"header": "Tarif (%)", "field": "tarif", "kind": "number", "width": 10},
            {"header": "PPh Dipotong", "field": "pph", "kind": "number", "width": 18},
        ]

    # ------------------------------------------------------------------
    # PPh booked outside the withholding engine
    # ------------------------------------------------------------------
    def _pph_account_kinds(self, company_ids):
        """Map each PPh payable account id -> pph_kind, from the configured rules.

        ``tax.withholding.rule.account_id`` is where each kode objek's Hutang
        PPh account is configured, and the category carries the pph_kind, so the
        chart itself tells us which article an account belongs to. No hardcoded
        account codes.
        """
        if "tax.withholding.rule" not in self.env:
            return {}
        rules = (
            self.env["tax.withholding.rule"]
            .sudo()
            .search([("company_id", "in", list(company_ids)), ("account_id", "!=", False)])
        )
        mapping = {}
        for rule in rules:
            kind = rule.category_id.pph_kind
            # An account shared by several articles keeps the first seen; the
            # per-article COA split means that does not happen in practice.
            mapping.setdefault(rule.account_id.id, kind)
        return mapping

    def _tax_base_splits(self, tax_line):
        """Base lines behind a PPh tax line, grouped by their Kode Objek PPh.

        The operator picks the kode objek on the *expense* line
        (``x_custom_withholding_category_id``) while the PPh itself lands on the
        tax line, so the recap has to walk back from the tax line to the lines it
        was computed on — reading the picker off the tax line always yielded a
        blank Kode Objek Pajak.

        Uncategorised base lines are kept as a group of their own so a bill that
        is only partly keyed still splits DPP and PPh proportionally instead of
        loading everything onto the one line that happens to carry a picker.
        Returns [] when nothing on the entry carries a picker, so the caller can
        fall back to a single unsplit row.
        """
        if not tax_line.tax_line_id:
            return []
        if "x_custom_withholding_category_id" not in self.env["account.move.line"]._fields:
            return []
        tax = tax_line.tax_line_id
        groups = {}
        for base in tax_line.move_id.line_ids:
            if base.tax_line_id or tax not in base.tax_ids:
                continue
            category = base.x_custom_withholding_category_id
            entry = groups.setdefault(
                category.id or 0,
                {"category": category, "base": 0.0, "account": base.account_id},
            )
            entry["base"] += abs(base.balance)
        if not any(g["category"] for g in groups.values()):
            return []
        return [g for g in groups.values() if g["base"]]

    def _move_category(self, move):
        """Any Kode Objek PPh picked on the entry, for rows without a tax line.

        A manual "Pemotongan PPh" journal entry has no tax line to walk back
        from, but the operator may still have keyed the kode objek on one of its
        lines.
        """
        if "x_custom_withholding_category_id" not in self.env["account.move.line"]._fields:
            return False
        for line in move.line_ids:
            if line.x_custom_withholding_category_id:
                return line.x_custom_withholding_category_id
        return False

    def _manual_pph_rows(self, filters):
        """Rows for PPh that never produced an ``account.move.withholding.line``.

        Accounting books PPh two other ways, and neither was visible here — the
        client's complaint "jurnal PPh yang sudah di input tidak muncul di Report
        Rekap PPh Pemotongan":

        * a **native PPh tax on a bill line** — the tax line carries the real
          ``tax_base_amount``, so DPP and tarif are exact.
        * a **manual journal entry** straight onto Hutang PPh — no DPP exists
          anywhere, so it is left blank rather than reverse-engineered from the
          rate, and the Sumber column says where the row came from.

        The engine's own "Pemotongan PPh" entries also credit these accounts, so
        they are excluded: their PPh is already reported from the withholding
        lines and would otherwise be counted twice.
        """
        acct_kinds = self._pph_account_kinds(filters["company_ids"])
        if not acct_kinds:
            return {}

        AML = self.env["account.move.line"].sudo()
        Move = self.env["account.move"].sudo()

        # Entries generated by the withholding engine — already represented.
        engine_move_ids = set()
        if "x_custom_withholding_move_id" in Move._fields:
            engine_move_ids = set(
                Move.search(
                    [
                        ("company_id", "in", list(filters["company_ids"])),
                        ("x_custom_withholding_move_id", "!=", False),
                    ]
                ).mapped("x_custom_withholding_move_id.id")
            )

        domain = [
            ("company_id", "in", list(filters["company_ids"])),
            ("account_id", "in", list(acct_kinds)),
            ("date", ">=", filters["date_from"]),
            ("date", "<=", filters["date_to"]),
        ]
        domain.append(
            ("parent_state", "=", "posted")
            if filters.get("posted_only", True)
            else ("parent_state", "in", ("draft", "posted"))
        )
        if filters.get("partner_ids"):
            domain.append(("move_id.partner_id", "in", filters["partner_ids"]))

        buckets = {}
        for ml in AML.search(domain):
            if ml.move_id.id in engine_move_ids:
                continue
            # Credit increases the liability to DJP; a debit is a settlement or
            # reversal and must not be reported as withholding.
            pph = (ml.credit or 0.0) - (ml.debit or 0.0)
            if pph <= 0:
                continue

            move = ml.move_id
            partner = move.commercial_partner_id or move.partner_id or ml.partner_id
            tax = ml.tax_line_id
            if tax:
                sumber = "Tax pada bill"
                dpp = ml.tax_base_amount or 0.0
                tarif = abs(tax.amount or 0.0)
                jenis = tax.name or ""
            else:
                sumber = "Jurnal manual"
                dpp = 0.0
                tarif = 0.0
                jenis = ml.name or ""

            # Largest debit line of the same entry is the expense being withheld,
            # used whenever the split below cannot name a better account.
            exp = move.line_ids.filtered(lambda l: l.debit > 0 and l.id != ml.id).sorted("debit", reverse=True)[:1]
            fallback_account = exp.account_id if exp else False

            # One row per Kode Objek Pajak keyed on the bill; a single row with
            # whatever the entry itself carries when there is nothing to split.
            splits = []
            groups = self._tax_base_splits(ml)
            total_base = sum(g["base"] for g in groups)
            if groups and total_base:
                left_dpp, left_pph = dpp, pph
                for idx, group in enumerate(groups):
                    last = idx == len(groups) - 1
                    ratio = group["base"] / total_base
                    splits.append(
                        {
                            "category": group["category"],
                            "account": group["account"] or fallback_account,
                            "dpp": left_dpp if last else round(dpp * ratio, 2),
                            "pph": left_pph if last else round(pph * ratio, 2),
                        }
                    )
                    left_dpp -= splits[-1]["dpp"]
                    left_pph -= splits[-1]["pph"]
            else:
                splits.append(
                    {
                        "category": self._opt(ml, "x_custom_withholding_category_id", False)
                        or self._move_category(move),
                        "account": fallback_account,
                        "dpp": dpp,
                        "pph": pph,
                    }
                )

            kind = acct_kinds.get(ml.account_id.id) or ""
            for split in splits:
                category = split["category"]
                account = split["account"]
                coa_expense = ""
                if account:
                    coa_expense = ("%s %s" % (self._account_code(account), account.name or "")).strip()
                buckets.setdefault(kind, []).append(
                    {
                        "date": move.date or move.invoice_date,
                        "doc_no": move.name or "",
                        "journal_no": move.name or "",
                        "invoice_no": move.ref or "",
                        "invoice_date": move.invoice_date,
                        "npwp": self._opt(partner, "x_custom_npwp") or self._opt(partner, "vat"),
                        "partner": partner.display_name or "",
                        "kode_objek": (category.bupot_object_code or category.code or "") if category else "",
                        "jenis_pph": _PPH_LABEL.get(kind, kind or ""),
                        "jenis_penghasilan": category.name if category else jenis,
                        "coa_expense": coa_expense,
                        "sumber": sumber,
                        "dpp": split["dpp"],
                        "tarif": tarif,
                        "pph": split["pph"],
                    }
                )
        return buckets

    def _build_lines(self, filters):
        pph_kind = filters.get("pph_kind") or "all"

        if "account.move.withholding.line" not in self.env:
            return [
                {"type": "note", "doc_no": "Modul PPh (custom_tax_id) belum terpasang — tidak ada data."},
                {"type": "grand_total", "doc_no": "TOTAL", "dpp": 0.0, "pph": 0.0},
            ]

        WL = self.env["account.move.withholding.line"].sudo()
        domain = [
            ("company_id", "in", list(filters["company_ids"])),
            ("move_id.date", ">=", filters["date_from"]),
            ("move_id.date", "<=", filters["date_to"]),
        ]
        if filters.get("posted_only", True):
            domain.append(("move_id.state", "=", "posted"))
        if pph_kind != "all":
            domain.append(("pph_kind", "=", pph_kind))
        records = WL.search(domain)

        buckets = {}
        orphan_count = 0
        orphan_total = 0.0
        for wl in records:
            move = wl.move_id
            # A withholding line only belongs in the recap when its PPh actually
            # reached the GL — i.e. the engine booked its "Pemotongan PPh" entry.
            # On prd_levis_begbal every bill has x_custom_withholding_move_id
            # empty while the same bills carry native PPh taxes that ARE booked,
            # so counting these lines too would double-report ~Rp161jt of PPh and
            # break the tie-out to the ledger. They are surfaced as a note
            # instead of being silently dropped or silently double-counted.
            if "x_custom_withholding_move_id" in move._fields and not move.x_custom_withholding_move_id:
                orphan_count += 1
                orphan_total += wl.tax_amount or 0.0
                continue
            partner = move.commercial_partner_id or move.partner_id
            # Separate PPh journal entry ("Pemotongan PPh …"), when custom_tax_id
            # books it as its own move; blank if the field/module is absent.
            wmove = self._opt(move, "x_custom_withholding_move_id")
            journal_no = wmove.name if wmove else ""
            # Expense account of the withheld source line.
            exp_acc = wl.move_line_id.account_id if wl.move_line_id else False
            coa_expense = ""
            if exp_acc:
                coa_expense = ("%s %s" % (self._account_code(exp_acc), exp_acc.name or "")).strip()
            buckets.setdefault(wl.pph_kind, []).append(
                {
                    "date": move.date or move.invoice_date,
                    "doc_no": move.name or "",
                    "journal_no": journal_no,
                    "invoice_no": move.ref or "",
                    "invoice_date": move.invoice_date,
                    "npwp": self._opt(partner, "x_custom_npwp") or self._opt(partner, "x_custom_nik"),
                    "partner": partner.display_name or "",
                    "kode_objek": wl.category_id.bupot_object_code or (wl.category_id.code or ""),
                    "jenis_pph": _PPH_LABEL.get(wl.pph_kind, wl.pph_kind or ""),
                    "jenis_penghasilan": wl.category_id.name or (wl.category_id.code or ""),
                    "coa_expense": coa_expense,
                    "sumber": "Engine",
                    "dpp": wl.base_amount or 0.0,
                    "tarif": wl.tarif or 0.0,
                    "pph": wl.tax_amount or 0.0,
                }
            )

        # Fold in PPh booked outside the engine (native tax on a bill, or a
        # manual journal entry onto Hutang PPh) so the recap is complete.
        for kind, rows in self._manual_pph_rows(filters).items():
            if pph_kind != "all" and kind != pph_kind:
                continue
            buckets.setdefault(kind, []).extend(rows)

        lines = []
        g_dpp = g_pph = 0.0
        ordered = [k for k in _PPH_ORDER if k in buckets] + [k for k in buckets if k not in _PPH_ORDER]
        for kind in ordered:
            group = sorted(
                buckets[kind],
                key=lambda r: (r["jenis_penghasilan"], r["date"] or date_cls.min, r["doc_no"]),
            )
            s_dpp = s_pph = 0.0
            for row in group:
                lines.append(row)
                s_dpp += row["dpp"]
                s_pph += row["pph"]
            lines.append(
                {
                    "type": "subtotal",
                    "doc_no": "Subtotal %s" % _PPH_LABEL.get(kind, kind),
                    "dpp": s_dpp,
                    "pph": s_pph,
                }
            )
            g_dpp += s_dpp
            g_pph += s_pph

        lines.append({"type": "grand_total", "doc_no": "TOTAL", "dpp": g_dpp, "pph": g_pph})
        if orphan_count:
            lines.append(
                {
                    "type": "note",
                    "doc_no": _(
                        "%(count)s baris withholding senilai %(total).2f TIDAK diikutkan: "
                        "belum ada jurnal GL-nya (x_custom_withholding_move_id kosong). "
                        "Total di atas sengaja dibuat sama dengan buku besar akun Hutang PPh.",
                        count=orphan_count,
                        total=orphan_total,
                    ),
                }
            )
        return lines
