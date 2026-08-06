# Selesaikan receipt pengganti HANYA untuk PO yang dulu sudah sempat di-GR -- prd_levis_begbal.
#
# Insiden 06-Aug-2026 (lihat 85/86/87/88/89). Dari 18 PO yang kolom Quantity/Unit Price-nya
# tertukar, hanya SATU yang receipt-nya sempat divalidasi: PO/T/EBR/2026/08/00132, lewat
# 27917/IN/00001 senilai Rp 191.294.913 -- yang kemudian diretur dan jurnalnya di-reverse
# penuh. Empat belas PO lain receipt-nya cuma dibatalkan, tidak pernah membukukan apa pun.
#
# Permintaan klien: receipt pengganti yang berstatus Ready diselesaikan HANYA untuk PO yang
# dulu sudah ter-GR, dengan nilai yang MERUJUK pada nilai GR lama itu. PO yang belum pernah
# di-GR dibiarkan Ready sampai barangnya benar-benar datang.
#
# Rujukan nilainya bukan sekadar formalitas -- ia dipakai sebagai pagar yang mengunci:
# script menolak jalan kalau nilai GR baru tidak persis sama dengan GR lama. Kesamaan itu
# memang harus terjadi, karena swap kolom mempertahankan qty x harga, jadi 124.233.901 pcs
# @ Rp 1..7 dan 351 pcs @ Rp 222.362..1.588.688 bernilai sama: Rp 191.294.913. Kalau suatu
# saat angkanya meleset, berarti ada yang berubah di luar sepengetahuan kita dan receipt
# TIDAK boleh divalidasi.
#
#   docker exec -i -e GR_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal \
#       --no-http < scripts/tenants/levis/90_receive_gr_for_previously_received_po.py
#
# Env flags:  GR_DRY=1     -> laporkan lalu rollback (default; 0 = commit)
#             GR_PO        -> nomor PO (default PO/T/EBR/2026/08/00132)
#             GR_OLD_PICKING -> receipt lama yang jadi rujukan nilai (default 319)
import os

env = env  # noqa: F821  (injected by odoo shell)
log = lambda m: print("[gr] " + m)

COMPANY_ID = 1
DRY = os.environ.get("GR_DRY", "1") == "1"
PO_NAME = os.environ.get("GR_PO", "PO/T/EBR/2026/08/00132")
OLD_PICKING = int(os.environ.get("GR_OLD_PICKING", "319"))

cr = env.cr
company = env["res.company"].browse(COMPANY_ID)

# ---------------------------------------------------------------- guards ---
order = env["purchase.order"].search([("name", "=", PO_NAME), ("company_id", "=", COMPANY_ID)], limit=1)
if not order:
    raise SystemExit("PO %s tidak ditemukan -- batal" % PO_NAME)
if order.state != "purchase":
    raise SystemExit("PO %s berstatus %s, seharusnya purchase -- batal" % (PO_NAME, order.state))

# PO ini harus memang yang dulu sudah ter-GR; kalau tidak, script salah sasaran.
old = env["stock.picking"].browse(OLD_PICKING).exists()
if not old or old.state != "done":
    raise SystemExit("receipt lama %s tidak ada atau bukan done -- batal" % OLD_PICKING)
if old not in order.picking_ids:
    raise SystemExit("receipt lama %s bukan milik %s -- batal" % (old.name, PO_NAME))

# Baris PO harus sudah ditukar balik (86), kalau belum kita akan menerima angka ngawur.
swapped = order.order_line.filtered(
    lambda l: not l.display_type and l.product_qty >= 1000.0 and 0 < l.price_unit <= 100.0
)
if swapped:
    raise SystemExit("%d baris PO masih tertukar -- jalankan 86 dulu, batal" % len(swapped))

ready = order.picking_ids.filtered(lambda p: p.state == "assigned")
if len(ready) != 1:
    raise SystemExit("diharapkan 1 receipt Ready, ditemukan %d -- batal" % len(ready))
picking = ready

short = picking.move_ids.filtered(lambda m: m.quantity != m.product_uom_qty)
if short:
    raise SystemExit("%d baris belum ter-reserve penuh -- akan jadi backorder, batal" % len(short))

# --------------------------------------------- rujukan: nilai GR yang lama ---
# GR lama membukukan satu jurnal per baris; itulah nilai yang harus direproduksi.
old_jes = env["account.move"].search(
    [("ref", "in", ["GR-VAL:%s" % m for m in old.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
if not old_jes:
    raise SystemExit("tidak ada jurnal GR lama sebagai rujukan -- batal")
old_by_account = {}
for line in old_jes.line_ids:
    old_by_account[line.account_id.id] = round(
        old_by_account.get(line.account_id.id, 0.0) + line.debit - line.credit, 2
    )
old_total = round(sum(v for v in old_by_account.values() if v > 0), 2)

new_total = round(
    sum(m.product_uom_qty * m.purchase_line_id.price_unit for m in picking.move_ids if m.purchase_line_id), 2
)
accounts = env["account.account"].browse(sorted(old_by_account)).with_company(company)

log(
    "PO %s -- receipt lama %s Rp %s, receipt baru %s Rp %s"
    % (
        PO_NAME,
        old.name,
        old_total,
        picking.name,
        new_total,
    )
)
log(
    "kuantitas: lama %s pcs -> baru %s pcs"
    % (
        round(sum(old.move_ids.mapped("quantity")), 2),
        round(sum(picking.move_ids.mapped("product_uom_qty")), 2),
    )
)

if new_total != old_total:
    raise SystemExit(
        "nilai GR baru Rp %s TIDAK sama dengan GR lama Rp %s -- ada yang berubah, batal" % (new_total, old_total)
    )
log("nilai GR baru cocok persis dengan GR lama yang dibatalkan -- lanjut")


# --------------------------------------------------------------- snapshot ---
def quants_by_usage():
    cr.execute(
        """select l.usage, coalesce(sum(q.quantity),0)
             from stock_quant q join stock_location l on l.id=q.location_id group by l.usage"""
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


def balances():
    cr.execute(
        """select l.account_id, coalesce(sum(l.debit-l.credit),0)
             from account_move_line l join account_move m on m.id=l.move_id
            where m.state='posted' and l.company_id=%s and l.account_id in %s
            group by l.account_id""",
        (COMPANY_ID, tuple(old_by_account)),
    )
    return {r[0]: round(float(r[1]), 2) for r in cr.fetchall()}


demand = round(sum(picking.move_ids.mapped("product_uom_qty")), 2)
before = {"quants": quants_by_usage(), "gl": balances()}
log("sebelum: stok %s" % before["quants"])
log("sebelum: GL %s" % {a.code: before["gl"].get(a.id, 0.0) for a in accounts})

# ------------------------------------------------------------- 1. validasi ---
picking.button_validate()
picking.invalidate_recordset(["state"])
if picking.state != "done":
    raise SystemExit("%s berakhir di status %s -- batal" % (picking.name, picking.state))
log("receipt %s divalidasi" % picking.name)

env.flush_all()
env.invalidate_all()

# -------------------------------------------------------------- 2. verifikasi ---
problems = []

backorders = env["stock.picking"].search([("backorder_id", "=", picking.id)])
if backorders:
    problems.append("muncul backorder: %s" % backorders.mapped("name"))

received = round(sum(order.order_line.mapped("qty_received")), 2)
if received != demand:
    problems.append("qty_received %s, seharusnya %s" % (received, demand))

after = {"quants": quants_by_usage(), "gl": balances()}
log("sesudah: stok %s" % after["quants"])
log("sesudah: GL %s" % {a.code: after["gl"].get(a.id, 0.0) for a in accounts})

expected_internal = round(before["quants"].get("internal", 0.0) + demand, 2)
if after["quants"].get("internal", 0.0) != expected_internal:
    problems.append("stok internal %s, seharusnya %s" % (after["quants"].get("internal"), expected_internal))

new_jes = env["account.move"].search(
    [("ref", "in", ["GR-VAL:%s" % m for m in picking.move_ids.ids]), ("company_id", "=", COMPANY_ID)]
)
booked = round(sum(new_jes.line_ids.mapped("debit")), 2)
log("jurnal GR baru: %d entri, Rp %s" % (len(new_jes), booked))
if len(new_jes) != len(picking.move_ids):
    problems.append("diharapkan %d jurnal, ada %d" % (len(picking.move_ids), len(new_jes)))
if set(new_jes.mapped("state")) - {"posted"}:
    problems.append("ada jurnal yang belum posted")
if booked != old_total:
    problems.append("jurnal baru Rp %s, GR lama Rp %s" % (booked, old_total))

# per akun pun harus sama dengan GR lama, bukan cuma totalnya
for acc in accounts:
    delta = round(after["gl"].get(acc.id, 0.0) - before["gl"].get(acc.id, 0.0), 2)
    want = old_by_account[acc.id]
    log("GL %s (%s): %+.2f, GR lama %+.2f" % (acc.code, acc.display_name, delta, want))
    if delta != want:
        problems.append("GL %s bergeser %s, GR lama %s" % (acc.code, delta, want))

cr.execute(
    "select count(*) from stock_quant where quantity < 0 and location_id in "
    "(select id from stock_location where usage='internal')"
)
if cr.fetchone()[0]:
    problems.append("ada quant internal negatif")

# PO lain yang belum pernah di-GR harus TIDAK tersentuh
others = env["stock.picking"].search(
    [
        ("picking_type_id", "=", picking.picking_type_id.id),
        ("state", "=", "assigned"),
        ("origin", "like", "PO/T/EBR/2026/08/001%"),
    ]
)
log("receipt PO lain yang dibiarkan Ready: %d (%s)" % (len(others), ", ".join(others.mapped("origin")[:5]) + " ..."))

if problems:
    for p in problems:
        log("MASALAH: " + p)
    cr.rollback()
    raise SystemExit("verifikasi gagal -- rollback, tidak ada yang berubah")

log("verifikasi OK -- %s pcs diterima, Rp %s masuk persediaan lawan GR/IR" % (demand, booked))
log("nilainya persis mereproduksi GR lama yang dibatalkan")

if DRY:
    cr.rollback()
    log("GR_DRY=1 -> rollback, database tidak tersentuh")
else:
    cr.commit()
    log("committed")
