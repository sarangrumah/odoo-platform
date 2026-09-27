# -*- coding: utf-8 -*-
"""``levis.clearing.ebr.wizard`` — what to put in the workbook, and nothing else.

Two sheets are heavy enough to be worth a choice: ``COMPILE SALES`` is one row
per X70D tender line (a Levi's month is ~9.200) and the AR sheet walks last
month's still-open receivable. Everything else is the run itself and is always
written.

The wizard computes nothing. It cannot: a report that recomputes the run it
reports would delete the receipt ticks the run's operator has been making all
week (see ``levis.clearing.manual.map`` for why that is not a theoretical worry).
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class LevisClearingEbrWizard(models.TransientModel):
    _name = "levis.clearing.ebr.wizard"
    _description = "Export Clearing Recon Workbook"

    run_id = fields.Many2one("levis.pos.clearing", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="run_id.company_id")
    compile_sales = fields.Boolean(
        string="Include COMPILE SALES",
        default=True,
        help="Every X70D tender transaction of the period — around 9.000 rows for a "
        "Levi's month. It is the slow half of the export: the staged feed is read "
        "through a SQL view over JSON, about a minute on prd_levis_begbal against "
        "two seconds for everything else. Untick it if you only need the "
        "reconciliation; SUMMARY already carries the sales side per store-day.",
    )
    receipt_gaps = fields.Boolean(
        string="Also list lines with unnamed receipts",
        help="Add the settlements that are mapped and allocated but whose X24DN "
        "transactions nobody has ticked yet. They are not blocking anything — on a "
        "Levi's month they are around 830 rows against 90 that genuinely need a "
        "decision — so they are off by default.",
    )
    ar_sheet = fields.Boolean(
        string="Include AR sheet",
        default=True,
        help="Last month's POS receivable: what this run collected, and what is still open.",
    )

    def action_export(self):
        self.ensure_one()
        if self.run_id.state == "draft":
            raise UserError(
                _(
                    "%s has not been computed yet, so there is nothing to report. Press "
                    "Compute Summary on the run first — it reads the statements and "
                    "builds the lines, and books nothing.",
                    self.run_id.name,
                )
            )
        return self.env["levis.clearing.ebr"]._action(
            self.run_id,
            options={
                "compile_sales": self.compile_sales,
                "ar_sheet": self.ar_sheet,
                "receipt_gaps": self.receipt_gaps,
            },
        )
