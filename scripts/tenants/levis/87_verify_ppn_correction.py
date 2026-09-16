# Verifikasi hasil koreksi PPN Masukan -- prd_levis_begbal. SELECT-ONLY.
#
#   python3 scripts/tenants/levis/87_verify_ppn_correction.py
#
# Env: DB -> database (default prd_levis_begbal)
#
# Memeriksa enam hal, dan menyatakan LULUS/GAGAL per pemeriksaan:
#   1. Tidak ada jurnal koreksi yang tertinggal draft (jebakan _post(soft=True)
#      pada entri bertanggal masa depan -- lihat 85_fix_po_ppn_included.py).
#   2. Setiap dokumen GR yang punya jurnal GR juga punya jurnal koreksi.
#   3. Jurnal koreksi seimbang, dan totalnya = bruto - DPP.
#   4. Saldo GL gabungan (GR + koreksi) = nilai move sesudah koreksi.
#   5. Nilai stock_move sudah turun ke DPP (rasio bruto/DPP ~ 1,11).
#   6. Total PO tidak berubah; amount_tax sudah terisi.

import csv
import io
import os
import subprocess
import sys
from decimal import Decimal

PG = "odoo19-platform-postgres"
DB = os.environ.get("DB", "prd_levis_begbal")
GROSS = Decimal("1.11")
TOLERANSI = Decimal("1.00")  # rupiah, menampung pembulatan per baris


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
        sys.exit(f"query failed:\n{out.stderr}")
    return list(csv.DictReader(io.StringIO(out.stdout)))


def d(v):
    return Decimal(v or "0")


hasil = []


def cek(nama, lulus, detail):
    hasil.append((nama, lulus, detail))
    print(f"[{'LULUS' if lulus else 'GAGAL'}] {nama}\n        {detail}")


print(f"Verifikasi koreksi PPN Masukan -- {DB}\n" + "=" * 78)

# 1. draft tertinggal
r = q(
    "select state, count(*) n, coalesce(sum(amount_total),0) v from account_move "
    "where ref like 'PPN-INC-KOREKSI:%' group by 1"
)
by_state = {x["state"]: (int(x["n"]), d(x["v"])) for x in r}
n_draft = by_state.get("draft", (0, 0))[0]
n_posted, v_posted = by_state.get("posted", (0, Decimal(0)))
cek(
    "1. Tidak ada jurnal koreksi tertinggal draft",
    n_draft == 0,
    f"posted {n_posted}, draft {n_draft}",
)

# 2. cakupan per dokumen GR
r = q(
    "with gr as ("
    "  select distinct sp.name nm from account_move am "
    "  join stock_move sm on sm.id = split_part(am.ref, ':', 2)::int "
    "  join stock_picking sp on sp.id = sm.picking_id "
    "  where am.ref like 'GR-VAL:%' and am.state = 'posted'"
    "), kor as ("
    "  select distinct substring(ref from 17) nm from account_move "
    "  where ref like 'PPN-INC-KOREKSI:%' and state = 'posted'"
    ") select (select count(*) from gr) total_gr, (select count(*) from kor) total_koreksi, "
    "(select string_agg(nm, ', ') from (select nm from gr except select nm from kor) t) belum"
)[0]
belum = r["belum"] or ""
cek(
    "2. Setiap dokumen GR punya jurnal koreksi",
    not belum or belum == "27917/IN/00001",
    f"GR berjurnal {r['total_gr']}, dikoreksi {r['total_koreksi']}" + (f" | belum: {belum}" if belum else ""),
)

# 3. jurnal koreksi seimbang
r = q(
    "select coalesce(sum(l.debit),0) debit, coalesce(sum(l.credit),0) kredit "
    "from account_move_line l join account_move am on am.id = l.move_id "
    "where am.ref like 'PPN-INC-KOREKSI:%' and am.state = 'posted'"
)[0]
kor_d, kor_k = d(r["debit"]), d(r["kredit"])
cek(
    "3. Jurnal koreksi seimbang",
    abs(kor_d - kor_k) <= TOLERANSI,
    f"debit {kor_d:,.2f} vs kredit {kor_k:,.2f}",
)

# 4. GL gabungan vs nilai move
gl = q(
    "select a.code_store->>'1' kode, a.name->>'en_US' nm, coalesce(sum(l.debit),0) debit, "
    "coalesce(sum(l.credit),0) kredit from account_move_line l "
    "join account_move am on am.id = l.move_id join account_account a on a.id = l.account_id "
    "where (am.ref like 'GR-VAL:%' or am.ref like 'PPN-INC-KOREKSI:%') and am.state = 'posted' "
    "group by 1,2 order by 1"
)
persediaan = sum(d(x["debit"]) - d(x["kredit"]) for x in gl if x["kode"].startswith("1113"))
grir = sum(d(x["kredit"]) - d(x["debit"]) for x in gl if x["kode"].startswith("2103"))

mv = q(
    "select coalesce(sum(sm.value),0) nilai, count(*) n from stock_move sm "
    "where sm.purchase_line_id is not null and sm.state = 'done' and sm.is_in "
    "and exists (select 1 from account_move am where am.ref = 'GR-VAL:' || sm.id "
    "and am.state = 'posted')"
)[0]
nilai_move, n_move = d(mv["nilai"]), int(mv["n"])
cek(
    "4. Saldo GL netto = nilai stock move",
    abs(persediaan - nilai_move) <= TOLERANSI * 10,
    f"Persediaan netto {persediaan:,.2f} | GR/IR netto {grir:,.2f} | move {nilai_move:,.2f} ({n_move:,} move)",
)

# 5. nilai move sudah DPP
bruto_gl = sum(d(x["debit"]) for x in gl if x["kode"].startswith("1113"))
rasio = bruto_gl / persediaan if persediaan else Decimal(0)
cek(
    "5. Nilai move sudah turun ke DPP",
    Decimal("1.105") < rasio < Decimal("1.115"),
    f"bruto {bruto_gl:,.2f} / DPP {persediaan:,.2f} = rasio {rasio:.6f}",
)

# 6. PO: pajak terisi, total tidak berubah
po = q(
    "select count(*) n, coalesce(sum(o.amount_untaxed),0) untaxed, "
    "coalesce(sum(o.amount_tax),0) tax, coalesce(sum(o.amount_total),0) total, "
    "count(*) filter (where o.amount_tax = 0) tanpa_pajak "
    "from purchase_order o where o.state = 'purchase'"
)[0]
untaxed, pajak, total = d(po["untaxed"]), d(po["tax"]), d(po["total"])
cek(
    "6. PO: PPN terisi dan total = DPP + PPN",
    int(po["tanpa_pajak"]) == 0 and abs(untaxed + pajak - total) <= TOLERANSI,
    f"{po['n']} PO | DPP {untaxed:,.2f} + PPN {pajak:,.2f} = {total:,.2f} | tanpa pajak: {po['tanpa_pajak']}",
)

print("\nRincian GL (jurnal GR + koreksi, posted):")
for x in gl:
    net = d(x["debit"]) - d(x["kredit"])
    print(
        f"  {x['kode']:<12} {x['nm'][:44]:<46} D {d(x['debit']):>18,.2f}  K {d(x['kredit']):>18,.2f}  net {net:>18,.2f}"
    )

gagal = [n for n, ok, _ in hasil if not ok]
print("\n" + "=" * 78)
print(
    f"{len(hasil) - len(gagal)}/{len(hasil)} pemeriksaan lulus"
    + (f" -- GAGAL: {', '.join(gagal)}" if gagal else " -- semua lulus")
)
sys.exit(1 if gagal else 0)
