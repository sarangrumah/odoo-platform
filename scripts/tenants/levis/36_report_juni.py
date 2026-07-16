# Build the June-2026 finance workbook for a levis DB (run via odoo shell).
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http < scripts/tenants/levis/36_report_juni.py
#
# Sheets:
#   Ringkasan          - headline figures + what is / is not included
#   Saldo Awal Juni    - per-COA balance as of 31-May-2026 (the loaded begbal)
#   Jurnal Sales Juni  - every account.move.line of the June X24 sales entries
#   Saldo Akhir Juni   - per-COA opening + June movement + closing as of 30-Jun-2026
#   COA Lengkap        - every account in the chart, incl. zero balances
#
# Env: OUT_PATH (default /tmp/levis/Laporan_Saldo_Juni_2026.xlsx)
import io
import os

import xlsxwriter

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[rpt] " + m)

OUT = os.environ.get("OUT_PATH", "/tmp/levis/Laporan_Saldo_Juni_2026.xlsx")
COMPANY_ID = 1
D_OPEN_END = "2026-05-31"  # begbal cutoff
D_FROM = "2026-06-01"
D_TO = "2026-06-30"

company = env["res.company"].browse(COMPANY_ID)


def q(sql, params=None):
    env.cr.execute(sql, params or ())
    return env.cr.fetchall()


# ---- per-account balances -------------------------------------------------------
BAL = """
    SELECT l.account_id, SUM(l.debit), SUM(l.credit)
    FROM account_move_line l JOIN account_move m ON m.id = l.move_id
    WHERE m.state='posted' AND m.company_id=%s AND m.date >= %s AND m.date <= %s
    GROUP BY l.account_id
"""
opening = {a: (d, c) for a, d, c in q(BAL, (COMPANY_ID, "1900-01-01", D_OPEN_END))}
movement = {a: (d, c) for a, d, c in q(BAL, (COMPANY_ID, D_FROM, D_TO))}
closing = {a: (d, c) for a, d, c in q(BAL, (COMPANY_ID, "1900-01-01", D_TO))}

accounts = {
    aid: (code, name)
    for aid, code, name in q(
        "SELECT id, code_store->>%s, name->>'en_US' FROM account_account ORDER BY code_store->>%s",
        (str(COMPANY_ID), str(COMPANY_ID)),
    )
}
log("accounts=%d opening=%d movement=%d closing=%d" % (len(accounts), len(opening), len(movement), len(closing)))

# ---- June sales journal lines ----------------------------------------------------
lines = q(
    """
    SELECT m.name, m.date, m.ref, j.code,
           a.code_store->>%s, a.name->>'en_US',
           l.name, l.debit, l.credit
    FROM account_move_line l
    JOIN account_move m ON m.id = l.move_id
    JOIN account_journal j ON j.id = m.journal_id
    JOIN account_account a ON a.id = l.account_id
    WHERE m.state='posted' AND m.company_id=%s AND m.date >= %s AND m.date <= %s
    ORDER BY m.name, a.code_store->>%s
""",
    (str(COMPANY_ID), COMPANY_ID, D_FROM, D_TO, str(COMPANY_ID)),
)
log("june journal lines: %d" % len(lines))

# ---- transaction-level detail -----------------------------------------------------
# The 20 INV entries above are POS session-close summaries. Finance also needs to see the
# underlying orders and lines, and which revenue account each line actually resolves to.
INCOME = "COALESCE((pt.property_account_income_id->>'1')::int, (pc.property_account_income_categ_id->>'1')::int)"
order_rows = q("""
    SELECT cfg.name, o.date_order::date, o.name, o.pos_reference,
           count(l.id), sum(l.qty), o.amount_total, o.amount_tax
    FROM pos_order o
    JOIN pos_session s ON s.id = o.session_id
    JOIN pos_config cfg ON cfg.id = s.config_id
    LEFT JOIN pos_order_line l ON l.order_id = o.id
    GROUP BY cfg.name, o.date_order, o.name, o.pos_reference, o.amount_total, o.amount_tax
    ORDER BY cfg.name, o.date_order, o.name
""")
line_rows = q(
    """
    SELECT cfg.name, o.date_order::date, o.name,
           pt.default_code, pt.name->>'en_US', pc.complete_name,
           l.qty, l.price_unit, l.price_subtotal, l.price_subtotal_incl,
           a.code_store->>'%s', a.name->>'en_US'
    FROM pos_order_line l
    JOIN pos_order o ON o.id = l.order_id
    JOIN pos_session s ON s.id = o.session_id
    JOIN pos_config cfg ON cfg.id = s.config_id
    JOIN product_product pp ON pp.id = l.product_id
    JOIN product_template pt ON pt.id = pp.product_tmpl_id
    LEFT JOIN product_category pc ON pc.id = pt.categ_id
    LEFT JOIN account_account a ON a.id = %s
    ORDER BY cfg.name, o.date_order, o.name, pt.default_code
"""
    % (COMPANY_ID, INCOME)
)
log("detail: %d orders, %d lines" % (len(order_rows), len(line_rows)))

pos_orders = q("SELECT count(*) FROM pos_order")[0][0]
n_moves = q(
    """SELECT count(*) FROM account_move
               WHERE state='posted' AND company_id=%s AND date>=%s AND date<=%s""",
    (COMPANY_ID, D_FROM, D_TO),
)[0][0]

# ---- workbook --------------------------------------------------------------------
buf = io.BytesIO()
wb = xlsxwriter.Workbook(buf, {"in_memory": True})
f_title = wb.add_format({"bold": True, "font_size": 14})
f_sub = wb.add_format({"font_size": 10, "italic": True, "font_color": "#555555"})
f_hdr = wb.add_format(
    {"bold": True, "bg_color": "#DDEBF7", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True}
)
f_txt = wb.add_format({"border": 1})
f_num = wb.add_format({"border": 1, "num_format": "#,##0.00"})
f_tot = wb.add_format({"bold": True, "border": 1, "num_format": "#,##0.00", "bg_color": "#F2F2F2"})
f_totl = wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2"})
f_lbl = wb.add_format({"bold": True})


def sign(d, c):
    return round(d - c, 2)


def balance_sheet(name, src, title, subtitle):
    """One sheet: Code | Account | Debit | Credit | Saldo (Dr-Cr).

    Debit/Credit are the *netted* balance per account (an account that received both
    a debit and a credit shows one side only), so the sheet reads as a balance and its
    total ties to the Trial Balance rather than to the gross posting volume.
    """
    ws = wb.add_worksheet(name)
    ws.write(0, 0, title, f_title)
    ws.write(1, 0, company.name, f_sub)
    ws.write(2, 0, subtitle, f_sub)
    heads = ["Kode", "Nama Akun", "Debit", "Kredit", "Saldo (Dr-Kr)"]
    for i, h in enumerate(heads):
        ws.write(4, i, h, f_hdr)
    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 46)
    ws.set_column(2, 4, 20)
    ws.freeze_panes(5, 0)
    r = 5
    td = tc = 0.0
    for aid, (code, aname) in accounts.items():
        d, c = src.get(aid, (0.0, 0.0))
        if not d and not c:
            continue
        net = sign(d, c)
        dr, cr = max(net, 0.0), max(-net, 0.0)
        ws.write(r, 0, code or "", f_txt)
        ws.write(r, 1, aname or "", f_txt)
        ws.write_number(r, 2, dr, f_num)
        ws.write_number(r, 3, cr, f_num)
        ws.write_number(r, 4, net, f_num)
        td += dr
        tc += cr
        r += 1
    ws.write(r, 0, "TOTAL", f_totl)
    ws.write(r, 1, "", f_totl)
    ws.write_number(r, 2, td, f_tot)
    ws.write_number(r, 3, tc, f_tot)
    ws.write_number(r, 4, sign(td, tc), f_tot)
    return td, tc, r - 5


# ---- Ringkasan (written last-ish but created first so it is the front tab) --------
ws0 = wb.add_worksheet("Ringkasan")

open_d, open_c, open_n = balance_sheet(
    "Saldo Awal Juni",
    opening,
    "Saldo Awal Juni 2026 (per 31-Mei-2026)",
    "Sumber: EBR TB — opening move 1-Jan-2026 + gerakan bulanan Jan s/d Mei (kolom Juni TB TIDAK dimuat)",
)

# ---- Jurnal Sales Juni -----------------------------------------------------------
ws = wb.add_worksheet("Jurnal Sales Juni")
ws.write(0, 0, "Jurnal Sales Juni 2026 (yang terbentuk dari import X24)", f_title)
ws.write(1, 0, company.name, f_sub)
ws.write(2, 0, "%d entri jurnal, %d baris, dari %d pos.order" % (n_moves, len(lines), pos_orders), f_sub)
heads = [
    "No. Jurnal",
    "Tanggal",
    "Referensi (Toko)",
    "Jurnal",
    "Kode Akun",
    "Nama Akun",
    "Keterangan",
    "Debit",
    "Kredit",
]
for i, h in enumerate(heads):
    ws.write(4, i, h, f_hdr)
ws.set_column(0, 0, 18)
ws.set_column(1, 1, 12)
ws.set_column(2, 2, 40)
ws.set_column(3, 3, 10)
ws.set_column(4, 4, 14)
ws.set_column(5, 5, 32)
ws.set_column(6, 6, 34)
ws.set_column(7, 8, 18)
ws.freeze_panes(5, 0)
r = 5
jd = jc = 0.0
for mname, mdate, mref, jcode, acode, aname, lname, d, c in lines:
    ws.write(r, 0, mname or "", f_txt)
    ws.write(r, 1, str(mdate), f_txt)
    ws.write(r, 2, mref or "", f_txt)
    ws.write(r, 3, jcode or "", f_txt)
    ws.write(r, 4, acode or "", f_txt)
    ws.write(r, 5, aname or "", f_txt)
    ws.write(r, 6, lname or "", f_txt)
    ws.write_number(r, 7, float(d), f_num)
    ws.write_number(r, 8, float(c), f_num)
    jd += float(d)
    jc += float(c)
    r += 1
for i in range(7):
    ws.write(r, i, "TOTAL" if i == 0 else "", f_totl)
ws.write_number(r, 7, jd, f_tot)
ws.write_number(r, 8, jc, f_tot)

# ---- Detail Order Juni ------------------------------------------------------------
ws = wb.add_worksheet("Detail Order Juni")
ws.write(0, 0, "Detail Order Juni 2026 (pos.order)", f_title)
ws.write(1, 0, "%d order" % len(order_rows), f_sub)
for i, h in enumerate(
    ["Toko", "Tanggal", "No. Order", "Ref. POS", "Jml Baris", "Total Qty", "Total (incl. pajak)", "Pajak"]
):
    ws.write(3, i, h, f_hdr)
ws.set_column(0, 0, 36)
ws.set_column(1, 1, 12)
ws.set_column(2, 3, 24)
ws.set_column(4, 5, 12)
ws.set_column(6, 7, 20)
ws.freeze_panes(4, 0)
ws.autofilter(3, 0, 3 + len(order_rows), 7)
r = 4
ot = oq = 0.0
for store, dt, oname, oref, nl, qty, tot, tax in order_rows:
    ws.write(r, 0, store or "", f_txt)
    ws.write(r, 1, str(dt), f_txt)
    ws.write(r, 2, oname or "", f_txt)
    ws.write(r, 3, oref or "", f_txt)
    ws.write_number(r, 4, int(nl or 0), f_txt)
    ws.write_number(r, 5, float(qty or 0), f_num)
    ws.write_number(r, 6, float(tot or 0), f_num)
    ws.write_number(r, 7, float(tax or 0), f_num)
    ot += float(tot or 0)
    oq += float(qty or 0)
    r += 1
for i in range(5):
    ws.write(r, i, "TOTAL" if i == 0 else "", f_totl)
ws.write_number(r, 5, oq, f_tot)
ws.write_number(r, 6, ot, f_tot)
ws.write(r, 7, "", f_totl)

# ---- Detail Baris Juni -------------------------------------------------------------
ws = wb.add_worksheet("Detail Baris Juni")
ws.write(0, 0, "Detail Baris Penjualan Juni 2026 (pos.order.line)", f_title)
ws.write(
    1, 0, "%d baris — kolom Akun Revenue menunjukkan COA yang benar-benar dipakai tiap baris" % len(line_rows), f_sub
)
for i, h in enumerate(
    [
        "Toko",
        "Tanggal",
        "No. Order",
        "Kode Produk",
        "Nama Produk",
        "Kategori",
        "Qty",
        "Harga Satuan",
        "Subtotal (excl. pajak)",
        "Subtotal (incl. pajak)",
        "Kode Akun Revenue",
        "Nama Akun Revenue",
    ]
):
    ws.write(3, i, h, f_hdr)
ws.set_column(0, 0, 36)
ws.set_column(1, 1, 12)
ws.set_column(2, 2, 22)
ws.set_column(3, 3, 16)
ws.set_column(4, 4, 40)
ws.set_column(5, 5, 38)
ws.set_column(6, 9, 18)
ws.set_column(10, 10, 18)
ws.set_column(11, 11, 30)
ws.freeze_panes(4, 0)
ws.autofilter(3, 0, 3 + len(line_rows), 11)
r = 4
lq = lsub = lincl = 0.0
for store, dt, oname, pcode, pname, categ, qty, pu, sub, incl, acode, aname in line_rows:
    ws.write(r, 0, store or "", f_txt)
    ws.write(r, 1, str(dt), f_txt)
    ws.write(r, 2, oname or "", f_txt)
    ws.write(r, 3, pcode or "", f_txt)
    ws.write(r, 4, (pname or "")[:120], f_txt)
    ws.write(r, 5, categ or "(tanpa kategori)", f_txt)
    ws.write_number(r, 6, float(qty or 0), f_num)
    ws.write_number(r, 7, float(pu or 0), f_num)
    ws.write_number(r, 8, float(sub or 0), f_num)
    ws.write_number(r, 9, float(incl or 0), f_num)
    ws.write(r, 10, acode or "(fallback perusahaan)", f_txt)
    ws.write(r, 11, aname or "", f_txt)
    lq += float(qty or 0)
    lsub += float(sub or 0)
    lincl += float(incl or 0)
    r += 1
for i in range(6):
    ws.write(r, i, "TOTAL" if i == 0 else "", f_totl)
ws.write_number(r, 6, lq, f_tot)
ws.write(r, 7, "", f_totl)
ws.write_number(r, 8, lsub, f_tot)
ws.write_number(r, 9, lincl, f_tot)
ws.write(r, 10, "", f_totl)
ws.write(r, 11, "", f_totl)

# ---- Saldo Akhir Juni: opening + movement + closing -------------------------------
ws = wb.add_worksheet("Saldo Akhir Juni")
ws.write(0, 0, "Saldo Akhir Juni 2026 (per 30-Jun-2026)", f_title)
ws.write(1, 0, company.name, f_sub)
ws.write(2, 0, "Saldo Awal (s/d 31-Mei) + Mutasi Juni (sales) = Saldo Akhir Juni", f_sub)
heads = [
    "Kode",
    "Nama Akun",
    "Saldo Awal Debit",
    "Saldo Awal Kredit",
    "Mutasi Juni Debit",
    "Mutasi Juni Kredit",
    "Saldo Akhir Debit",
    "Saldo Akhir Kredit",
]
for i, h in enumerate(heads):
    ws.write(4, i, h, f_hdr)
ws.set_column(0, 0, 14)
ws.set_column(1, 1, 46)
ws.set_column(2, 7, 20)
ws.freeze_panes(5, 0)
r = 5
tot = [0.0] * 6
for aid, (code, aname) in accounts.items():
    od, oc = opening.get(aid, (0.0, 0.0))
    md, mc = movement.get(aid, (0.0, 0.0))
    cd, cc = closing.get(aid, (0.0, 0.0))
    if not any((od, oc, md, mc, cd, cc)):
        continue
    # present each side netted so a row reads as a single balance
    onet, cnet = sign(od, oc), sign(cd, cc)
    vals = [max(onet, 0), max(-onet, 0), md, mc, max(cnet, 0), max(-cnet, 0)]
    ws.write(r, 0, code or "", f_txt)
    ws.write(r, 1, aname or "", f_txt)
    for i, v in enumerate(vals):
        ws.write_number(r, 2 + i, v, f_num)
        tot[i] += v
    r += 1
ws.write(r, 0, "TOTAL", f_totl)
ws.write(r, 1, "", f_totl)
for i, v in enumerate(tot):
    ws.write_number(r, 2 + i, v, f_tot)
close_d, close_c = tot[4], tot[5]

# ---- COA Lengkap (all accounts, incl. zeros) --------------------------------------
ws = wb.add_worksheet("COA Lengkap")
ws.write(0, 0, "Saldo Akhir Juni 2026 — seluruh COA (termasuk saldo nol)", f_title)
ws.write(1, 0, company.name, f_sub)
for i, h in enumerate(["Kode", "Nama Akun", "Saldo Akhir Debit", "Saldo Akhir Kredit", "Saldo (Dr-Kr)"]):
    ws.write(3, i, h, f_hdr)
ws.set_column(0, 0, 14)
ws.set_column(1, 1, 46)
ws.set_column(2, 4, 20)
ws.freeze_panes(4, 0)
r = 4
for aid, (code, aname) in accounts.items():
    cd, cc = closing.get(aid, (0.0, 0.0))
    net = sign(cd, cc)
    ws.write(r, 0, code or "", f_txt)
    ws.write(r, 1, aname or "", f_txt)
    ws.write_number(r, 2, max(net, 0), f_num)
    ws.write_number(r, 3, max(-net, 0), f_num)
    ws.write_number(r, 4, net, f_num)
    r += 1

# ---- Ringkasan content ------------------------------------------------------------
ws0.write(0, 0, "Laporan Saldo Juni 2026", f_title)
ws0.write(1, 0, company.name, f_sub)
ws0.set_column(0, 0, 52)
ws0.set_column(1, 1, 26)
rows = [
    ("Database", "prd_levis_begbal"),
    ("Periode", "1 s/d 30 Juni 2026"),
    ("", ""),
    ("Saldo Awal Juni — total Debit", open_d),
    ("Saldo Awal Juni — total Kredit", open_c),
    ("Jumlah akun dgn saldo awal", open_n),
    ("", ""),
    ("Jurnal sales Juni — entri", n_moves),
    ("Jurnal sales Juni — baris", len(lines)),
    ("Jurnal sales Juni — total Debit", jd),
    ("Jurnal sales Juni — total Kredit", jc),
    ("pos.order terimport", pos_orders),
    ("Detail baris penjualan (pos.order.line)", len(line_rows)),
    ("Detail — subtotal excl. pajak", lsub),
    ("Detail — subtotal incl. pajak", lincl),
    ("", ""),
    ("Saldo Akhir Juni — total Debit", close_d),
    ("Saldo Akhir Juni — total Kredit", close_c),
    ("", ""),
    ("SUDAH termasuk", "begbal opening 1-Jan + mutasi Jan s/d Mei"),
    ("SUDAH termasuk", "sales Juni detail (import X24, 4.387 order)"),
    ("BELUM termasuk", "jurnal NON-SALES Juni (kolom Juni TB tidak dimuat)"),
    ("BELUM termasuk", "settlement bank (Dr Outstanding Receipts / Cr POS Suspense) — bertanggal Juli"),
    ("Catatan", "POS Suspense Clearing masih terbuka per 30-Jun karena settlement jatuh di Juli"),
]
r = 3
for k, v in rows:
    if not k:
        r += 1
        continue
    ws0.write(r, 0, k, f_lbl if not k.startswith(("SUDAH", "BELUM", "Catatan")) else f_lbl)
    if isinstance(v, float):
        ws0.write_number(r, 1, v, wb.add_format({"num_format": "#,##0.00"}))
    else:
        ws0.write(r, 1, v)
    r += 1

wb.close()
raw = buf.getvalue()
with open(OUT, "wb") as f:
    f.write(raw)
log("wrote %s (%d bytes)" % (OUT, len(raw)))
log("saldo awal   D=%.2f C=%.2f" % (open_d, open_c))
log("jurnal juni  D=%.2f C=%.2f" % (jd, jc))
log("saldo akhir  D=%.2f C=%.2f" % (close_d, close_c))
assert abs(open_d - open_c) < 1, "saldo awal tidak balance"
assert abs(jd - jc) < 1, "jurnal juni tidak balance"
assert abs(close_d - close_c) < 1, "saldo akhir tidak balance"
log("==== BALANCED / DONE ====")
