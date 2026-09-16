# Perbaikan PPN Masukan yang terkapitalisasi ke persediaan -- prd_levis_begbal.
#
# Dijalankan lewat odoo shell (butuh ORM):
#   docker exec -i odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
#       --shell-interface=python < scripts/tenants/levis/85_fix_po_ppn_included.py
#
# Env:  CONFIRM=1     -> benar-benar menulis + commit per dokumen GR.
#                        Tanpa ini: DRY RUN, rollback tiap dokumen GR.
#       TAX_ID=21     -> pajak pembelian 12% included yang dipasang ke baris PO.
#       LIMIT=n       -> proses n dokumen GR pertama saja (untuk uji coba).
#       ONE_DATE=...  -> paksa semua jurnal koreksi ke satu tanggal. Default:
#                        akhir bulan periode GR masing-masing.
#       EXCLUDE_GR=   -> daftar nama dokumen GR (pisah koma) yang tidak dikoreksi.
#                        Default mengecualikan 27917/IN/00001: GR itu masuk dengan
#                        qty/harga TERTUKAR (124 juta pcs @ Rp 1) dan sudah diretur
#                        lewat 27917/OUT/00005, tetapi jurnal retur (GR-RET-VAL:)
#                        tidak pernah terbit -- jadi GL-nya harus dibereskan dulu
#                        sebelum koreksi PPN menyentuhnya.
#
# --------------------------------------------------------------------------
# Latar
# --------------------------------------------------------------------------
# PO dibuat lewat import Excel. Import melewati onchange_product_id(), satu-satunya
# tempat Odoo 19 mengisi purchase.order.line.tax_ids. Akibatnya tax_ids kosong, dan
# _get_gross_price_unit() (purchase/models/purchase_order_line.py:484) memakai harga
# bruto apa adanya sebagai harga pokok -- padahal harga PO sudah termasuk PPN (DPP
# nilai lain 11/12, PMK 11/2025, tarif efektif 11%). Jurnal GR custom
# (custom_levis_localization, ref GR-VAL:<stock_move_id>) lalu membukukan
# Dr Persediaan / Cr GR-IR sebesar bruto -- PPN Masukan ikut terkapitalisasi.
#
# --------------------------------------------------------------------------
# Cara kerja: per DOKUMEN GR (stock.picking), bukan sekali jalan
# --------------------------------------------------------------------------
# Basis data ini HIDUP -- tim masih menerima barang saat skrip berjalan. Versi
# sebelumnya memproses 20 ribu baris dalam satu transaksi dan menahan row lock
# selama 22 menit. Sekarang tiap dokumen GR diproses lalu di-commit sendiri:
# lock hanya dipegang beberapa detik, bisa dihentikan di tengah jalan, dan aman
# diulang (idempotent lewat ref jurnal).
#
# Untuk tiap dokumen GR:
#   1. Isi tax_ids pada baris PO yang kosong.
#   2. moves._set_value() -- Odoo menurunkan ulang nilai move lewat jalur aslinya,
#      _get_value_from_quotation() (purchase_stock/models/stock_move.py:225) ->
#      _get_stock_move_price_unit() -> compute_all()['total_void'] = DPP.
#      standard_price ikut dihitung ulang oleh _update_standard_price().
#   3. Satu jurnal koreksi atas selisihnya, ref PPN-INC-KOREKSI:<nama GR>,
#      bertanggal akhir bulan periode GR itu. Akun & analytic OU disalin dari
#      jurnal GR asli supaya saldo tetap bisa diiris per store.
#      Jurnal GR lama idempotent per ref dan sudah posted -- tidak bisa
#      mengoreksi dirinya sendiri, jadi koreksi dibukukan terpisah.

import calendar
import json
import os
import sys
import traceback
from collections import defaultdict
from datetime import date

from odoo import fields

CONFIRM = os.environ.get("CONFIRM") == "1"
TAX_ID = int(os.environ.get("TAX_ID", "21"))
LIMIT = int(os.environ.get("LIMIT", "0"))
ONE_DATE = os.environ.get("ONE_DATE") or None
EXCLUDE_GR = {s.strip() for s in os.environ.get("EXCLUDE_GR", "27917/IN/00001").split(",") if s.strip()}

MODE = "EKSEKUSI (commit per GR)" if CONFIRM else "DRY RUN (rollback per GR)"
print("=" * 84, flush=True)
print(f"85_fix_po_ppn_included  --  {MODE}", flush=True)
print("=" * 84, flush=True)

company = env["res.company"].browse(1)
env = env(context=dict(env.context, allowed_company_ids=[company.id]))
tax = env["account.tax"].browse(TAX_ID)
if not tax.exists():
    raise SystemExit(f"tax id {TAX_ID} tidak ada")
inc = tax.price_include_override or company.account_price_include
print(f"Pajak : [{tax.id}] {tax.name} | amount={tax.amount} | include={inc}", flush=True)
if inc != "tax_included":
    raise SystemExit("pajak yang dipilih bukan tax_included -- harga PO sudah termasuk PPN")

cur = company.currency_id
KOREKSI_REF = "PPN-INC-KOREKSI:%s"


def tanggal_koreksi(d):
    """Akhir bulan periode GR -- tapi tidak pernah melewati hari ini.

    account.move._post() default-nya soft=True: entri bertanggal MASA DEPAN tidak
    diposting, melainkan ditandai auto_post='at_date' dan dibiarkan draft sampai
    tanggal itu tiba. Untuk GR bulan berjalan, akhir bulan masih di depan, jadi
    jurnalnya akan menggantung. Karena itu dibatasi ke hari ini.
    """
    akhir = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    return str(min(akhir, fields.Date.context_today(env["account.move"])))


# --------------------------------------------------------------------------
# Populasi: dokumen GR yang punya move masuk dari PO dan sudah selesai
# --------------------------------------------------------------------------
moves_all = env["stock.move"].search(
    [
        ("purchase_line_id", "!=", False),
        ("state", "=", "done"),
        ("company_id", "=", company.id),
        ("picking_id", "!=", False),
    ]
)
moves_all = moves_all.filtered(lambda m: m.is_in)
pickings = moves_all.picking_id.sorted("id")
print(f"Populasi: {len(pickings)} dokumen GR, {len(moves_all):,} move", flush=True)

sudah = set(
    env["account.move"].search([("ref", "=like", "PPN-INC-KOREKSI:%"), ("company_id", "=", company.id)]).mapped("ref")
)
if sudah:
    print(f"  {len(sudah)} dokumen GR sudah pernah dikoreksi -- akan dilewati", flush=True)

if EXCLUDE_GR:
    kena = [p.name for p in pickings if p.name in EXCLUDE_GR]
    print(f"  dikecualikan manual: {', '.join(kena) if kena else '(tidak ada di populasi)'}", flush=True)

antrian = [p for p in pickings if KOREKSI_REF % p.name not in sudah and p.name not in EXCLUDE_GR]
if LIMIT:
    antrian = antrian[:LIMIT]
print(f"Antrian : {len(antrian)} dokumen GR\n", flush=True)

journal = (
    env["product.category"].search([("property_stock_journal", "!=", False)], limit=1).property_stock_journal
    or company.account_stock_journal_id
)
if not journal:
    raise SystemExit("jurnal persediaan tidak ketemu")
print(f"Jurnal  : {journal.name}\n", flush=True)

tot_bruto = tot_dpp = tot_ppn = 0.0
n_ok = n_skip = n_gagal = 0
rekap_akun = defaultdict(float)
gagal = []

for idx, picking in enumerate(antrian, start=1):
    ref = KOREKSI_REF % picking.name
    try:
        moves = picking.move_ids.filtered(lambda m: m.state == "done" and m.is_in and m.purchase_line_id)
        if not moves:
            n_skip += 1
            continue

        # Jurnal GR asli -> sumber akun + analytic OU, dan bukti nilai yang dibukukan.
        gr_refs = [f"GR-VAL:{m.id}" for m in moves]
        gr_moves = env["account.move"].search(
            [
                ("ref", "in", gr_refs),
                ("company_id", "=", company.id),
                ("state", "=", "posted"),
            ]
        )
        gr_by_ref = {am.ref: am for am in gr_moves}
        if not gr_by_ref:
            print(f"[{idx}/{len(antrian)}] {picking.name}: tidak ada jurnal GR posted -- dilewati", flush=True)
            n_skip += 1
            continue

        before = {m.id: m.value for m in moves}

        # 1. isi pajak pada baris PO yang kosong
        lines = moves.purchase_line_id
        kosong = lines.filtered(lambda l: not l.tax_ids)
        if kosong:
            kosong.write({"tax_ids": [(6, 0, [TAX_ID])]})
        lain = lines.filtered(lambda l: l.tax_ids and l.tax_ids.ids != [TAX_ID])

        # 2. hitung ulang nilai move dari baris PO
        moves._set_value()
        env.flush_all()

        after = {m.id: m.value for m in moves}
        b = sum(before.values())
        a = sum(after.values())
        d = b - a
        if cur.is_zero(d):
            print(f"[{idx}/{len(antrian)}] {picking.name}: tidak ada selisih -- dilewati", flush=True)
            env.cr.rollback()
            n_skip += 1
            continue
        rasio = b / a if a else 0
        if not (1.105 < rasio < 1.115):
            raise ValueError(f"rasio bruto/DPP {rasio:.6f} di luar dugaan (bruto {b:,.2f} dpp {a:,.2f})")

        # 3. jurnal koreksi, dikelompokkan per (akun persediaan, akun GR/IR, analytic OU)
        buckets = defaultdict(float)
        tanggal_gr = None
        for m in moves:
            delta = before[m.id] - after[m.id]
            if not delta:
                continue
            am = gr_by_ref.get(f"GR-VAL:{m.id}")
            if not am:
                continue
            dr = am.line_ids.filtered(lambda l: l.debit > 0)[:1]
            cr_ = am.line_ids.filtered(lambda l: l.credit > 0)[:1]
            if not dr or not cr_:
                continue
            tanggal_gr = tanggal_gr or am.date
            key = (dr.account_id.id, cr_.account_id.id, json.dumps(dr.analytic_distribution or {}, sort_keys=True))
            buckets[key] += delta

        tanggal = ONE_DATE or tanggal_koreksi(tanggal_gr)
        label = f"Koreksi PPN Masukan atas GR {picking.name} -- harga PO sudah termasuk PPN (DPP 11/12)"
        line_vals = []
        dibukukan = 0.0
        for (val_acc, grir_acc, ou), amt in sorted(buckets.items()):
            amt = cur.round(amt)
            if cur.is_zero(amt):
                continue
            ou = json.loads(ou) or False
            dibukukan += amt
            rekap_akun[grir_acc] += amt
            rekap_akun[-val_acc] -= amt
            line_vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": grir_acc,
                        "name": label,
                        "debit": amt,
                        "credit": 0.0,
                        "analytic_distribution": ou,
                    },
                )
            )
            line_vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": val_acc,
                        "name": f"Keluarkan PPN Masukan dari harga pokok persediaan -- {picking.name}",
                        "debit": 0.0,
                        "credit": amt,
                        "analytic_distribution": ou,
                    },
                )
            )
        if not line_vals:
            env.cr.rollback()
            n_skip += 1
            continue

        koreksi = env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": company.id,
                "date": tanggal,
                "ref": ref,
                "line_ids": line_vals,
            }
        )
        koreksi._post()
        env.flush_all()

        tot_bruto += b
        tot_dpp += a
        tot_ppn += dibukukan
        n_ok += 1
        catatan = f" | {len(lain)} baris PO sudah berpajak lain" if lain else ""
        print(
            f"[{idx}/{len(antrian)}] {picking.name} {tanggal} | {len(moves):>4} move | "
            f"bruto {b:>16,.2f} -> DPP {a:>16,.2f} | koreksi {dibukukan:>14,.2f} | "
            f"{len(line_vals) // 2} pasang baris{catatan}",
            flush=True,
        )

        if CONFIRM:
            env.cr.commit()
        else:
            env.cr.rollback()
    except Exception as exc:  # noqa: BLE001 -- satu GR gagal tidak boleh menghentikan sisanya
        env.cr.rollback()
        n_gagal += 1
        gagal.append((picking.name, str(exc)))
        print(f"[{idx}/{len(antrian)}] {picking.name}: GAGAL -- {exc}", flush=True)
        traceback.print_exc(file=sys.stdout)

# --------------------------------------------------------------------------
# Rekap
# --------------------------------------------------------------------------
print("\n" + "=" * 84, flush=True)
print(f"Dokumen GR dikoreksi : {n_ok}   dilewati: {n_skip}   gagal: {n_gagal}", flush=True)
print(f"Nilai bruto          : {tot_bruto:>20,.2f}", flush=True)
print(f"Nilai DPP            : {tot_dpp:>20,.2f}", flush=True)
print(f"PPN dikoreksi        : {tot_ppn:>20,.2f}", flush=True)
if tot_dpp:
    print(f"Rasio bruto/DPP      : {tot_bruto / tot_dpp:.6f}", flush=True)
print("\nRekap koreksi per akun:", flush=True)
for acc_id, amt in sorted(rekap_akun.items(), key=lambda kv: abs(kv[0])):
    acc = env["account.account"].browse(abs(acc_id))
    sisi = "Debit " if amt > 0 else "Kredit"
    print(f"  {acc.code:<12} {acc.display_name[:48]:<50} {sisi} {abs(amt):>18,.2f}", flush=True)
if gagal:
    print("\nGagal:", flush=True)
    for nm, err in gagal:
        print(f"  {nm}: {err}", flush=True)
if not CONFIRM:
    print("\nDRY RUN -- semua di-rollback. Jalankan ulang dengan CONFIRM=1 saat jam sepi.", flush=True)
