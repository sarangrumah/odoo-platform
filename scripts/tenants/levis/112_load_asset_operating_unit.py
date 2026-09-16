# -*- coding: utf-8 -*-
"""Muat kolom 'OU Final' dari worksheet penetapan kembali ke aset tetap.

DRY RUN secara default. Menulis hanya ketika APPLY=1.

  docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal \\
    --no-http --max-cron-threads=0 --shell-interface=python \\
    < scripts/tenants/levis/112_load_asset_operating_unit.py

Dijalankan lewat ``odoo shell`` (butuh ``env``), bukan python biasa. Worksheet
dibaca dari dalam container: share ``/srv/sftp-share/files`` ter-mount di
``/mnt/data_levis``. Untuk menerapkan, ubah ``APPLY`` di bawah menjadi ``True``
atau jalankan dengan salinan yang sudah disetel -- ``odoo shell`` tidak
mewariskan env var dari host.

Env:  DB    -> database (default prd_levis_begbal)
      FILE  -> worksheet terisi
      APPLY -> 1 untuk benar-benar menulis

Yang ditulis hanya ``l10n_ou_analytic_id``; field itu punya inverse yang
menyusun ``analytic_distribution`` = {ou_id: 100} di bawahnya, jadi jangan
menyentuh distribusinya langsung dari sini.

Penjaga, karena ini menulis ke register aset produksi:
  * nama OU harus ADA di plan Operating Unit -- typo ditolak, tidak dibuat;
  * kode aset harus ada, dan hanya aset ``running`` yang disentuh;
  * aset yang OU-nya sudah sama dilewati, sehingga aman dijalankan ulang;
  * satu ringkasan dicetak sebelum apa pun ditulis, dan APPLY=0 berhenti di situ.
"""

import os
import sys
from openpyxl import load_workbook

DB = os.environ.get("DB", "prd_levis_begbal")
FILE = os.environ.get("FILE", "/mnt/data_levis/Penetapan_Operating_Unit_Aset.xlsx")
APPLY = os.environ.get("APPLY", "0") == "1"

wb = load_workbook(FILE, data_only=True)
ws = wb["Aset"]
rows = []
for r in ws.iter_rows(min_row=5, values_only=True):
    if not r or not r[0]:
        continue
    rows.append({"code": str(r[0]).strip(), "ou": (str(r[9]).strip() if r[9] else "")})
print("Worksheet : %s  (%d baris)" % (FILE, len(rows)))

Asset = env["custom.fixed.asset"]
plan = env["account.analytic.plan"].search([("name", "=", "Operating Unit")], limit=1, order="id")
if not plan:
    sys.exit("plan 'Operating Unit' tidak ada di %s" % DB)
by_name = {a.name: a for a in env["account.analytic.account"].search([("plan_id", "=", plan.id)])}

to_write, skip_same, miss_asset, miss_ou, blank, not_running = [], 0, [], [], 0, []
for row in rows:
    if not row["ou"]:
        blank += 1
        continue
    ou = by_name.get(row["ou"])
    if not ou:
        miss_ou.append((row["code"], row["ou"]))
        continue
    asset = Asset.search([("code", "=", row["code"])], limit=1)
    if not asset:
        miss_asset.append(row["code"])
        continue
    if asset.state != "running":
        not_running.append(row["code"])
        continue
    if asset.l10n_ou_analytic_id == ou:
        skip_same += 1
        continue
    to_write.append((asset, ou))

print("Akan ditulis      : %d" % len(to_write))
print("Sudah sama        : %d" % skip_same)
print("OU dikosongkan    : %d" % blank)
print("Aset tidak ketemu : %d %s" % (len(miss_asset), miss_asset[:5]))
print("OU tidak dikenal  : %d %s" % (len(miss_ou), miss_ou[:5]))
print("Bukan running     : %d %s" % (len(not_running), not_running[:5]))

if miss_ou:
    sys.exit("BERHENTI: ada nama Operating Unit yang tidak dikenal. Perbaiki worksheet dulu.")
if not APPLY:
    print("\nDRY RUN — tidak ada yang ditulis. Jalankan ulang dengan APPLY=1 untuk menerapkan.")
else:
    for asset, ou in to_write:
        asset.l10n_ou_analytic_id = ou
    env.cr.commit()
    print("\nDITERAPKAN: %d aset." % len(to_write))
    sample = to_write[:3]
    for asset, ou in sample:
        print("   %s -> %s  distribution=%s" % (asset.code, ou.name, asset.analytic_distribution))
