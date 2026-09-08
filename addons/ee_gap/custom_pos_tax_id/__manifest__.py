# -*- coding: utf-8 -*-
{
    "name": "Custom POS Tax ID (e-Faktur dari POS)",
    "summary": "Identitas pembeli di POS: syarat e-Faktur Keluaran atas penjualan eceran",
    "description": """
Jembatan antara Point of Sale dan identitas pajak Indonesia.

Penjualan eceran dilaporkan **digunggung** — agregat per masa, tanpa identitas
pembeli. Tetapi ketika pembeli meminta faktur pajak, penyerahan itu keluar dari
digunggung dan harus terbit e-Faktur atas namanya. Di Odoo jalur itu adalah
tombol *Invoice* di POS: order yang di-invoice menerbitkan ``out_invoice``, dan
ekspor FK/OF di ``custom_coretax_export`` memprosesnya seperti faktur lain.

Yang hilang adalah penjaganya. NPWP pembeli wajib ada di baris FK; tanpa itu
faktur tetap terbit dan baru ketahuan gagal saat ekspor, ketika struk sudah
lama dicetak dan pelanggan sudah pulang. Modul ini menolak lebih awal, di titik
yang masih bisa diperbaiki.

Tidak ada perubahan layar POS: Odoo 19 mengedit pelanggan lewat form partner
standar, yang sudah memuat kolom NPWP dari ``custom_tax_id``.
""",
    "author": "Custom Platform",
    "category": "Accounting/Localizations",
    "version": "19.0.0.1.0",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "custom_tax_id",
    ],
    "capability_tags": ["indonesian-tax", "efaktur", "point-of-sale"],
    "data": [
        "views/pos_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
