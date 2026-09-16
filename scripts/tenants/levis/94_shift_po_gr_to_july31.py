# Menggeser PO + GR + jurnalnya ke 31 Juli 2026 -- prd_levis_begbal.
#
# Dijalankan lewat odoo shell (butuh ORM):
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       --shell-interface=python < scripts/tenants/levis/94_shift_po_gr_to_july31.py
#
# Env:  CONFIRM=1         -> benar-benar menulis + commit. Tanpa ini: DRY RUN
#                            (semua di-rollback di akhir).
#       PO_IDS=504,506    -> id purchase.order yang digeser. Default:
#                            504 = PO/T/EBR/2026/07/00104
#                            506 = PO/T/EBR/2026/07/00105
#       TARGET=2026-07-31 -> tanggal akuntansi tujuan.
#       TARGET_TIME=03:00 -> jam UTC untuk field datetime (03:00 UTC = 10:00 WIB,
#                            supaya tanggalnya tetap 31 Juli baik di UTC maupun WIB).
#
# --------------------------------------------------------------------------
# Latar
# --------------------------------------------------------------------------
# Dua PO ini bertanggal 31 Juli 2026 (WIB) tetapi barangnya baru di-GR tanggal
# 5 Agustus, sehingga 200 jurnal valuasi GR (ref GR-VAL:<stock_move_id>) jatuh di
# Agustus, ditambah 2 jurnal koreksi PPN included (ref PPN-INC-KOREKSI:<nama GR>)
# tanggal 6 Agustus. Persediaan dan GR/IR-nya jadi tidak nyambung dengan PO-nya.
# Periode Juli masih terbuka (fiscalyear_lock_date = 2026-06-30), jadi aman
# dibukukan ulang di sana.
#
# --------------------------------------------------------------------------
# Cara kerja
# --------------------------------------------------------------------------
# 1. purchase.order : date_order + date_approve -> TARGET.
# 2. stock.picking  : scheduled_date + date_done -> TARGET; stock.move dan
#                     stock.move.line ikut digeser supaya laporan persediaan
#                     (yang membaca stock_move.date) konsisten dengan GL.
# 3. account.move   : reset ke draft, name di-'/'-kan, date -> TARGET, lalu
#                     di-post ulang. Nama harus dilepas: prefix urutan Odoo
#                     memuat periode (STJ/2026/08/...), kalau tanggalnya digeser
#                     tanpa melepas nama, entri Juli akan bernomor Agustus dan
#                     _check_sequence_mixin menolaknya. Setelah post ulang entri
#                     mendapat nomor di ekor urutan Juli (STJ/2026/07/...).
#
# Dikerjakan per dokumen GR lalu commit sendiri-sendiri: lock tidak dipegang
# lama dan skrip aman dihentikan/diulang di tengah jalan.

import os
import sys
import traceback
from collections import defaultdict

CONFIRM = os.environ.get("CONFIRM") == "1"
PO_IDS = [int(s) for s in os.environ.get("PO_IDS", "504,506").split(",") if s.strip()]
TARGET = os.environ.get("TARGET", "2026-07-31")
TARGET_TIME = os.environ.get("TARGET_TIME", "03:00")
TARGET_DT = f"{TARGET} {TARGET_TIME}:00"

MODE = "EKSEKUSI (commit per GR)" if CONFIRM else "DRY RUN (rollback di akhir)"
print("=" * 84, flush=True)
print(f"94_shift_po_gr_to_july31  --  {MODE}", flush=True)
print(f"Target: {TARGET} (datetime {TARGET_DT} UTC)", flush=True)
print("=" * 84, flush=True)

orders = env["purchase.order"].browse(PO_IDS).exists()
if len(orders) != len(PO_IDS):
    raise SystemExit(f"PO tidak lengkap: minta {PO_IDS}, ketemu {orders.ids}")

company = orders.company_id
if len(company) != 1:
    raise SystemExit("PO lintas company -- hentikan")
env = env(context=dict(env.context, allowed_company_ids=company.ids))
orders = orders.with_company(company)

lock = company.fiscalyear_lock_date
if lock and str(lock) >= TARGET:
    raise SystemExit(f"fiscalyear_lock_date = {lock} menutup {TARGET}")

AccountMove = env["account.move"]


def jurnal_untuk(picking):
    """Jurnal valuasi GR + jurnal koreksi PPN milik satu dokumen GR."""
    refs = [f"GR-VAL:{m.id}" for m in picking.move_ids]
    refs.append(f"PPN-INC-KOREKSI:{picking.name}")
    return AccountMove.search(
        [
            ("ref", "in", refs),
            ("company_id", "=", company.id),
        ]
    )


# --------------------------------------------------------------------------
# Ringkasan sebelum bekerja
# --------------------------------------------------------------------------
rencana = []
for po in orders:
    pickings = po.order_line.move_ids.picking_id.sorted("id")
    for picking in pickings:
        moves = jurnal_untuk(picking)
        rencana.append((po, picking, moves))
        per_tanggal = defaultdict(int)
        for am in moves:
            per_tanggal[str(am.date)] += 1
        rincian = ", ".join(f"{d}: {n}" for d, n in sorted(per_tanggal.items()))
        print(
            f"{po.name} | {picking.name} | GR {picking.date_done} | "
            f"{len(picking.move_ids)} move | {len(moves)} jurnal ({rincian})",
            flush=True,
        )
        belum_posted = moves.filtered(lambda m: m.state != "posted")
        if belum_posted:
            print(f"    ! {len(belum_posted)} jurnal tidak berstatus posted: {belum_posted.mapped('name')}", flush=True)
        terekonsiliasi = moves.line_ids.filtered(lambda l: l.reconciled or l.matched_debit_ids or l.matched_credit_ids)
        if terekonsiliasi:
            print(
                f"    ! {len(terekonsiliasi)} baris sudah terekonsiliasi -- reset ke draft akan melepasnya", flush=True
            )

if not rencana:
    raise SystemExit("tidak ada dokumen GR untuk PO tersebut")

print("", flush=True)

# --------------------------------------------------------------------------
# Eksekusi
# --------------------------------------------------------------------------
n_ok = n_gagal = 0
gagal = []
digeser_po = set()

for idx, (po, picking, moves) in enumerate(rencana, 1):
    try:
        if po.id not in digeser_po:
            po.write({"date_order": TARGET_DT, "date_approve": TARGET_DT})
            digeser_po.add(po.id)

        picking.write({"scheduled_date": TARGET_DT, "date_done": TARGET_DT})
        picking.move_ids.write({"date": TARGET_DT})
        picking.move_ids.move_line_ids.write({"date": TARGET_DT})

        nama_lama = moves.mapped("name")
        moves.button_draft()
        moves.write({"name": "/", "date": TARGET})
        moves.action_post()

        salah = moves.filtered(lambda m: m.state != "posted" or str(m.date) != TARGET)
        if salah:
            raise ValueError(f"{len(salah)} jurnal gagal kembali ke posted/{TARGET}: {salah.ids}")

        print(
            f"[{idx}/{len(rencana)}] {picking.name}: {len(moves)} jurnal "
            f"{nama_lama[0]}..{nama_lama[-1]} -> {moves[0].name}..{moves[-1].name} @ {TARGET}",
            flush=True,
        )
        n_ok += 1
        if CONFIRM:
            env.cr.commit()
    except Exception as exc:  # noqa: BLE001 -- satu GR gagal tidak boleh menghentikan sisanya
        env.cr.rollback()
        digeser_po.discard(po.id)
        n_gagal += 1
        gagal.append((picking.name, str(exc)))
        print(f"[{idx}/{len(rencana)}] {picking.name}: GAGAL -- {exc}", flush=True)
        traceback.print_exc(file=sys.stdout)

print("\n" + "=" * 84, flush=True)
print(f"Dokumen GR digeser: {n_ok}   gagal: {n_gagal}", flush=True)
for nm, err in gagal:
    print(f"  {nm}: {err}", flush=True)
if not CONFIRM:
    env.cr.rollback()
    print("\nDRY RUN -- semua di-rollback. Ulangi dengan CONFIRM=1.", flush=True)
