"""AR (POS Receivable per tender) per Operating Unit — Juli vs Agustus 2026.

Read-only. Builds an xlsx from prd_levis_begbal with, per store:

  * penjualan yang masuk piutang (debit `1106000101..110`)
  * yang sudah tertagih/terekonsiliasi (credit)
  * sisa terbuka (amount_residual)

Two warnings the sheets repeat, because both mislead a reader who does not know:

1. Rekonsiliasi Juli dilakukan **per akun lintas toko**, jadi baris sisa mewarisi
   toko dan tanggal yang arbitrer. Kolom "sisa" per toko untuk Juli karena itu
   bukan bukti toko mana yang belum menyetor — hanya totalnya yang bermakna.
2. Agustus **belum di-clearing**, jadi kolom tertagihnya mendekati nol. Itu bukan
   temuan; itu pekerjaan yang memang belum dijalankan.

`1106000112` (POS Suspense Clearing) sengaja TIDAK diikutkan: akun itu didebet dan
dikredit di hari yang sama oleh tiap RIREC, memasukkannya melipatduakan penjualan.

Usage:
  PGPASSWORD=... python3 101_report_ar_per_ou_juli_agustus.py [--out FILE] [--db DB]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import defaultdict

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

CONTAINER = "odoo19-platform-postgres"
ACC_RANGE = "between '1106000101' and '1106000110'"
MONTHS = [("Juli", "2026-07-01", "2026-08-01"), ("Agustus", "2026-08-01", "2026-09-01")]

TENDER_LABEL = {
    "1106000101": "CASH",
    "1106000102": "DOMESTIC CARD / QRIS",
    "1106000103": "VISA",
    "1106000104": "MASTERCARD",
    "1106000105": "OTHER CREDIT CARD",
    "1106000106": "CREDIT CARD",
    "1106000107": "JCB",
    "1106000108": "BRI CREDIT CARD",
    "1106000109": "AMEX",
    "1106000110": "OVO",
}

HEAD_FILL = PatternFill("solid", fgColor="1F3A34")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=10)
TOTAL_FILL = PatternFill("solid", fgColor="E7ECEA")
NOTE_FONT = Font(italic=True, color="5A6663", size=9)
THIN = Side(style="thin", color="C9D2CF")
BORDER = Border(bottom=THIN)
MONEY = '#,##0;-#,##0;"-"'


def psql(db: str, sql: str) -> list[list[str]]:
    pw = os.environ.get("PGPASSWORD")
    if not pw:
        sys.exit("PGPASSWORD belum di-set (ambil dari /opt/odoo-platform/.env).")
    out = subprocess.run(
        [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={pw}",
            CONTAINER,
            "psql",
            "-U",
            "odoo",
            "-d",
            db,
            "-A",
            "-F",
            "\t",
            "-t",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ln.split("\t") for ln in out.splitlines() if ln.strip()]


def fetch(db: str, start: str, end: str) -> dict[tuple[str, str], dict[str, float]]:
    """(store, account) -> {debit, credit, residual, open_lines}"""
    rows = psql(
        db,
        f"""
        select coalesce(ou.name, '(tanpa OU)'),
               a.code_store->>'1',
               round(sum(ml.debit)), round(sum(ml.credit)),
               round(sum(ml.amount_residual)),
               count(*) filter (where not ml.reconciled)
          from account_move_line ml
          join account_account a on a.id = ml.account_id
          join account_move mv on mv.id = ml.move_id
          left join operating_unit ou on ou.id = ml.operating_unit_id
         where mv.state = 'posted'
           and a.code_store->>'1' {ACC_RANGE}
           and ml.date >= '{start}' and ml.date < '{end}'
         group by 1, 2
    """,
    )
    data: dict[tuple[str, str], dict[str, float]] = {}
    for store, acc, deb, cred, resid, nopen in rows:
        data[(store, acc)] = {
            "debit": float(deb or 0),
            "credit": float(cred or 0),
            "residual": float(resid or 0),
            "open": int(nopen or 0),
        }
    return data


def by_store(data) -> dict[str, dict[str, float]]:
    agg: dict[str, dict[str, float]] = defaultdict(lambda: {"debit": 0.0, "credit": 0.0, "residual": 0.0, "open": 0})
    for (store, _acc), v in data.items():
        for k in ("debit", "credit", "residual", "open"):
            agg[store][k] += v[k]
    return agg


def write_header(ws, headers, row=1):
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center" if c > 1 else "left", vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=row + 1, column=2)


def widths(ws, *pairs):
    for col, w in pairs:
        ws.column_dimensions[get_column_letter(col)].width = w


def note(ws, row, text):
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = NOTE_FONT
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def sheet_summary(wb, jul_store, agu_store):
    ws = wb.create_sheet("RINGKASAN PER TOKO")
    write_header(
        ws,
        [
            "Operating Unit",
            "Juli — penjualan",
            "Juli — tertagih",
            "Juli — sisa",
            "Juli — % tertagih",
            "Agustus — penjualan",
            "Agustus — tertagih",
            "Agustus — sisa",
            "Penjualan Agu vs Jul",
            "Selisih",
        ],
    )
    stores = sorted(set(jul_store) | set(agu_store))
    r = 2
    tot = defaultdict(float)
    for s in stores:
        j = jul_store.get(s, {"debit": 0, "credit": 0, "residual": 0})
        a = agu_store.get(s, {"debit": 0, "credit": 0, "residual": 0})
        pct = (j["credit"] / j["debit"]) if j["debit"] else 0
        growth = ((a["debit"] - j["debit"]) / j["debit"]) if j["debit"] else 0
        vals = [
            s,
            j["debit"],
            j["credit"],
            j["residual"],
            pct,
            a["debit"],
            a["credit"],
            a["residual"],
            growth,
            a["debit"] - j["debit"],
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = BORDER
            if c in (5, 9):
                cell.number_format = "0.0%"
            elif c > 1:
                cell.number_format = MONEY
        for k, idx in (("jd", 1), ("jc", 2), ("jr", 3), ("ad", 5), ("ac", 6), ("ar", 7)):
            tot[k] += vals[idx]
        r += 1
    ws.cell(row=r, column=1, value="TOTAL")
    totals = [
        tot["jd"],
        tot["jc"],
        tot["jr"],
        tot["jc"] / tot["jd"] if tot["jd"] else 0,
        tot["ad"],
        tot["ac"],
        tot["ar"],
        (tot["ad"] - tot["jd"]) / tot["jd"] if tot["jd"] else 0,
        tot["ad"] - tot["jd"],
    ]
    for c, v in enumerate(totals, start=2):
        cell = ws.cell(row=r, column=c, value=v)
        cell.number_format = "0.0%" if c in (5, 9) else MONEY
    for c in range(1, 11):
        ws.cell(row=r, column=c).fill = TOTAL_FILL
        ws.cell(row=r, column=c).font = Font(bold=True, size=10)
    widths(ws, (1, 38), *[(c, 17) for c in range(2, 11)])
    note(
        ws,
        r + 2,
        "Agustus BELUM di-clearing: kolom 'tertagih' mendekati nol karena "
        "jurnal settlement-nya memang belum dibuat, bukan karena dana belum masuk.",
    )
    note(
        ws,
        r + 3,
        "Kolom 'sisa' Juli per toko TIDAK menunjukkan toko mana yang belum menyetor: "
        "rekonsiliasi Juli dilakukan per akun lintas toko, jadi baris sisa mewarisi "
        "toko yang arbitrer. Hanya total Juli yang bermakna.",
    )
    return ws


def sheet_tender(wb, title, data, subtitle):
    ws = wb.create_sheet(title)
    accs = sorted({acc for (_s, acc) in data})
    write_header(ws, ["Operating Unit"] + [f"{a}\n{TENDER_LABEL.get(a, '')}" for a in accs] + ["Total"])
    stores = sorted({s for (s, _a) in data})
    r = 2
    coltot = defaultdict(float)
    for s in stores:
        ws.cell(row=r, column=1, value=s).border = BORDER
        rowtot = 0.0
        for c, acc in enumerate(accs, start=2):
            v = data.get((s, acc), {}).get("debit", 0.0)
            cell = ws.cell(row=r, column=c, value=v)
            cell.number_format, cell.border = MONEY, BORDER
            rowtot += v
            coltot[acc] += v
        cell = ws.cell(row=r, column=len(accs) + 2, value=rowtot)
        cell.number_format, cell.border, cell.font = MONEY, BORDER, Font(bold=True, size=10)
        r += 1
    ws.cell(row=r, column=1, value="TOTAL").font = Font(bold=True, size=10)
    for c, acc in enumerate(accs, start=2):
        cell = ws.cell(row=r, column=c, value=coltot[acc])
        cell.number_format = MONEY
    cell = ws.cell(row=r, column=len(accs) + 2, value=sum(coltot.values()))
    cell.number_format = MONEY
    for c in range(1, len(accs) + 3):
        ws.cell(row=r, column=c).fill = TOTAL_FILL
        ws.cell(row=r, column=c).font = Font(bold=True, size=10)
    widths(ws, (1, 38), *[(c, 16) for c in range(2, len(accs) + 3)])
    note(ws, r + 2, subtitle)
    return ws


def sheet_open_lines(wb, db):
    ws = wb.create_sheet("SISA JULI — BARIS TERBUKA")
    write_header(ws, ["Operating Unit", "Akun", "Tender", "Tanggal", "Jurnal", "Sisa"])
    rows = psql(
        db,
        f"""
        select coalesce(ou.name, '(tanpa OU)'), a.code_store->>'1', ml.date::text,
               mv.name, round(sum(ml.amount_residual))
          from account_move_line ml
          join account_account a on a.id = ml.account_id
          join account_move mv on mv.id = ml.move_id
          left join operating_unit ou on ou.id = ml.operating_unit_id
         where mv.state = 'posted'
           and a.code_store->>'1' {ACC_RANGE}
           and ml.date >= '2026-07-01' and ml.date < '2026-08-01'
           and not ml.reconciled
         group by 1, 2, 3, 4
         order by 5 desc
    """,
    )
    r, tot = 2, 0.0
    for store, acc, date, move, resid in rows:
        v = float(resid or 0)
        tot += v
        for c, val in enumerate([store, acc, TENDER_LABEL.get(acc, ""), date, move], start=1):
            ws.cell(row=r, column=c, value=val).border = BORDER
        cell = ws.cell(row=r, column=6, value=v)
        cell.number_format, cell.border = MONEY, BORDER
        r += 1
    ws.cell(row=r, column=1, value=f"TOTAL ({len(rows)} baris)").font = Font(bold=True, size=10)
    cell = ws.cell(row=r, column=6, value=tot)
    cell.number_format, cell.font = MONEY, Font(bold=True, size=10)
    for c in range(1, 7):
        ws.cell(row=r, column=c).fill = TOTAL_FILL
    widths(ws, (1, 38), (2, 14), (3, 22), (4, 13), (5, 22), (6, 16))
    note(
        ws,
        r + 2,
        "Tanggal dan toko pada baris-baris ini tidak bisa dibaca harfiah — "
        "rekonsiliasi per akun lintas toko membuat baris yang tersisa mewarisi "
        "identitas yang arbitrer. Komposisi sebenarnya: timing 31-Juli 412.665.600 + "
        "KOL Grand Indonesia 76.926.875 + AEON 1.400.875 − over-clearing 498.901 − "
        "1.501.700 yang sudah tertagih 1-Agustus.",
    )
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="prd_levis_begbal")
    ap.add_argument("--out", default="/srv/sftp-share/files/Laporan_AR_per_OU_Juli_Agustus2026.xlsx")
    args = ap.parse_args()

    jul = fetch(args.db, "2026-07-01", "2026-08-01")
    agu = fetch(args.db, "2026-08-01", "2026-09-01")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, by_store(jul), by_store(agu))
    sheet_tender(wb, "JULI PER TENDER", jul, "Nilai = penjualan yang masuk piutang (debit) per jenis tender.")
    sheet_tender(
        wb,
        "AGUSTUS PER TENDER",
        agu,
        "Nilai = penjualan yang masuk piutang (debit) per jenis tender. "
        "Seluruhnya masih terbuka: clearing Agustus belum dijalankan.",
    )
    sheet_open_lines(wb, args.db)
    wb.save(args.out)

    jt, at = by_store(jul), by_store(agu)
    print(
        f"Juli    penjualan {sum(v['debit'] for v in jt.values()):>18,.0f}"
        f"  tertagih {sum(v['credit'] for v in jt.values()):>18,.0f}"
        f"  sisa {sum(v['residual'] for v in jt.values()):>15,.0f}"
    )
    print(
        f"Agustus penjualan {sum(v['debit'] for v in at.values()):>18,.0f}"
        f"  tertagih {sum(v['credit'] for v in at.values()):>18,.0f}"
        f"  sisa {sum(v['residual'] for v in at.values()):>15,.0f}"
    )
    print("tersimpan:", args.out)


if __name__ == "__main__":
    main()
