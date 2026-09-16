# -*- coding: utf-8 -*-
"""Worksheet penetapan Operating Unit untuk aset tetap -- SELECT-ONLY.

Menghasilkan satu xlsx berisi setiap aset beserta Operating Unit yang
**diturunkan dari lokasi asetnya**, untuk ditinjau Accounting. Kolom "OU Final"
sudah terisi usulannya dan memakai dropdown, jadi yang perlu disentuh hanya
barisan yang salah -- bukan 148 sel kosong.

Dasar penurunannya: nama lokasi aset di tenant ini sama persis dengan nama akun
analytic Operating Unit ("OLS SES - PLAZA SENAYAN", "EBR - HEAD OFFICE").
Lokasi bertingkat diambil akar pertamanya, sehingga tiga sub-lokasi kantor pusat
jatuh ke satu OU. Kecocokannya 148/148; skrip tetap menandai baris yang tidak
cocok alih-alih menebak.

  python3 gen_ou_worksheet.py            # DB=prd_levis_begbal
"""

import csv
import io
import os
import subprocess
import sys
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

PG = "odoo19-platform-postgres"
DB = os.environ.get("DB", "prd_levis_begbal")
OUT = os.environ.get("OUT", "/srv/sftp-share/files/Penetapan_Operating_Unit_Aset.xlsx")

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
SUG_FILL = PatternFill("solid", fgColor="E2EFDA")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
NOTE_FONT = Font(italic=True, color="595959")


def q(sql):
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


ASSETS = """
with loc_root as (
  select l.id, l.complete_name,
         coalesce(split_part(l.complete_name,' / ',1), l.complete_name) as root_name
  from custom_fixed_asset_location l
), ou as (
  select aa.id, aa.name->>'en_US' as nm from account_analytic_account aa
  join account_analytic_plan p on p.id=aa.plan_id where p.name->>'en_US'='Operating Unit'
)
select a.code, a.name as asset_name, coalesce(g.code,'') as grup,
       coalesce(lr.complete_name,'') as lokasi, a.acquisition_date::text as tgl,
       a.acquisition_value::text as nilai, coalesce(a.quantity,1)::text as qty,
       a.state, coalesce(ou.nm,'') as ou_usulan,
       case when ou.id is null then 'TIDAK COCOK' else '' end as catatan
from custom_fixed_asset a
left join custom_fixed_asset_group g on g.id=a.group_id
left join loc_root lr on lr.id=a.location_id
left join ou on ou.nm=lr.root_name
order by coalesce(ou.nm,'zzz'), g.code, a.code
"""

OUS = """
select aa.name->>'en_US' as nm from account_analytic_account aa
join account_analytic_plan p on p.id=aa.plan_id
where p.name->>'en_US'='Operating Unit' order by 1
"""

rows = q(ASSETS)
ous = [r["nm"] for r in q(OUS)]
print(f"{DB}: {len(rows)} aset, {len(ous)} Operating Unit")

wb = Workbook()

# ---------------------------------------------------------------- sheet 1
ws = wb.active
ws.title = "Aset"
ws["A1"] = "Penetapan Operating Unit untuk Aset Tetap — %s" % DB
ws["A1"].font = Font(bold=True, size=13)
ws.merge_cells("A1:J1")
n = ws.cell(
    row=2,
    column=1,
    value=(
        "Kolom 'OU Final' SUDAH TERISI dengan usulan yang diturunkan dari lokasi aset — "
        "silakan ubah hanya baris yang salah, lewat dropdown di selnya. Kolom 'OU Usulan' "
        "sengaja dibiarkan sebagai pembanding; jangan diubah. Baris bertanda TIDAK COCOK di "
        "kolom Catatan wajib diisi manual."
    ),
)
n.font, n.alignment = NOTE_FONT, Alignment(wrap_text=True, vertical="top")
ws.merge_cells("A2:J2")
ws.row_dimensions[2].height = 42

heads = [
    "Kode Aset",
    "Nama Aset",
    "Grup",
    "Lokasi Aset",
    "Tgl Akuisisi",
    "Nilai Perolehan",
    "Qty",
    "Status",
    "OU Usulan (jangan diubah)",
    "OU Final (boleh diubah)",
]
widths = [16, 46, 10, 42, 13, 18, 7, 10, 34, 34]
for i, (h, w) in enumerate(zip(heads, widths), start=1):
    c = ws.cell(row=4, column=i, value=h)
    c.fill, c.font = HDR_FILL, HDR_FONT
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions[get_column_letter(i)].width = w
ws.row_dimensions[4].height = 30

r = 5
for row in rows:
    ws.cell(row=r, column=1, value=row["code"])
    ws.cell(row=r, column=2, value=row["asset_name"])
    ws.cell(row=r, column=3, value=row["grup"])
    ws.cell(row=r, column=4, value=row["lokasi"])
    ws.cell(row=r, column=5, value=row["tgl"])
    v = ws.cell(row=r, column=6, value=float(row["nilai"] or 0))
    v.number_format = "#,##0.00"
    ws.cell(row=r, column=7, value=float(row["qty"] or 1))
    ws.cell(row=r, column=8, value=row["state"])
    ws.cell(row=r, column=9, value=row["ou_usulan"])
    f = ws.cell(row=r, column=10, value=row["ou_usulan"])
    f.fill = WARN_FILL if row["catatan"] else SUG_FILL
    r += 1

dv = DataValidation(
    type="list", formula1="'Daftar OU'!$A$2:$A$%d" % (len(ous) + 1), allow_blank=True, showDropDown=False
)
dv.error = "Pilih salah satu Operating Unit dari daftar."
dv.errorTitle = "Operating Unit tidak dikenal"
ws.add_data_validation(dv)
dv.add("J5:J%d" % (r - 1))
ws.freeze_panes = "A5"
ws.auto_filter.ref = "A4:J%d" % (r - 1)

# ---------------------------------------------------------------- sheet 2
w2 = wb.create_sheet("Daftar OU")
c = w2.cell(row=1, column=1, value="Operating Unit yang sah (%d)" % len(ous))
c.fill, c.font = HDR_FILL, HDR_FONT
w2.column_dimensions["A"].width = 40
for i, nm in enumerate(ous, start=2):
    w2.cell(row=i, column=1, value=nm)

# ---------------------------------------------------------------- sheet 3
w3 = wb.create_sheet("Ringkasan")
w3["A1"] = "Ringkasan usulan per Operating Unit"
w3["A1"].font = Font(bold=True, size=12)
for i, (h, wd) in enumerate(zip(["Operating Unit", "Jumlah Aset", "Nilai Perolehan"], [38, 14, 20]), start=1):
    c = w3.cell(row=3, column=i, value=h)
    c.fill, c.font = HDR_FILL, HDR_FONT
    w3.column_dimensions[get_column_letter(i)].width = wd
agg = {}
for row in rows:
    k = row["ou_usulan"] or "(TIDAK COCOK)"
    n_, v_ = agg.get(k, (0, 0.0))
    agg[k] = (n_ + 1, v_ + float(row["nilai"] or 0))
rr = 4
for k in sorted(agg, key=lambda x: -agg[x][0]):
    w3.cell(row=rr, column=1, value=k)
    w3.cell(row=rr, column=2, value=agg[k][0])
    c = w3.cell(row=rr, column=3, value=agg[k][1])
    c.number_format = "#,##0.00"
    rr += 1
w3.cell(row=rr, column=1, value="TOTAL").font = Font(bold=True)
w3.cell(row=rr, column=2, value=sum(v[0] for v in agg.values())).font = Font(bold=True)
c = w3.cell(row=rr, column=3, value=sum(v[1] for v in agg.values()))
c.font, c.number_format = Font(bold=True), "#,##0.00"

wb.save(OUT)
# Supaya user share bisa mengunduhnya lewat SFTP / File Browser.
try:
    import grp
    import pwd

    os.chown(OUT, pwd.getpwnam("sftpshare").pw_uid, grp.getgrnam("sftpusers").gr_gid)
except (KeyError, PermissionError, OSError):
    pass
print("Tersimpan : %s" % OUT)
print("Cocok     : %d / %d" % (sum(1 for x in rows if not x["catatan"]), len(rows)))
