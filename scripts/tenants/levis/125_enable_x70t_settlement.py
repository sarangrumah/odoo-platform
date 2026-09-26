"""Nyalakan settlement X70T, dan susulkan hari-hari yang tendernya belum masuk.

LATAR: sejak 16-Sep-2026 POS Levi's mengeluarkan tender ber-acquirer (BCA_QRIS,
BCA_DEBIT_GPN, BRI_REGULAR_OFF_US, MANDIRI_QRIS, ... 14 kode). **X70D tidak memuat
baris-baris itu sama sekali** -- bukan terlambat, bukan dilebur ke kode kasar: dari
87 pasang file malam, X70D dan X70T cocok sampai rupiah pada hari yang hanya memakai
kosakata OFFLINE_*/CASH, dan X70D kurang PERSIS sebesar tender ber-acquirer pada hari
yang memakainya. X24DN tetap menagih penuh (penjualan per toko = tender X70T per toko,
sampai rupiah), jadi selisihnya menginap di POS Suspense Clearing.

X70T memuatnya: per toko, per hari dagang, per terminal, satu kolom per tender.
``_post_x70t_settlement`` memposting SELISIH antara yang dilaporkan X70T dan yang
sudah diselesaikan hari itu, jadi urutan X70D/X70T tidak penting dan menjalankannya
dua kali tidak menggandakan apa pun.

    docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \\
        --shell-interface=python < scripts/tenants/levis/125_enable_x70t_settlement.py

Env:
  CONFIRM=1   -> menulis + commit. Tanpa itu: DRY RUN (rollback di akhir).
  SINCE=YYYYMMDD -> susulkan file X70T dari tanggal itu (default: tidak menyusul).

--------------------------------------------------------------------------
Yang diubah
--------------------------------------------------------------------------
1. ``retail.import.profile`` ``levis_x70t`` -- dibuat oleh modul 19.0.0.27.0.
2. Feed "Levi's X70T" diarahkan ke profile itu (di DB lama ia menunjuk
   ``levis_x70``, yang column_map-nya berhenti di dua kolom tender pertama),
   sequence 60 supaya jalan SESUDAH X70D (20) pada hari yang sama.
3. Mailbox X-center: ``ingest_glob`` ditambah ``X70T*.xlsx``. Selama ini file X70T
   hanya diarsipkan ke backup_dir dan tidak pernah sampai ke drop folder.
4. ``retail_import.x70t_post_enabled`` = 1.

Keduanya (2 dan 3) record operasional ber-``noupdate="1"``: upgrade modul TIDAK
menyentuhnya, jadi harus lewat skrip ini.
"""

import base64
import glob
import os
import re

CONFIRM = os.environ.get("CONFIRM") == "1"
SINCE = os.environ.get("SINCE", "")
MAILBOX_DIR = "/mnt/data_levis/mailbox"

Param = env["ir.config_parameter"].sudo()
profile = env["retail.import.profile"].search([("file_type", "=", "x70t")], limit=1)
if not profile:
    raise SystemExit("profile x70t tidak ada -- upgrade custom_retail_import ke 19.0.0.27.0 dulu")
print(f"profile  : {profile.code} (data_start_row={profile.data_start_row}, require={profile.require_fields})")

# --- 2. feed ---------------------------------------------------------------
feed = env["retail.import.feed"].search([("file_glob", "=like", "X70T%")], limit=1)
if feed:
    before = feed.profile_id.code
    feed.write({"profile_id": profile.id, "sequence": 60, "active": True})
    print(f"feed     : {feed.name} | profile {before} -> {profile.code}, sequence 60, active")
else:
    feed = env["retail.import.feed"].create(
        {
            "name": "Levi's X70T — Tender Settlement (FTPS drop)",
            "sequence": 60,
            "profile_id": profile.id,
            "source_type": "local",
            "local_dir": "/mnt/data_levis/data",
            "archive_dir": "/mnt/data_levis/archive",
            "file_glob": "X70T*.xlsx",
            "company_id": profile.company_id.id,
        }
    )
    print(f"feed     : dibuat ({feed.name})")

# --- 3. mailbox glob -------------------------------------------------------
for mb in env["retail.import.mailbox"].search([("sender_filter", "like", "levi.com")]):
    globs = [g.strip() for g in (mb.ingest_glob or "").split(",") if g.strip()]
    if not any(g.upper().startswith("X70T") for g in globs):
        globs.append("X70T*.xlsx")
        mb.ingest_glob = ",".join(globs)
        print(f"mailbox  : {mb.name} | ingest_glob -> {mb.ingest_glob}")
    else:
        print(f"mailbox  : {mb.name} | ingest_glob sudah memuat X70T")

# --- 4. switch -------------------------------------------------------------
Param.set_param("retail_import.x70t_post_enabled", "1")
print("param    : retail_import.x70t_post_enabled = 1")

# --- catch-up --------------------------------------------------------------
if SINCE:
    files = sorted(glob.glob(f"{MAILBOX_DIR}/*/*/X70T_*.xlsx"))
    files = [f for f in files if (re.search(r"__(\d{8})T", os.path.basename(f)) or [None, ""])[1] >= SINCE]
    print(f"\nsusulan  : {len(files)} file X70T sejak {SINCE}")
    for path in files:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        log = env["retail.import.log"].create({"profile_id": profile.id, "filename": os.path.basename(path)})
        env["retail.import.executor"]._load_x70t(profile, b64, log)
        print(f"  {os.path.basename(path)[:50]:<50} {log.records_created} move | {(log.error_message or '')[:100]}")

env.cr.execute(
    """
    select aml.date, round(sum(aml.debit - aml.credit)) as open
    from account_move_line aml
    join account_account a on a.id = aml.account_id
    join account_move m on m.id = aml.move_id
    where a.name ->> 'en_US' = 'POS Suspense Clearing' and m.state = 'posted'
      and aml.date >= date '2026-09-01'
    group by 1 having round(sum(aml.debit - aml.credit)) <> 0 order by 1
    """
)
rows = env.cr.fetchall()
print("\nPOS Suspense Clearing yang masih terbuka (September):")
for d, amount in rows:
    print(f"  {d}  {amount:>15,.0f}")
print(f"  {'TOTAL':<10} {sum(r[1] for r in rows):>15,.0f}")

if CONFIRM:
    env.cr.commit()
    print("\nCOMMIT")
else:
    env.cr.rollback()
    print("\nDRY RUN -- rollback. Jalankan ulang dengan CONFIRM=1 untuk menulis.")
