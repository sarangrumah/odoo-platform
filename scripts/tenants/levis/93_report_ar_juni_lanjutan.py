"""Ringkasan hasil penyelesaian clearing AR Juni 2026 di prd_levis_begbal.

SELECT-ONLY. Membaca ledger apa adanya dan menulis workbook untuk Accounting/FICO:
ringkasan enam jurnal EBR-ADJ-AR-JUNI-2026-*, detail baris tiga jurnal terakhir
(dibuat 92_ar_juni_lanjutan.py), verifikasi saldo sebelum/sesudah, dan alokasi
reclass POS Receivable Juli.

    python3 scripts/tenants/levis/93_report_ar_juni_lanjutan.py

Env:  DB=prd_levis_begbal   OUT=/srv/sftp-share/files/Ringkasan_Clearing_AR_Juni2026.xlsx
"""

import csv
import io
import os
import subprocess
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PG = "odoo19-platform-postgres"
DB = os.environ.get("DB", "prd_levis_begbal")
OUT = os.environ.get("OUT", "/srv/sftp-share/files/Ringkasan_Clearing_AR_Juni2026.xlsx")
CUTOFF, BOOKDATE, MONTHEND = "2026-06-30", "2026-07-01", "2026-07-31"
REF = "EBR-ADJ-AR-JUNI-2026"
NEW_REFS = ("SALESMANUAL", "TOPUP", "ADJ")

ACC = """with acc as (select id,(select value from jsonb_each_text(code_store) limit 1) code,
                            name->>'en_US' nm from account_account)"""
OU = """left join lateral (select k::int aid from jsonb_object_keys(l.analytic_distribution) k limit 1) y on true
        left join account_analytic_account o on o.id=y.aid"""


def q(sql):
    """Read-only query -> list of dicts."""
    out = subprocess.run(
        [
            "docker",
            "exec",
            PG,
            "sh",
            "-c",
            f'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d {DB} --csv -v ON_ERROR_STOP=1 -c "{sql}"',
        ],
        capture_output=True,
        text=True,
    )
    if out.returncode:
        sys.exit("query failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


H_FILL = PatternFill("solid", fgColor="DDEBF7")
T_FILL = PatternFill("solid", fgColor="FFF2CC")
MONEY = "#,##0;[Red]-#,##0"


def sheet(wb, title, headers, rows, money_cols=(), notes=(), total_row=False):
    ws = wb.create_sheet(title)
    r = 1
    for n in notes:
        ws.cell(r, 1, n).font = Font(italic=True, size=10)
        r += 1
    if notes:
        r += 1
    head = r
    for c, h in enumerate(headers, 1):
        cell = ws.cell(r, c, h)
        cell.font = Font(bold=True)
        cell.fill = H_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in rows:
        r += 1
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            if c in money_cols:
                cell.number_format = MONEY
    if total_row and r > head:
        for c in range(1, len(headers) + 1):
            ws.cell(r, c).fill = T_FILL
            ws.cell(r, c).font = Font(bold=True)
    ws.freeze_panes = ws.cell(head + 1, 1)
    for c, h in enumerate(headers, 1):
        width = max([len(str(h))] + [len(str(row[c - 1])) for row in rows if row[c - 1] is not None] or [10])
        ws.column_dimensions[get_column_letter(c)].width = min(max(width + 2, 11), 58)
    return ws


def num(v):
    return round(float(v or 0), 2)


# --- 1. enam jurnal adjustment ---------------------------------------------
moves = q(
    f"""select m.name, m.ref, m.state, m.date::text,
               sum(l.debit) dr, count(*) nline
          from account_move m join account_move_line l on l.move_id=m.id
         where m.ref like '{REF}%' group by 1,2,3,4 order by m.name"""
)

# --- 2. detail baris tiga jurnal baru --------------------------------------
detail = q(
    f"""{ACC}
        select m.ref, m.name mname, a.code, a.nm, coalesce(o.name->>'en_US','(tanpa OU)') ou,
               l.name descr, l.debit, l.credit
          from account_move_line l
          join account_move m on m.id=l.move_id
          join acc a on a.id=l.account_id {OU}
         where m.ref in ({",".join("'%s-%s'" % (REF, s) for s in NEW_REFS)})
         order by m.name, a.code, coalesce(o.name->>'en_US','')"""
)

# --- 3. verifikasi saldo ---------------------------------------------------
bals = q(
    f"""{ACC}
        select a.code, a.nm,
               sum(l.balance) filter (where m.state='posted' and l.date<='{CUTOFF}') jun30,
               sum(l.balance) filter (where m.state='posted' and l.date<='{MONTHEND}') jul31,
               sum(l.balance) filter (where l.date<='{MONTHEND}') jul31_draft
          from account_move_line l join account_move m on m.id=l.move_id join acc a on a.id=l.account_id
         where a.code in ('1106000001','2103100003','7104000001','7699000000')
         group by 1,2 order by 1"""
)
jun_debit = num(
    q(
        f"""select sum(l.debit) v from account_move_line l join account_move m on m.id=l.move_id
            where m.state='posted' and l.date between '2026-06-01' and '{CUTOFF}'"""
    )[0]["v"]
)

# --- 4. alokasi reclass POS receivable -------------------------------------
alloc = q(
    f"""{ACC}
        select coalesce(o.name->>'en_US','(tanpa OU)') ou, a.code, a.nm, l.credit
          from account_move_line l join account_move m on m.id=l.move_id
          join acc a on a.id=l.account_id {OU}
         where m.ref='{REF}-SALESMANUAL' and l.credit>0
         order by 1, a.code"""
)
pos_open = q(
    f"""{ACC}
        select coalesce(o.name->>'en_US','(tanpa OU)') ou, a.code,
               sum(case when m.state='posted' then l.debit-l.credit
                        when m.state='draft'  then -l.credit else 0 end) sisa
          from account_move_line l join account_move m on m.id=l.move_id
          join acc a on a.id=l.account_id {OU}
         where a.code between '1106000101' and '1106000110'
           and l.date between '{BOOKDATE}' and '{MONTHEND}' and m.state in ('posted','draft')
         group by 1,2 having sum(case when m.state='posted' then l.debit-l.credit
                                      when m.state='draft'  then -l.credit else 0 end) <> 0
         order by 1,2"""
)

# --- workbook --------------------------------------------------------------
wb = Workbook()
wb.remove(wb.active)

ws = wb.create_sheet("1. Ringkasan")
lines = [
    ("Ringkasan penyelesaian clearing AR Juni 2026", True),
    (f"Database {DB} · posisi diukur per {CUTOFF} · seluruh jurnal dibukukan {BOOKDATE}", False),
    ("Dasar persetujuan: sheet 'Ringkasan & Ulasan' workbook rekon final FICO Juni 2026", False),
    ("", False),
    ("Kenapa dibukukan 01-Jul dan bukan 30-Jun", True),
    ("Angka Juni sudah dilaporkan ke klien dan tidak boleh berubah sama sekali. Nilai tetap", False),
    ("diukur pada posisi 30-Jun-2026, hanya tanggal bukunya yang jatuh di periode terbuka.", False),
    (f"Bukti Juni utuh: total debit Juni tetap {jun_debit:,.2f}.", False),
    ("", False),
    ("Penjualan manual Rp 14.608.080 = reclass, bukan pendapatan baru", True),
    ("Uangnya tersetor ke bank pada Juni, tetapi store menginput ulang penjualannya di X24DN", False),
    ("pada Juli. Jadi di Odoo penjualan itu sudah ada sebagai POS Receivable Juli per tender,", False),
    ("lengkap dengan pendapatan dan PPN Keluaran-nya. Membukukannya sebagai Dr Piutang /", False),
    ("Cr Penjualan akan mendobel pendapatan dan PPN Keluaran Juli. Karena itu jurnalnya", False),
    ("memindahkan piutang dari POS Receivable Juli ke Trade Receivables, tanpa menyentuh", False),
    ("pendapatan. Lihat sheet '4. Alokasi reclass'.", False),
    ("", False),
    ("Top-up clearing Rp 4.186.925", True),
    ("Clearing 4-Aug-2026 berhenti di 667.523.715, bukan 671.710.640, karena deposit MM Bekasi", False),
    ("18.861.775 melebihi piutangnya 14.674.850 selama penjualan manual belum tercatat.", False),
    ("Setelah reclass di atas, piutangnya cukup dan sisa depositnya bisa di-clear penuh.", False),
    ("", False),
    ("Adjustment Rp 260.660", True),
    ("Sisa selisih rekon dipecah per toko: Central Park 200.000 adj bank yang digantung sebagai", False),
    ("deposit Juli (di-clear bersama AR Juli), TSM Bandung 50.170 kelebihan charge MDR Juni,", False),
    ("dan rounding 10.490 ke other operating income. Setelah ini sisa selisih tinggal Rp 1", False),
    ("(Grand Indonesia, piutang tokonya nol sehingga tidak bisa di-clear; FICO juga mencatat -1).", False),
]
for i, (text, bold) in enumerate(lines, 1):
    c = ws.cell(i, 1, text)
    if bold:
        c.font = Font(bold=True, size=12 if i == 1 else 11)
ws.column_dimensions["A"].width = 100

sheet(
    wb,
    "2. Jurnal",
    ["Move", "Ref", "Status", "Tanggal", "Total debit", "Jumlah baris", "Keterangan"],
    [
        [
            m["name"],
            m["ref"],
            m["state"],
            m["date"],
            num(m["dr"]),
            int(m["nline"]),
            {
                "REALOKASI": "diposting 4-Aug-2026",
                "MDR": "diposting 4-Aug-2026",
                "CLEARING": "diposting 4-Aug-2026 (kena cap piutang MM Bekasi)",
                "SALESMANUAL": "diposting 7-Aug-2026 — reclass POS Receivable Juli",
                "TOPUP": "diposting 7-Aug-2026 — melunasi cap clearing",
                "ADJ": "diposting 7-Aug-2026 — sisa selisih per toko",
            }.get(m["ref"].rsplit("-", 1)[-1], ""),
        ]
        for m in moves
    ],
    money_cols=(5,),
    notes=[
        "Enam jurnal adjustment AR Juni 2026, semuanya bertanggal 01-Jul-2026.",
        "Total debit jurnal ADJ (264.842) lebih besar dari mutasi nettonya ke Trade Receivables "
        "(260.660) karena tiga toko rounding-nya negatif sehingga mengkredit piutang.",
    ],
)

sheet(
    wb,
    "3. Detail baris",
    ["Move", "Ref", "Akun", "Nama akun", "Operating Unit", "Keterangan", "Debit", "Kredit"],
    [
        [
            d["mname"],
            d["ref"].rsplit("-", 1)[-1],
            d["code"],
            d["nm"],
            d["ou"],
            d["descr"],
            num(d["debit"]),
            num(d["credit"]),
        ]
        for d in detail
    ],
    money_cols=(7, 8),
    notes=["Baris lengkap tiga jurnal yang dibuat 7-Aug-2026. Setiap baris membawa Operating Unit."],
)

verif_rows = []
for b in bals:
    verif_rows.append(
        [
            b["code"],
            b["nm"],
            num(b["jun30"]),
            num(b["jul31"]),
            num(b["jul31_draft"]),
        ]
    )
sheet(
    wb,
    "4. Verifikasi saldo",
    ["Akun", "Nama akun", f"Posted s/d {CUTOFF}", f"Posted s/d {MONTHEND}", f"Termasuk draft s/d {MONTHEND}"],
    verif_rows,
    money_cols=(3, 4, 5),
    notes=[
        f"Kolom '{CUTOFF}' adalah posisi yang sudah dilaporkan — harus sama dengan angka rekon FICO: "
        "Trade Receivables 1.025.747.288, Deposit -671.710.641, MDR Bank 25.971.461,73.",
        "Kolom 'Posted s/d 31-Jul' adalah posisi setelah keenam jurnal adjustment. Sasaran sheet FICO "
        "untuk Trade Receivables 368.378.122; selisih Rp 1 adalah Grand Indonesia.",
        "Kolom terakhir memasukkan 63 jurnal clearing Juli yang masih DRAFT (menunggu approval "
        "Accounting) — Trade Receivables menjadi +2.949.901, tidak lagi minus.",
    ],
)

alloc_rows = [[a["ou"], a["code"], a["nm"], num(a["credit"])] for a in alloc]
alloc_rows.append(["TOTAL", "", "", round(sum(r[3] for r in alloc_rows), 2)])
sheet(
    wb,
    "5. Alokasi reclass",
    ["Operating Unit", "Akun POS Receivable", "Nama akun", "Jumlah direclass"],
    alloc_rows,
    money_cols=(4,),
    notes=[
        "Sisi kredit jurnal SALESMANUAL. Alokasinya hanya mengambil tender yang sisanya masih "
        "terbuka setelah 63 draft clearing Juli diposting, urut dari sisa terbesar — kalau "
        "mengambil baris yang akan disettle clearing Juli, clearing itu akan kurang bahan.",
        "Baris kreditnya sekaligus direkonsiliasi ke baris debit POS Receivable-nya.",
    ],
    total_row=True,
)

pos_rows = [[p["ou"], p["code"], num(p["sisa"])] for p in pos_open]
pos_rows.append(["TOTAL", "", round(sum(r[2] for r in pos_rows), 2)])
sheet(
    wb,
    "6. Sisa POS Receivable",
    ["Operating Unit", "Akun POS Receivable", "Sisa terbuka"],
    pos_rows,
    money_cols=(3,),
    notes=[
        "Sisa POS Receivable Juli yang tetap terbuka setelah seluruh jurnal clearing Juli "
        "(termasuk yang masih draft) dan reclass di sheet 5 diperhitungkan.",
        "Tidak boleh ada yang negatif — negatif berarti clearing Juli kekurangan bahan.",
    ],
    total_row=True,
)

wb.save(OUT)
os.chmod(OUT, 0o644)
print("tulis %s" % OUT)
print("  jurnal            : %d" % len(moves))
print("  baris detail      : %d" % len(detail))
print("  total debit Juni  : %.2f (harus tidak berubah)" % jun_debit)
for b in bals:
    print("  %s per %s = %s | per %s = %s" % (b["code"], CUTOFF, num(b["jun30"]), MONTHEND, num(b["jul31"])))
neg = [p for p in pos_rows[:-1] if p[2] < -0.004]
if neg:
    sys.exit("SISA POS RECEIVABLE NEGATIF: %s" % neg)
