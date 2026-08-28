import Link from "next/link";

import { OrderedBars, RankBars } from "@/components/charts";
import { Kpi } from "@/components/kpi";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import { defaultCompanyIds } from "@/lib/queries/common";
import {
  grirAccounts,
  openItemsByAge,
  reconcileAccountView,
  summaryByAccount,
} from "@/lib/queries/openitems";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function OpenItemsPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [summary, view, grir, ageBands] = await Promise.all([
    summaryByAccount(scope),
    reconcileAccountView(),
    grirAccounts(),
    openItemsByAge(scope),
  ]);

  const viewById = new Map(view.map((v) => [v.accountId, v]));
  const grirSet = new Set(grir);

  const total = summary.reduce((s, r) => s + r.outstanding, 0);
  const totalLines = summary.reduce((s, r) => s + r.lineCount, 0);
  const grirTotal = summary.filter((s) => grirSet.has(s.accountId)).reduce((s, r) => s + r.outstanding, 0);
  const grirLines = summary.filter((s) => grirSet.has(s.accountId)).reduce((s, r) => s + r.lineCount, 0);
  const stale = summary.filter((s) => s.oldestAgeDays > 90);

  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();
  const drill = (accountId: number) =>
    qs ? `/openitems/${accountId}?${qs}` : `/openitems/${accountId}`;

  // Magnitude, so a receivable and a payable of the same size rank together:
  // the question this chart answers is "where is the most unfinished business",
  // and the direction is in the table column beside it.
  const byAccount = summary
    .map((row) => ({
      // Code plus a trimmed name: the full account names run past 40 characters,
      // wrap to three lines and collide with the row below.
      name: row.name.length > 24 ? `${row.code} ${row.name.slice(0, 23)}…` : `${row.code} ${row.name}`,
      value: Math.abs(row.outstanding),
      signed: row.outstanding,
      href: drill(row.accountId),
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 15);

  // Signed, not absolute. Across all reconcile accounts the bands genuinely
  // point in opposite directions — 0–30 days nets to a credit, 31–90 to a debit
  // — and drawing magnitudes would make those look like the same thing.
  const ageChart = ageBands.map((b) => ({ name: b.label, value: b.outstanding }));

  return (
    <>
      <div className="page-head">
        <h1>Open Items &amp; GR/IR</h1>
        <p>
          Semua yang belum tuntas di akun rekonsiliasi per {dayLabel(filters.asOf)}. Residual
          dibangun ulang dari rekonsiliasi yang benar-benar sudah terjadi pada tanggal itu, bukan
          dari residual hari ini — itulah versi yang cocok dengan buku besar di akhir periode.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Total outstanding" value={rupiahShort(total)} hint={`${count(totalLines)} baris`} />
        <Kpi
          label="GR/IR"
          value={rupiahShort(grirTotal)}
          hint={`${count(grirLines)} baris pada ${count(grir.length)} akun`}
        />
        <Kpi label="Akun dengan open item" value={count(summary.length)} />
        <Kpi
          label="Akun beritem > 90 hari"
          value={count(stale.length)}
          hint="Diukur dari item terbuka tertua"
        />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Umur item terbuka</h2>
        <p className="sub">
          Dihitung dari tanggal baris ke tanggal potong, bukan dari jatuh tempo: akun kliring
          tidak punya jatuh tempo, dan pertanyaan yang sebenarnya diajukan ke akun seperti itu
          adalah &ldquo;sudah berapa lama ini menggantung&rdquo;. Batang digambar bertanda:
          yang di bawah garis nol bersaldo kredit, yang di atas bersaldo debit.
        </p>
        <OrderedBars data={ageChart} />
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Umur</th>
                <th>Baris</th>
                <th>Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {ageBands.map((b) => (
                <tr key={b.code}>
                  <td>{b.label}</td>
                  <td className="num">{count(b.lineCount)}</td>
                  <td className="num">{b.outstanding ? rupiah(b.outstanding) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Akun dengan outstanding terbesar</h2>
        <p className="sub">
          Diperingkat menurut besarnya, tanpa memandang arah — piutang dan hutang sebesar itu
          sama-sama pekerjaan yang belum selesai. Arahnya ada di kolom tabel berikutnya. Klik
          batang untuk membuka akunnya.
        </p>
        <RankBars data={byAccount} labelWidth={250} />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Outstanding per akun</h2>
        <p className="sub">
          Total per akun dihitung <strong>tanpa netting</strong>. Itu disengaja: netting FIFO hanya
          memindahkan rupiah antar baris dan tidak pernah mengubah jumlah bertandanya, jadi angka
          ini tidak bisa dirusak oleh kesalahan di netting — dan itulah yang diuji cek 8 di halaman
          Pembuktian Angka. Jumlah baris di sini juga jumlah sebelum netting: itu ukuran berapa
          banyak entri yang masih berdiri di buku besar. Klik akun untuk melihat hasil setelah
          netting.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Akun</th>
                <th>Tipe</th>
                <th>Baris</th>
                <th>Tanpa lawan transaksi</th>
                <th>Lawan transaksi</th>
                <th>Terlama</th>
                <th>Umur (hari)</th>
                <th>Outstanding</th>
                <th>Residual hari ini (view)</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((row) => {
                const v = viewById.get(row.accountId);
                return (
                  <tr key={row.accountId}>
                    <td>
                      <Link href={drill(row.accountId)}>
                        {row.code} {row.name}
                      </Link>
                      {grirSet.has(row.accountId) && (
                        <span className="chip" style={{ marginLeft: 6 }}>
                          GR/IR
                        </span>
                      )}
                    </td>
                    <td>{row.accountType}</td>
                    <td className="num">{count(row.lineCount)}</td>
                    <td className="num">{count(row.anonymousLines)}</td>
                    <td className="num">{count(row.partnerCount)}</td>
                    <td>{row.oldestDate ? dayLabel(row.oldestDate) : "—"}</td>
                    <td className="num">{count(row.oldestAgeDays)}</td>
                    <td className="num">{rupiah(row.outstanding)}</td>
                    <td className="num">{v ? rupiah(v.residual) : "—"}</td>
                  </tr>
                );
              })}
              <tr className="total-row">
                <td>Total</td>
                <td />
                <td className="num">{count(totalLines)}</td>
                <td />
                <td />
                <td />
                <td />
                <td className="num">{rupiah(total)}</td>
                <td className="num">{rupiah(view.reduce((s, v) => s + v.residual, 0))}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="note" style={{ marginTop: 12 }}>
          Kolom terakhir adalah view <code>custom_reconcile_account</code> milik modul
          custom_account_reconcile. View itu selalu membaca residual <em>hari ini</em>, jadi ia hanya
          wajib sama dengan kolom Outstanding ketika tanggal potong adalah hari ini. Cek 6 di
          halaman Pembuktian Angka menyatakan hal itu secara eksplisit.
        </div>
      </div>

      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
        Dibuktikan di <Link href={qs ? `/tie?${qs}` : "/tie"}>Pembuktian Angka</Link>, cek 6 sampai 9.
      </p>
    </>
  );
}
