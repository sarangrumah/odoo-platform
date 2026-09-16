# -*- coding: utf-8 -*-
"""Fixed Asset Register & Depreciation Schedule (Daftar Aktiva Tetap).

Reuses the ``custom.report.engine`` XLSX infrastructure from
``custom_accounting_reports``: one row per asset with the acquisition value,
accumulated depreciation before the period, the monthly depreciation amounts,
the movement inside the period, the accumulated depreciation at the end of it
and the resulting book value.

Three things this report answers that it did not before (sheet rows #51, #60):

* **The accounts and the location travel with the row.** Accounting reviews this
  monthly and uses it for asset opname, and both jobs need to see which asset
  account, accumulated account and expense account a row will post to — without
  opening 148 asset forms. The analytic distribution rides along too, so the
  store is on the same line.

* **A date range, not a year.** ``date_to`` is the as-of date: accumulation and
  book value are stated at that date, not at 31 December. An opname taken on the
  15th can now be reconciled against a register taken on the 15th.

* **Posted, not merely scheduled.** ``basis`` defaults to ``posted``, so
  accumulation reflects what the ledger actually carries. The old behaviour —
  every scheduled line whether booked or not — stays available as ``schedule``,
  because the depreciation *schedule* is a legitimate second use of this report
  and silently changing its numbers would be worse than offering both.
"""

from odoo import models


MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class CustomReportAssetRegister(models.AbstractModel):
    _name = "custom.report.asset.register"
    _inherit = "custom.report.engine"
    _description = "Fixed Asset Register & Depreciation Schedule"

    _report_code = "asset_register"
    _report_title = "Daftar Aktiva Tetap & Penyusutan"

    def _xlsx_columns(self):
        cols = [
            {"header": "No", "field": "no", "kind": "text", "width": 5},
            {"header": "Code", "field": "code", "kind": "text", "width": 14},
            {"header": "Asset Name", "field": "name", "kind": "text", "width": 34},
            {"header": "Group", "field": "group", "kind": "text", "width": 18},
            {"header": "Location", "field": "location", "kind": "text", "width": 28},
            {"header": "Operating Unit", "field": "analytic", "kind": "text", "width": 26},
            {"header": "Qty", "field": "qty", "kind": "number", "width": 7},
            # The three accounts every row will post to. #51 asks for them by
            # name so a monthly review does not mean opening each asset form.
            {"header": "Asset Account", "field": "acc_asset", "kind": "text", "width": 30},
            {"header": "Accum. Dep. Account", "field": "acc_accum", "kind": "text", "width": 30},
            {"header": "Dep. Expense Account", "field": "acc_expense", "kind": "text", "width": 30},
            {"header": "Acq. Date", "field": "acq_date", "kind": "date", "width": 12},
            {"header": "Life (mo)", "field": "life", "kind": "number", "width": 9},
            {"header": "Acquisition Value", "field": "acq_value", "kind": "number", "width": 18},
            {"header": "Accum. Opening", "field": "opening", "kind": "number", "width": 16},
        ]
        for i, label in enumerate(MONTH_LABELS):
            cols.append({"header": label, "field": "m%d" % i, "kind": "number", "width": 13})
        cols += [
            # "Period", not "YTD": the range no longer has to start in January.
            {"header": "Period", "field": "ytd", "kind": "number", "width": 15},
            {"header": "Accum. End", "field": "accum_end", "kind": "number", "width": 16},
            {"header": "Book Value", "field": "book", "kind": "number", "width": 16},
        ]
        return cols

    def _account_label(self, account):
        """``code name``, or empty — the register is read by people, not joined."""
        if not account:
            return ""
        return " ".join(part for part in (account.code, account.display_name) if part)

    def _analytic_label(self, asset):
        """Names behind ``analytic_distribution``, so the store is on the row.

        Read off the distribution rather than off a tenant field: the base
        module has the distribution, ``l10n_ou_analytic_id`` lives in a tenant
        addon and is absent on ARKA-AIM.
        """
        distribution = asset.analytic_distribution or {}
        ids = [int(part) for key in distribution for part in str(key).split(",") if part.isdigit()]
        if not ids:
            return ""
        accounts = self.env["account.analytic.account"].browse(ids).exists()
        return ", ".join(accounts.mapped("display_name"))

    # Uses the engine's generic flat ``_xlsx_body`` (rows + grand_total).

    def _build_lines(self, filters):
        date_from = filters.get("date_from")
        date_to = filters["date_to"]
        # The twelve month columns are a one-year schedule by construction, so
        # they follow the year the period ENDS in. A range that spans a year
        # boundary still totals correctly in Period / Accum. End; only the month
        # breakdown is limited to the closing year, and the header says so.
        year = filters.get("year") or date_to.year
        posted_only = (filters.get("basis") or "posted") == "posted"

        Asset = self.env["custom.fixed.asset"]
        domain = [("company_id", "in", filters["company_ids"])]
        if filters.get("group_ids"):
            domain.append(("group_id", "in", filters["group_ids"]))
        if filters.get("location_ids"):
            domain.append(("location_id", "in", filters["location_ids"]))
        if filters.get("asset_states"):
            domain.append(("state", "in", filters["asset_states"]))
        assets = Asset.search(domain, order="code, id")

        lines = []
        totals = {
            "acq_value": 0.0,
            "qty": 0.0,
            "opening": 0.0,
            "ytd": 0.0,
            "accum_end": 0.0,
            "book": 0.0,
            **{"m%d" % i: 0.0 for i in range(12)},
        }
        for index, asset in enumerate(assets, start=1):
            months = [0.0] * 12
            opening = 0.0
            period = 0.0
            for dep in asset.depreciation_line_ids:
                if not dep.date:
                    continue
                # ``posted`` is the register basis: accumulation has to match
                # what the ledger carries, or an opname cannot be reconciled
                # against it. ``schedule`` keeps the old, forward-looking view.
                if posted_only and not dep.posted:
                    continue
                if dep.reversed:
                    continue
                if date_from and dep.date < date_from:
                    opening += dep.amount
                    continue
                if dep.date > date_to:
                    continue
                period += dep.amount
                if dep.date.year == year:
                    months[dep.date.month - 1] += dep.amount
            ytd = period
            accum_end = opening + ytd
            book = (asset.acquisition_value or 0.0) - accum_end

            row = {
                "no": str(index),
                "code": asset.code or "",
                "name": asset.name or "",
                "group": asset.group_id.name or "",
                "location": asset.location_id.complete_name or asset.location_id.name or "",
                "analytic": self._analytic_label(asset),
                "qty": asset.quantity or 0.0,
                "acc_asset": self._account_label(asset.asset_account_id),
                "acc_accum": self._account_label(asset.depreciation_account_id),
                "acc_expense": self._account_label(asset.expense_account_id),
                "acq_date": asset.acquisition_date,
                "life": asset.useful_life_months or 0,
                "acq_value": asset.acquisition_value or 0.0,
                "opening": opening,
                "ytd": ytd,
                "accum_end": accum_end,
                "book": book,
            }
            for i in range(12):
                row["m%d" % i] = months[i]
            lines.append(row)

            totals["acq_value"] += row["acq_value"]
            totals["qty"] += row["qty"]
            totals["opening"] += opening
            totals["ytd"] += ytd
            totals["accum_end"] += accum_end
            totals["book"] += book
            for i in range(12):
                totals["m%d" % i] += months[i]

        totals.update({"type": "grand_total", "name": "TOTAL"})
        lines.append(totals)
        return lines


class ReportAssetRegister(models.AbstractModel):
    _name = "report.custom_accounting_asset.report_asset_register"
    _description = "Asset Register PDF Renderer"

    def _get_report_values(self, docids, data=None):
        data = data or {}
        report = self.env["custom.report.asset.register"]
        ctx = report._compute(data.get("options") or data.get("filters"))
        return {
            "doc_ids": docids,
            "doc_model": data.get("doc_model", ""),
            "docs": [],
            **ctx,
        }
