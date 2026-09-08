import { RankBars } from "@/components/charts";
import { parseFilters } from "@/lib/filters";
import { count, dayLabel, decimal, percent, rupiah, rupiahShort } from "@/lib/format";
import { associateLeaderboard, dataExtent } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function AssociatesPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, extent] = await Promise.all([searchParams, dataExtent()]);
  const filters = parseFilters(params, extent);
  const rows = await associateLeaderboard(filters);

  const total = rows.reduce((sum, r) => sum + r.gross, 0);
  const top = rows.slice(0, 15);
  const median = rows.length ? rows[Math.floor(rows.length / 2)].atv : 0;

  return (
    <>
      <div className="page-head">
        <h1>Papan Peringkat Associate</h1>
        <p>
          {dayLabel(filters.from)} – {dayLabel(filters.to)}. {count(rows.length)} associate.
          Klik sebuah baris untuk memfilter dasbor ke orang itu.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <div className="card kpi">
          <span className="label">Associate aktif</span>
          <span className="value">{count(rows.length)}</span>
          <span className="foot">punya transaksi pada rentang ini</span>
        </div>
        <div className="card kpi">
          <span className="label">ATV median</span>
          <span className="value">{rupiahShort(median)}</span>
          <span className="foot">median, bukan rata-rata</span>
        </div>
        <div className="card kpi">
          <span className="label">Kontribusi 10 teratas</span>
          <span className="value">
            {percent(total ? rows.slice(0, 10).reduce((s, r) => s + r.gross, 0) / total : 0)}
          </span>
          <span className="foot">dari total penjualan</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>15 Teratas berdasarkan Penjualan</h2>
        <p className="sub">Nama sesuai kolom staf dari feed retail-import.</p>
        <RankBars
          data={top.map((r) => ({
            name: r.name,
            value: r.gross,
            id: r.name,
            selected: filters.associate === r.name,
          }))}
          paramKey="associate"
        />
      </div>

      <div className="card">
        <h2>Semua Associate</h2>
        <p className="sub">
          ATV dan UPT lebih menjelaskan cara seseorang menjual daripada total penjualannya, yang
          sebagian besar mengikuti ramainya toko.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th className="rank">#</th>
                <th>Associate</th>
                <th>Toko</th>
                <th>Penjualan</th>
                <th>Transaksi</th>
                <th>ATV</th>
                <th>UPT</th>
                <th>Berdiskon</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.name}>
                  <td className="rank">{i + 1}</td>
                  <td>{r.name}</td>
                  <td>{r.store.replace(/^OLS SES - /, "")}</td>
                  <td className="num">{rupiah(r.gross)}</td>
                  <td className="num">{count(r.transactions)}</td>
                  <td className="num">{rupiahShort(r.atv)}</td>
                  <td className="num">{decimal(r.upt)}</td>
                  <td className="num">{percent(r.discountShare)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="note" style={{ marginTop: 14 }}>
          Kolom <strong>Toko</strong> menampilkan gerai pertama tempat associate ini tercatat.
          Seorang associate yang berpindah gerai akan muncul di bawah satu nama toko saja.
        </div>
      </div>
    </>
  );
}
