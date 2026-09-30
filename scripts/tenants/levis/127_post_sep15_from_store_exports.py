"""Tutup POS Suspense Clearing 15-Sep-2026 dari ekspor X70D milik toko.

LATAR: malam 15-Sep-2026 X-center tidak mengirim satu pun laporan (lihat
`levis-x70d-feed-gaps-sep2026`). Penjualannya menyusul dimuat lewat X24DN pada 28-Sep,
jadi Dr POS Suspense Clearing terbentuk tanpa pernah ada laporan tender yang
memindahkannya ke POS Receivable per tender. Per 30-Sep-2026 yang terbuka di 15-Sep
adalah **Rp 273.186.750 di 20 toko**.

Sumber penggantinya ada di DB: sejak feed `x70d_store` dinyalakan 30-Sep-2026, ekspor
X70D yang dikirim toko sendiri sudah ter-stage (315 berkas, 67.601 baris). Untuk 15-Sep
ekspor itu cocok **sampai rupiah** dengan suspense yang terbuka di 16 dari 20 toko;
TP3 selisih Rp 50.000, dan 3 toko belum pernah mengirim (Trans Studio Cibubur, Paskal
Bandung, AEON BSD City) sehingga ~Rp 25,87 jt tetap harus ditagih ke X-center.

Masalahnya `x70d_store` adalah tipe **stage-only** (`_load_x70d_store` -> `_stage_only`):
ia sengaja tidak pernah memposting, karena X70D malam-lah yang jadi sumber kebenaran dan
memuat setiap toko. Untuk 15-Sep X70D malam itu tidak ada sama sekali, jadi skrip ini
menyusun ulang baris ekspor toko ke **bentuk kolom X70D korporat** dan memasukkannya lewat
profile `levis_x70d` yang biasa. Dengan begitu seluruh jalur yang sudah teruji yang bekerja:
staging, netting `_ri_settled_by_tender`, `_ri_post_tender_transfer`, lalu
`_ri_reconcile_suspense` -- dan baris 15-Sep akhirnya muncul juga di tender detail
`levis_pos_x70d_txn`, yang memang seharusnya begitu.

    docker exec -i odoo19-platform-odoo odoo shell -c /etc/odoo/odoo.conf \\
        -d prd_levis_begbal --no-http < scripts/tenants/levis/127_post_sep15_from_store_exports.py

Env:
  CONFIRM=1        -> menulis + commit. Tanpa itu DRY RUN: berkas disusun, netting
                      dihitung dan dicetak, lalu rollback. Tidak ada log/jurnal dibuat.
  DAY=YYYY-MM-DD   -> hari dagang yang ditutup (default 2026-09-15).
  OUT=/path.xlsx   -> simpan salinan berkas yang disusun (buat lampiran audit).

PERINGATAN: seperti 125_enable_x70t_settlement, bagian posting TIDAK BISA di-dry-run --
`_post_x70d_reconcile` memanggil `_ri_commit` sebelum skrip ini sempat rollback. Karena itu
`Executor.run` dikunci di belakang CONFIRM. Tidak berbahaya kalau terlanjur: posting menetting
terhadap yang sudah diselesaikan hari itu, jadi menjalankannya dua kali menghasilkan 0 move.

Yang SENGAJA dilewati: transaksi yang store/tanggal/register/transnum-nya sudah ada di
`levis_pos_x70d_txn` untuk hari itu. Tanpa penyaring ini, 9 toko baru (80680, 80741-80748)
yang 15-Sep-nya sudah dimuat manual 26-Sep akan masuk dua kali -- view itu tidak punya dedup,
dan itulah cara 96 baris duplikat lahir pada 28-29 Sep (lihat
`levis-x70d-manual-upload-pitfalls`).
"""

import base64
import io
import json
import os
from collections import defaultdict

import openpyxl

CONFIRM = os.environ.get("CONFIRM") == "1"
DAY = os.environ.get("DAY", "2026-09-15")
OUT = os.environ.get("OUT", "")

HEADER = [
    "STORE CODE",
    "SAP STORE CODE",
    "STORE NAME",
    "TRANS DATE",
    "REGISTER ",
    "TRANSNUM",
    "CASHIER LOGIN ID",
    "CASHIER NAME",
    "TENDER TYPE",
    "TENDER AMOUNT",
    "AUTH NUMBER",
    "VOUCHER NUMBER",
]

Profile = env["retail.import.profile"].sudo()
Log = env["retail.import.log"].sudo()
Executor = env["retail.import.executor"]

profile = Profile.search([("file_type", "=", "x70d")], limit=1)
if not profile:
    raise SystemExit("profile x70d tidak ada")
company = profile.company_id
print(f"profile  : {profile.code} (company {company.name})")
print(f"hari     : {DAY}   CONFIRM={'1' if CONFIRM else '0 (dry run)'}")

# ---------------------------------------------------------------- baris sumber
# Kiriman toko kumulatif: hari dagang yang sama datang berulang kali. Ambil baris
# yang PALING BARU di-stage per transaksi -- persis aturan yang dipakai view
# levis_mdr_txn, supaya koreksi kiriman terakhir yang menang.
env.cr.execute(
    """
    select distinct on (j->>'store_code', j->>'register', j->>'transnum')
           j->>'store_code'      as store_code,
           j->>'sap_store_code'  as sap_store_code,
           j->>'store_name'      as store_name,
           j->>'register'        as register,
           j->>'transnum'        as transnum,
           j->>'cashier_id'      as cashier_id,
           j->>'cashier_name'    as cashier_name,
           j->>'tender_type'     as tender_type,
           j->>'tender_amount'   as tender_amount
      from (
            select l.id, l.raw_data_json::json as j
              from retail_import_line l
              join retail_import_log g      on g.id = l.log_id
              join retail_import_profile p  on p.id = g.profile_id
             where p.file_type = 'x70d_store'
               and l.raw_data_json like '{%%'
               and l.raw_data_json::json->>'trans_date' = %s
           ) x
     order by j->>'store_code', j->>'register', j->>'transnum', id desc
    """,
    (DAY,),
)
rows = env.cr.dictfetchall()
print(f"baris ekspor toko untuk {DAY}: {len(rows)}")
if not rows:
    raise SystemExit("tidak ada baris ekspor toko untuk hari itu -- tidak ada yang bisa dilakukan")

# Transaksi yang sudah ada di tender detail: lewati, jangan gandakan.
env.cr.execute(
    "select store_code, register, transnum from levis_pos_x70d_txn where trans_date = %s",
    (DAY,),
)
already = {(r[0], r[1], r[2]) for r in env.cr.fetchall()}
fresh = [r for r in rows if (r["store_code"], r["register"], r["transnum"]) not in already]
skipped = len(rows) - len(fresh)
print(f"sudah ada di tender detail (dilewati): {skipped}")
print(f"akan dimasukkan: {len(fresh)}")
if not fresh:
    raise SystemExit("semua transaksi hari itu sudah ada di tender detail -- tidak ada yang perlu dimuat")


def _amount(value):
    try:
        return float(profile._parse_amount(value) or 0)
    except Exception:
        return 0.0


total_in = round(sum(_amount(r["tender_amount"]) for r in fresh), 2)
per_store = defaultdict(float)
for r in fresh:
    per_store[r["store_code"]] += _amount(r["tender_amount"])
print(f"nilai tender yang dimasukkan: {total_in:,.2f} di {len(per_store)} toko")

# ------------------------------------------------------------ susun berkas X70D
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Sheet1"
ws.append(HEADER)
for r in fresh:
    ws.append(
        [
            r["store_code"],
            r["sap_store_code"],
            r["store_name"],
            DAY,
            r["register"],
            r["transnum"],
            r["cashier_id"],
            r["cashier_name"],
            r["tender_type"],
            _amount(r["tender_amount"]),
            "",  # AUTH NUMBER -- kosong di feed malam, dikosongkan juga di sini
            "",  # VOUCHER NUMBER -- idem; label acquirer tetap hidup di baris x70d_store
        ]
    )
buf = io.BytesIO()
wb.save(buf)
raw = buf.getvalue()
file_b64 = base64.b64encode(raw).decode("ascii")
filename = "X70D_from_store_exports_%s.xlsx" % DAY.replace("-", "")
print(f"berkas disusun: {filename} ({len(raw)} byte, {len(fresh)} baris data)")
if OUT:
    with open(OUT, "wb") as fh:
        fh.write(raw)
    print(f"salinan audit  : {OUT}")

# ------------------------------------------------------------------- pratinjau
# Hitung netting yang sama seperti _post_x70d_reconcile supaya dry run jujur.
ns = profile.namespace
by_tender = defaultdict(float)
for r in fresh:
    tt = str(r["tender_type"] or "").strip()
    if not tt:
        continue
    tt = Executor._X24_TENDER_FOLD.get(tt, tt)
    cid = Executor._xid_get(ns, Executor._safe_xid("posconfig_", r["store_code"]), "pos.config")
    cfg = env["pos.config"].with_context(active_test=False).browse(cid) if cid else False
    ou = Executor._ri_config_ou(cfg) if cfg else False
    by_tender[(tt, ou.id if ou else False)] += _amount(r["tender_amount"])

gl_date = profile._parse_date(DAY)
settled = Executor._ri_settled_by_tender(company, gl_date)
netted = {k: round(a - settled.get(k, 0.0), 2) for k, a in by_tender.items()}
postable = {k: a for k, a in netted.items() if a > 0}
print(f"\npratinjau posting untuk {gl_date} (setelah netting):")
for (tender, ou_id), amt in sorted(postable.items()):
    ou = env["account.analytic.account"].browse(ou_id).name if ou_id else "(tanpa OU)"
    print(f"  {tender:28} {ou:38} {amt:>16,.2f}")
print(f"  {'TOTAL':28} {'':38} {sum(postable.values()):>16,.2f}")

susp = Executor._x24_suspense_account(company)
env.cr.execute(
    """select round(sum(aml.balance), 2)
         from account_move_line aml join account_move m on m.id = aml.move_id
        where aml.account_id = %s and m.state = 'posted' and aml.date = %s""",
    (susp.id, DAY),
)
before = env.cr.fetchone()[0] or 0
print(f"\nsuspense {DAY} sebelum: {before:,.2f}")

if not CONFIRM:
    env.cr.rollback()
    print("\nDRY RUN -- tidak ada log, tidak ada jurnal. Jalankan ulang dengan CONFIRM=1.")
else:
    file_hash = Log.compute_hash(raw)
    prior = Log.search([("profile_id", "=", profile.id), ("file_hash", "=", file_hash)], limit=1)
    if prior:
        raise SystemExit(f"berkas identik sudah pernah dimuat (log {prior.id}) -- berhenti")
    log = Log.create(
        {
            "profile_id": profile.id,
            "filename": filename,
            "file_hash": file_hash,
            "state": "queued",
        }
    )
    log.store_source(file_b64, filename)
    env.cr.commit()
    print(f"log dibuat: {log.id}")
    Executor.run(log)
    env.cr.commit()
    log.invalidate_recordset()
    print(f"state: {log.state} | created={log.records_created} | lines={log.line_count}")
    print(f"catatan: {log.error_message}")
    env.cr.execute(
        """select round(sum(aml.balance), 2)
             from account_move_line aml join account_move m on m.id = aml.move_id
            where aml.account_id = %s and m.state = 'posted' and aml.date = %s""",
        (susp.id, DAY),
    )
    after = env.cr.fetchone()[0] or 0
    print(f"suspense {DAY} sesudah: {after:,.2f}  (turun {before - after:,.2f})")
    env.cr.execute(
        """select m.name, m.ref, round(sum(aml.debit), 2)
             from account_move m join account_move_line aml on aml.move_id = m.id
            where m.date = %s and m.ref like %s and aml.debit > 0
            group by 1, 2 order by 1""",
        (DAY, "%%(log %s)" % log.id),
    )
    for name, ref, dr in env.cr.fetchall():
        print(f"move {name}: {ref}  Dr {dr:,.2f}")
    print(json.dumps({"log": log.id, "rows": len(fresh), "posted_total": sum(postable.values())}))
