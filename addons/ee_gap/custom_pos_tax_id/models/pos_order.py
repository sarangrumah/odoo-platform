# -*- coding: utf-8 -*-
"""Guard: a POS order may only be invoiced once the buyer can be identified.

An invoiced POS order leaves the digunggung recap and becomes an
``out_invoice``, which is what ``custom_coretax_export`` turns into an FK row.
The FK layout has no blank-NPWP variant — ``NPWP`` and ``TKU_PEMBELI`` are
derived from the partner — so an invoice raised against an anonymous walk-in
customer is a faktur that can never be uploaded.

Without this guard nothing complains until the tax team runs the export at the
end of the masa, long after the receipt was printed and the customer left. We
refuse at the point where it is still fixable: the cashier can open the partner
and type the NPWP while the buyer is still standing there.

``x_custom_nik`` is accepted as an alternative because DJP allows NIK in place
of NPWP for an individual buyer — the same fallback ``custom.report.faktur
.pajak`` already applies when it prints the NPWP/NIK column.
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    x_custom_partner_npwp = fields.Char(
        related="partner_id.x_custom_npwp",
        string="NPWP Pembeli",
        readonly=True,
    )

    def _pos_tax_identity_missing(self):
        """Orders in ``self`` whose buyer cannot carry an e-Faktur."""
        missing = self.browse()
        for order in self:
            partner = order.partner_id.commercial_partner_id or order.partner_id
            if not partner:
                missing |= order
                continue
            npwp = (partner.x_custom_npwp or "").strip()
            nik = ((partner.x_custom_nik or "") if "x_custom_nik" in partner._fields else "").strip()
            if not npwp and not nik:
                missing |= order
        return missing

    def _generate_pos_order_invoice(self):
        blocked = self._pos_tax_identity_missing()
        if blocked:
            raise UserError(
                _(
                    "Faktur pajak tidak bisa diterbitkan tanpa identitas pembeli.\n\n"
                    "Order berikut belum punya pelanggan ber-NPWP/NIK:\n%(orders)s\n\n"
                    "Pilih pelanggan di POS lalu isi NPWP (atau NIK) pada data "
                    "pelanggan, kemudian ulangi. Penjualan tanpa identitas pembeli "
                    "tidak perlu di-invoice — pelaporannya lewat rekap PPN "
                    "digunggung.",
                    orders="\n".join("- %s" % (order.name or order.pos_reference or order.id) for order in blocked),
                )
            )
        return super()._generate_pos_order_invoice()
