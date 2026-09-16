# -*- coding: utf-8 -*-
"""AP Aging Export — the payable twin of the AR collection worklist.

Sheet item #46 asks for "Report Aging yang sesuai SAP". The receivable side
already answers it (`custom.report.ar.aging.export`, fifteen overdue buckets);
this is the same layout read off the payable control account, so Finance can
put the two side by side.

Everything structural is inherited: the open-line query, the as-of residual,
the bucket edges, the XLSX writer and the on-screen table. What changes is the
commercial trail. On a customer invoice that trail is *sale* order → delivery;
on a vendor bill it is *purchase* order → goods receipt, and the vendor's own
document number lives in ``ref`` rather than in a linked order. So only
``_commercial_refs`` and the column headers are overridden.

Like its AR twin it ships **no wizard of its own** — it drives
``custom.report.aged.payable.wizard`` through the ``ap_aging_export`` context
key. This addon is installed on thirteen databases and a new ``TransientModel``
would force a schema change on every one of them.
"""

from odoo import models


class CustomReportApAgingExport(models.AbstractModel):
    _name = "custom.report.ap.aging.export"
    _inherit = "custom.report.ar.aging.export"
    _description = "AP Aging Export"

    _report_code = "ap_aging_export"
    _report_title = "AP Aging Export"

    def _account_type(self):
        return "liability_payable"

    # ------------------------------------------------------------------
    # Columns — same grid, vendor wording
    # ------------------------------------------------------------------
    def _base_columns(self):
        cols = super()._base_columns()
        renames = {
            "partner_name": "Vendor Name",
            "doc_no": "No Bill",
            "po_no": "No. PO",
            "so_no": "Vendor Ref",
            "do_no": "No. GR",
            "invoice_date": "Bill Date",
            "receive_date": "GR Date",
        }
        for col in cols:
            header = renames.get(col.get("field"))
            if header:
                col["header"] = header
        return cols

    # ------------------------------------------------------------------
    # Commercial trail — purchase side
    # ------------------------------------------------------------------
    def _purchase_orders(self, move):
        """The purchase orders behind a bill — via the bill lines when
        ``purchase`` is installed, else by matching ``invoice_origin`` on name.

        Mirrors ``_sale_orders`` deliberately, including its guards: this addon
        renders on tenants that have no ``purchase`` at all.
        """
        if "purchase.order" not in self.env:
            return None
        orders = self.env["purchase.order"].browse()
        if "purchase_line_id" in self.env["account.move.line"]._fields:
            orders = move.invoice_line_ids.purchase_line_id.order_id
        if not orders and move.invoice_origin:
            names = [part.strip() for part in move.invoice_origin.split(",") if part.strip()]
            if names:
                orders = self.env["purchase.order"].search([("name", "in", names)])
        return orders

    def _commercial_refs(self, move):
        """``(po_no, vendor_ref, gr_no, receive_date)`` for one bill.

        The tuple positions are the AR ones (``po_no, so_no, do_no,
        receive_date``) because the row builder is inherited; only the meaning
        of the middle two changes, which is why the headers are renamed above.

        ``receive_date`` is the goods-receipt date, which is what #25 settled as
        the basis Finance ages a purchase against — the bill date is when the
        paperwork arrived, not when the liability was incurred.
        """
        # On a bill ``ref`` is the vendor's own document number (Bill Reference);
        # on a plain journal entry it is the bookkeeper's narration, so don't
        # pass that off as a vendor reference.
        vendor_ref = (move.ref or "") if move.is_invoice(include_receipts=True) else ""
        po_no = ""
        gr_no = ""
        receive_date = False
        orders = self._purchase_orders(move)
        if orders:
            po_no = ", ".join(o.name for o in orders if o.name)
            pickings = orders.picking_ids if "picking_ids" in orders._fields else orders.browse()
            done = pickings.filtered(lambda p: p.state == "done")
            pickings = done or pickings
            if pickings:
                gr_no = ", ".join(p.name for p in pickings if p.name)
                dates = [p.date_done for p in pickings if p.date_done]
                if dates:
                    receive_date = max(dates).date()
        if not po_no:
            po_no = move.invoice_origin or ""
        return po_no, vendor_ref, gr_no, receive_date
