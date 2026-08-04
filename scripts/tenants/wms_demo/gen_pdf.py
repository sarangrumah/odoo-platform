# -*- coding: utf-8 -*-
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUT = "/var/lib/odoo/hht_barcode_test_receiving.pdf"

H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=19, spaceAfter=2)
SUB = ParagraphStyle("SUB", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
H2 = ParagraphStyle(
    "H2",
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=colors.white,
    backColor=colors.HexColor("#1f2937"),
    borderPadding=(4, 5, 4, 5),
    spaceBefore=4,
    spaceAfter=4,
)
NOTE = ParagraphStyle("NOTE", fontName="Helvetica", fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
LBL = ParagraphStyle("LBL", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)
SML = ParagraphStyle("SML", fontName="Helvetica", fontSize=7.2, leading=9, textColor=colors.HexColor("#555555"))
CODE = ParagraphStyle("CODE", fontName="Courier", fontSize=7, leading=8.5, textColor=colors.HexColor("#333333"))


def bc_code128(value, bar_width=0.40, height=13):
    return createBarcodeDrawing(
        "Code128",
        value=value,
        barHeight=height * mm,
        barWidth=bar_width * mm,
        humanReadable=False,
        quiet=True,
    )


def bc_ean13(value, height=14):
    return createBarcodeDrawing(
        "EAN13",
        value=value,
        barHeight=height * mm,
        barWidth=0.36 * mm,
        humanReadable=True,
        fontSize=6.5,
        quiet=True,
    )


def cell(drawing, label, sub=None, raw=None):
    flow = [drawing, Spacer(1, 1.5 * mm), Paragraph(label, LBL)]
    if sub:
        flow.append(Paragraph(sub, SML))
    if raw:
        flow.append(Paragraph(raw, CODE))
    return flow


def grid(cells, cols=2, width=175 * mm):
    rows, cur = [], []
    for c in cells:
        cur.append(c)
        if len(cur) == cols:
            rows.append(cur)
            cur = []
    if cur:
        cur += [""] * (cols - len(cur))
        rows.append(cur)
    t = Table(rows, colWidths=[width / cols] * cols, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#dddddd")),
            ]
        )
    )
    return t


story = []
story.append(Paragraph("Lembar Barcode Uji Scan &mdash; HHT Receiving", H1))
story.append(
    Paragraph(
        "Database <b>demo_wms</b> &middot; Gudang <b>JDC</b> &middot; Device "
        "<b>Denso BHT-1700QWB-1</b> &middot; dibuat 28 Juli 2026<br/>"
        "Semua kode di lembar ini sudah diverifikasi resolve terhadap data "
        "demo_wms lewat jalur yang sama dengan aplikasi HHT "
        "(<font face='Courier' size='7'>/hht/wms/scan/resolve</font>).",
        SUB,
    )
)
story.append(Spacer(1, 5 * mm))

# ---------------------------------------------------------------- 1
story.append(Paragraph("1 &nbsp;&middot;&nbsp; Dokumen Penerimaan", H2))
story.append(
    Paragraph(
        "Scan di layar daftar <b>Receive</b> &mdash; HHT langsung lompat ke receipt "
        "yang dimaksud tanpa perlu cari manual. Dua dokumen ini keduanya berstatus "
        "<b>Ready</b> dan saling melengkapi: yang pertama untuk uji lot, yang kedua "
        "khusus untuk uji serial/IMEI di bagian 5.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
story.append(
    grid(
        [
            cell(
                bc_code128("JDC/IN/00001", 0.45, 16),
                "JDC/IN/00001",
                "Ready &middot; 4 baris &middot; 168 unit &middot; lot-tracked<br/>dipakai bagian 2, 3, 4 dan 7",
            ),
            cell(
                bc_code128("JDC/IN/00012", 0.45, 16),
                "JDC/IN/00012",
                "Ready &middot; 1 baris &middot; 5 unit JD-TRK-01<br/>dipakai bagian 5 &mdash; serial / IMEI",
            ),
        ],
        cols=2,
    )
)
story.append(Spacer(1, 3 * mm))

# ---------------------------------------------------------------- 2
ON_RECEIPT = [
    ("8990000000013", "NK-PEG-42", "Nike Air Zoom Pegasus", 60),
    ("8990000000037", "AD-ULT-42", "Adidas Ultraboost 22", 48),
    ("8990000000051", "PM-RSX-42", "Puma RS-X", 36),
    ("8990000000020", "NK-CRT-41", "Nike Court Vision Low", 24),
]
story.append(Paragraph("2 &nbsp;&middot;&nbsp; Produk pada Receipt &mdash; EAN-13", H2))
story.append(
    Paragraph(
        "Empat produk yang benar-benar ada di JDC/IN/00001. Ingat aturan modul: "
        "<b>scan menetapkan (SET) kuantitas, bukan menambah</b> &mdash; kuantitas "
        "pre-fill dari demand di-nol-kan lebih dulu, jadi hitungan fisik yang menang. "
        "Semua produk ini <b>lot-tracked</b>.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
story.append(
    grid(
        [
            cell(
                bc_ean13(b),
                f"{sku} &nbsp;&mdash;&nbsp; {b}",
                f"{nm} &middot; demand <b>{q}</b> unit &middot; tracking: lot",
            )
            for b, sku, nm, q in ON_RECEIPT
        ],
        cols=2,
    )
)

# ---------------------------------------------------------------- 3
story.append(Paragraph("3 &nbsp;&middot;&nbsp; GTIN-14 (alias barcode)", H2))
story.append(
    Paragraph(
        "Varian 14-digit dari produk yang sama, menguji tabel alias "
        "<font face='Courier' size='7'>product.barcode</font> di modul "
        "<b>custom_product_barcode</b>. Harus resolve ke produk yang identik dengan "
        "bagian 2 &mdash; kalau tidak, jalur alias-nya putus.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
story.append(
    grid(
        [cell(bc_code128("0" + b, 0.40, 12), f"0{b}", f"{sku} &middot; {nm}") for b, sku, nm, _q in ON_RECEIPT], cols=2
    )
)

# ---------------------------------------------------------------- 4
GS1 = [
    ("01089900000000131727123110LOT-NKPEG-01", "NK-PEG-42", "LOT-NKPEG-01", "31 Des 2027"),
    ("01089900000000371728063010LOT-ADULT-01", "AD-ULT-42", "LOT-ADULT-01", "30 Jun 2028"),
    ("01089900000000511727093010LOT-PMRSX-01", "PM-RSX-42", "LOT-PMRSX-01", "30 Sep 2027"),
    ("01089900000000201728033110LOT-NKCRT-01", "NK-CRT-41", "LOT-NKCRT-01", "31 Mar 2028"),
]
story.append(Paragraph("4 &nbsp;&middot;&nbsp; GS1 Element String &mdash; GTIN + Expiry + Lot", H2))
story.append(
    Paragraph(
        "Format <b>AI 01</b> (GTIN, 14 digit) + <b>AI 17</b> (kedaluwarsa, YYMMDD) + "
        "<b>AI 10</b> (nomor lot). AI 10 sengaja ditaruh <b>paling akhir</b> karena "
        "panjangnya variabel &mdash; dengan begitu tidak butuh karakter pemisah FNC1 "
        "(<font face='Courier' size='7'>\\x1d</font>) yang sering tidak dikirim scanner "
        "saat mode keyboard-wedge. Sesudah validasi, cek lot yang terbentuk: "
        "<b>expiration_date</b> harus ikut terisi dari AI 17.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
story.append(
    grid(
        [
            cell(bc_code128(c, 0.26, 14), f"{sku} &middot; lot {lot}", f"kedaluwarsa {exp}", c)
            for c, sku, lot, exp in GS1
        ],
        cols=2,
    )
)

# ---------------------------------------------------------------- 5
story.append(Paragraph("5 &nbsp;&middot;&nbsp; Serial / IMEI &mdash; JD-TRK-01", H2))
story.append(
    Paragraph(
        "<b>JD Smart Tracker (IMEI)</b>, tracking = <b>serial</b>, EAN-13 "
        "8990000000099. Satu serial = satu unit, satu move line. "
        "Buka dulu <b>JDC/IN/00012</b> (barcode di bagian 1) &mdash; receipt itu "
        "dibuat khusus berisi <b>5 unit JD-TRK-01</b> dan tidak ada produk "
        "serial-tracked lain, sehingga kelima kode di bawah cukup untuk memenuhinya. "
        "Syarat itu penting: IMEI polos hanya ter-atribusi otomatis kalau receipt "
        "punya <b>tepat satu</b> produk serial-tracked; kalau lebih dari satu, "
        "hanya bentuk GS1 AI 21 yang bekerja.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
IMEI = ["356938035643809", "356938035643817", "356938035643825", "356938035643833"]
cells = [cell(bc_code128(i, 0.40, 12), i, "IMEI polos (14&ndash;16 digit)") for i in IMEI]
cells.append(
    cell(
        bc_code128("010899000000009921356938035643810", 0.28, 14),
        "GS1 AI 01 + AI 21",
        "serial 356938035643810",
        "010899000000009921356938035643810",
    )
)
story.append(grid(cells, cols=2))

# ---------------------------------------------------------------- 6
BINS = [
    ("JDC-GR-IN-01", "JDC/Stock/GR Dock/GR-IN-01", "dok terima &mdash; titik turun barang"),
    ("JDC-HD-A-01", "JDC/Stock/HD Palletised Racking/HD-A-01", "rak palet"),
    ("JDC-HD-A-02", "JDC/Stock/HD Palletised Racking/HD-A-02", "rak palet"),
    ("JDC-HD-A-03", "JDC/Stock/HD Palletised Racking/HD-A-03", "rak palet"),
    ("JDC-NIK-01", "JDC/Stock/Forward Pick Area/NIKE/NIK-01", "forward pick &mdash; Nike"),
    ("JDC-ADI-01", "JDC/Stock/Forward Pick Area/ADIDAS/ADI-01", "forward pick &mdash; Adidas"),
    ("JDC-PUM-01", "JDC/Stock/Forward Pick Area/PUMA/PUM-01", "forward pick &mdash; Puma"),
    ("JDC-PACK-01", "JDC/Stock/Pack &amp; Ship Staging/PACK-01", "staging pack &amp; ship"),
    ("JDC-GR", "JDC/Stock/GR Dock (Goods Receipt)", "induk zona GR"),
    ("JDCSTOCK", "JDC/Stock", "induk stok gudang"),
]
story.append(Paragraph("6 &nbsp;&middot;&nbsp; Bin / Lokasi &mdash; Putaway", H2))
story.append(
    Paragraph(
        "Dipakai di layar <b>Putaway</b> untuk menerima atau menolak saran bin dari "
        "engine. Scan bin lain dari daftar ini untuk menguji jalur override manual.<br/>"
        "<b>Catatan:</b> <font face='Courier' size='7'>JDCQUALITY</font> "
        "(JDC/Quality Control) sengaja tidak dicetak &mdash; lokasi itu ter-<i>archive</i> "
        "di demo_wms sehingga scan-nya akan gagal.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
story.append(grid([cell(bc_code128(b, 0.42, 12), b, f"{path}<br/>{note}") for b, path, note in BINS], cols=2))

# ---------------------------------------------------------------- 7
OTHER = [
    ("8990000000044", "AD-SMB-43", "Adidas Samba OG"),
    ("8990000000068", "NK-TEE-M", "Nike Dri-FIT Tee"),
    ("8990000000075", "AD-TIR-M", "Adidas Tiro Track Pant"),
    ("8990000000082", "PM-HOD-L", "Puma Essentials Hoodie"),
]
story.append(Paragraph("7 &nbsp;&middot;&nbsp; Uji Negatif &mdash; Barang Salah &amp; Kode Asing", H2))
story.append(
    Paragraph(
        "Produk-produk ini <b>ada di master</b> tetapi <b>tidak ada di JDC/IN/00001</b>: "
        "scan-nya harus ditolak sebagai barang di luar dokumen, bukan diam-diam "
        "menambah baris. Kode terakhir tidak terdaftar di mana pun &mdash; HHT harus "
        "menjawab <font face='Courier' size='7'>NOT_FOUND</font>.",
        NOTE,
    )
)
story.append(Spacer(1, 2 * mm))
cells = [
    cell(bc_ean13(b), f"{sku} &nbsp;&mdash;&nbsp; {b}", f"{nm} &middot; <b>di luar</b> JDC/IN/00001")
    for b, sku, nm in OTHER
]
cells.append(cell(bc_code128("9999999999999", 0.40, 12), "9999999999999", "tidak terdaftar &mdash; harus NOT_FOUND"))
story.append(grid(cells, cols=2))

doc = SimpleDocTemplate(
    OUT,
    pagesize=A4,
    leftMargin=18 * mm,
    rightMargin=17 * mm,
    topMargin=15 * mm,
    bottomMargin=14 * mm,
    title="Lembar Barcode Uji Scan - HHT Receiving (demo_wms)",
    author="Odoo Platform",
)


def footer(canvas, doc_):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawString(18 * mm, 8 * mm, "demo_wms - JDC - lembar uji scan HHT receiving")
    canvas.drawRightString(193 * mm, 8 * mm, "hal. %d" % doc_.page)
    canvas.restoreState()


doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("WROTE", OUT)
