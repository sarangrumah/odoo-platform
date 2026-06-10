# -*- coding: utf-8 -*-
"""VAT / PPh report: Output vs Input per tax, subtotals per fiscal
position. Cross-references the optional ``custom.coretax.transaction``
when the Coretax module is installed.
"""

from odoo import models


class CustomReportTax(models.AbstractModel):
    _name = "custom.report.tax"
    _inherit = "custom.report.engine"
    _description = "Custom Tax Report"

    _report_code = "tax"
    _report_title = "Tax Report"

    def _xlsx_columns(self):
        return [
            {"header": "Tax", "field": "tax_name", "kind": "text", "width": 34},
            {"header": "Rate", "field": "tax_rate", "kind": "number", "width": 10},
            {"header": "Type", "field": "tax_use", "kind": "text", "width": 12},
            {"header": "Fiscal Position", "field": "fiscal_position", "kind": "text", "width": 24},
            {"header": "Base", "field": "base_amount", "kind": "number", "width": 18},
            {"header": "Tax", "field": "tax_amount", "kind": "number", "width": 18},
        ]

    def _xlsx_body(self, sheet, ctx, columns, fmts, start_row):
        row = start_row
        for col_idx, col in enumerate(columns):
            sheet.write(row, col_idx, col["header"], fmts["header"])
        sheet.freeze_panes(row + 1, 0)
        row += 1

        for line in ctx.get("lines", []):
            ltype = line.get("type")
            if ltype == "category":
                sheet.merge_range(row, 0, row, 5, line.get("label") or "", fmts["section"])
                row += 1
                for t in line.get("taxes", []):
                    sheet.write(row, 0, t.get("tax_name") or "", fmts["text"])
                    sheet.write_number(row, 1, float(t.get("tax_rate") or 0.0), fmts["num"])
                    sheet.write(row, 2, t.get("tax_use") or "", fmts["text"])
                    sheet.write(row, 3, t.get("fiscal_position") or "", fmts["text"])
                    sheet.write_number(row, 4, float(t.get("base_amount") or 0.0), fmts["num"])
                    sheet.write_number(row, 5, float(t.get("tax_amount") or 0.0), fmts["num"])
                    row += 1
                sheet.merge_range(row, 0, row, 3, "Subtotal", fmts["total_text"])
                sheet.write_number(row, 4, float(line.get("base_subtotal") or 0.0), fmts["total_num"])
                sheet.write_number(row, 5, float(line.get("tax_subtotal") or 0.0), fmts["total_num"])
                row += 1
            elif ltype == "fp_breakdown":
                sheet.merge_range(row, 0, row, 5, line.get("label") or "", fmts["section"])
                row += 1
                for r in line.get("rows", []):
                    sheet.merge_range(row, 0, row, 3, r.get("fiscal_position") or "", fmts["text"])
                    sheet.write_number(row, 4, float(r.get("base_subtotal") or 0.0), fmts["num"])
                    sheet.write_number(row, 5, float(r.get("tax_subtotal") or 0.0), fmts["num"])
                    row += 1
            elif ltype == "total":
                sheet.merge_range(row, 0, row, 4, line.get("label") or "", fmts["total_text"])
                sheet.write_number(row, 5, float(line.get("tax_amount") or 0.0), fmts["total_num"])
                row += 1
            elif ltype == "grand_total":
                sheet.merge_range(row, 0, row, 3, line.get("label") or "Grand Total", fmts["total_text"])
                sheet.write_number(row, 4, float(line.get("base_amount") or 0.0), fmts["total_num"])
                sheet.write_number(row, 5, float(line.get("tax_amount") or 0.0), fmts["total_num"])
                row += 1
        return row

    def _classify(self, tax):
        """Bucket a tax into output / input / withholding."""
        # Convention: ``type_tax_use=='sale'`` is output VAT; ``purchase``
        # is input VAT. Withholdings flagged via name prefix "PPh".
        if (tax.name or "").upper().startswith("PPH"):
            return "withholding"
        if tax.type_tax_use == "sale":
            return "output"
        if tax.type_tax_use == "purchase":
            return "input"
        return "other"

    def _build_lines(self, filters):
        AML = self.env["account.move.line"]
        domain = self._base_move_line_domain(filters)

        # Base lines (move lines that bear ``tax_ids``)
        base_rows = AML._read_group(
            domain=domain + [("tax_ids", "!=", False)],
            groupby=["tax_ids"],
            aggregates=["balance:sum"],
        )
        base_by_tax = {tax.id: -(b or 0.0) for tax, b in base_rows}

        # Tax lines (move lines that ARE a tax line via ``tax_line_id``)
        tax_rows = AML._read_group(
            domain=domain + [("tax_line_id", "!=", False)],
            groupby=["tax_line_id"],
            aggregates=["balance:sum"],
        )
        tax_by_tax = {tax.id: -(b or 0.0) for tax, b in tax_rows}

        all_tax_ids = sorted(set(base_by_tax) | set(tax_by_tax))
        taxes = self.env["account.tax"].browse(all_tax_ids)

        # Cross-reference Coretax if installed.
        coretax_link = {}
        if "custom.coretax.transaction" in self.env:
            Coretax = self.env["custom.coretax.transaction"]
            coretax_rows = Coretax.sudo().search(
                [
                    ("create_date", ">=", filters["date_from"]),
                    ("create_date", "<=", filters["date_to"]),
                ]
            )
            for ct in coretax_rows:
                tax_id = getattr(ct, "tax_id", False)
                if tax_id:
                    coretax_link.setdefault(tax_id.id, []).append(ct.id)

        groups = {}
        for tax in taxes:
            cat = self._classify(tax)
            grp = groups.setdefault(
                cat,
                {
                    "type": "category",
                    "category": cat,
                    "label": {
                        "output": "Output VAT (PPN Keluaran)",
                        "input": "Input VAT (PPN Masukan)",
                        "withholding": "Withholding (PPh)",
                        "other": "Other Taxes",
                    }[cat],
                    "taxes": [],
                    "base_subtotal": 0.0,
                    "tax_subtotal": 0.0,
                },
            )
            base = base_by_tax.get(tax.id, 0.0)
            tax_amt = tax_by_tax.get(tax.id, 0.0)
            fiscal_position = getattr(tax, "fiscal_position_ids", None) and tax.fiscal_position_ids.mapped("name") or []
            grp["taxes"].append(
                {
                    "tax_id": tax.id,
                    "tax_name": tax.name,
                    "tax_rate": tax.amount,
                    "tax_use": tax.type_tax_use,
                    "fiscal_position": ", ".join(fiscal_position),
                    "base_amount": base,
                    "tax_amount": tax_amt,
                    "coretax_ids": coretax_link.get(tax.id, []),
                }
            )
            grp["base_subtotal"] += base
            grp["tax_subtotal"] += tax_amt

        # Per fiscal position subtotal (cross-cutting).
        fp_subtotals = {}
        for grp in groups.values():
            for t in grp["taxes"]:
                fp = t["fiscal_position"] or "—"
                row = fp_subtotals.setdefault(
                    fp,
                    {
                        "fiscal_position": fp,
                        "base_subtotal": 0.0,
                        "tax_subtotal": 0.0,
                    },
                )
                row["base_subtotal"] += t["base_amount"]
                row["tax_subtotal"] += t["tax_amount"]

        lines = []
        total_base = total_tax = 0.0
        for cat in ("output", "input", "withholding", "other"):
            if cat in groups:
                grp = groups[cat]
                lines.append(grp)
                total_base += grp["base_subtotal"]
                total_tax += grp["tax_subtotal"]

        # Output vs Input balance (PPN payable / refundable)
        net_ppn = groups.get("output", {}).get("tax_subtotal", 0.0) - groups.get("input", {}).get("tax_subtotal", 0.0)
        lines.append(
            {
                "type": "fp_breakdown",
                "label": "Per Fiscal Position",
                "rows": list(fp_subtotals.values()),
            }
        )
        lines.append(
            {
                "type": "total",
                "label": "Net PPN (Output - Input)",
                "tax_amount": net_ppn,
            }
        )
        lines.append(
            {
                "type": "grand_total",
                "label": "Grand Total",
                "base_amount": total_base,
                "tax_amount": total_tax,
            }
        )
        return lines
