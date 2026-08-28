import { RankBars, SparkGrid } from "@/components/charts";
import { parseFilters } from "@/lib/filters";
import { count, dayLabel, decimal, percent, rupiah, rupiahShort } from "@/lib/format";
import {
  dataExtent,
  silentStores,
  storeDailyTrend,
  storeRanking,
  topCategories,
  topProducts,
} from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function StoresPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, extent] = await Promise.all([searchParams, dataExtent()]);
  const filters = parseFilters(params, extent);

  const drilldown = filters.stores.length > 0;

  // The product joins are only paid for once a store is picked: on the
  // unfiltered view they add ~60ms for two panels nobody has asked for yet.
  const [rows, silent, daily, topCats, topProds] = await Promise.all([
    storeRanking(filters),
    silentStores(filters),
    storeDailyTrend(filters, 8),
    drilldown ? topCategories(filters, 10) : Promise.resolve([]),
    drilldown ? topProducts(filters, 10) : Promise.resolve([]),
  ]);

  const total = rows.reduce((sum, r) => sum + r.gross, 0);
  const selected = new Set(filters.stores.map(String));

  const bars = rows.map((r) => ({
    name: r.name.replace(/^OLS SES - /, ""),
    value: r.gross,
    id: String(r.id),
    selected: selected.has(String(r.id)),
  }));

  const groups = Object.values(
    daily.reduce<Record<string, { name: string; total: number; points: { day: string; gross: number }[] }>>(
      (acc, row) => {
        const key = row.store;
        acc[key] ??= { name: key.replace(/^OLS SES - /, ""), total: 0, points: [] };
        acc[key].total += row.gross;
        acc[key].points.push({ day: row.day, gross: row.gross });
        return acc;
      },
      {},
    ),
  ).sort((a, b) => b.total - a.total);

  // Scoped to the selection, so the drill-down shares of the panels below add
  // to 100% of the store — not of the whole chain.
  const drillRows = rows.filter((r) => selected.has(String(r.id)));
  const drillGross = drillRows.reduce((sum, r) => sum + r.gross, 0);
  const drillTxn = drillRows.reduce((sum, r) => sum + r.transactions, 0);
  const selectedNames = drillRows.map((r) => r.name).join(", ");

  let cumulative = 0;

  return (
    <>
      <div className="page-head">
        <h1>Kinerja Toko</h1>
        <p>
          {dayLabel(filters.from)} – {dayLabel(filters.to)}. Klik sebuah batang untuk memfilter
          seluruh dasbor ke toko itu; klik lagi untuk melepasnya.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Peringkat Toko</h2>
        <p className="sub">{count(rows.length)} toko dengan penjualan pada rentang ini.</p>
        <RankBars data={bars} paramKey="stores" />
      </div>

      {drilldown && (
        <div className="card" style={{ marginBottom: 14 }}>
          <h2>Detail {selectedNames || "Toko Terpilih"}</h2>
          <p className="sub">
            Sepuluh kategori dan sepuluh produk terlaris pada toko dan rentang yang sedang
            dipilih. Penjualan {rupiah(drillGross)} dari {count(drillTxn)} transaksi.
          </p>

          <div className="grid cols-2">
            <div>
              <h3 className="panel-title">10 Kategori Teratas</h3>
              {topCats.length === 0 ? (
                <p className="sub">Tidak ada penjualan pada pilihan ini.</p>
              ) : (
                <>
                  <RankBars
                    data={topCats.map((c) => ({ name: c.name, value: c.gross }))}
                    height={Math.max(180, topCats.length * 26 + 24)}
                  />
                  <div className="table-wrap" style={{ marginTop: 10 }}>
                    <table className="data">
                      <thead>
                        <tr>
                          <th className="rank">#</th>
                          <th>Kategori</th>
                          <th>Penjualan</th>
                          <th>Kontribusi</th>
                          <th>Unit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topCats.map((c, i) => (
                          <tr key={c.name}>
                            <td className="rank">{i + 1}</td>
                            <td>{c.name}</td>
                            <td className="num">{rupiahShort(c.gross)}</td>
                            <td className="num">{percent(drillGross ? c.gross / drillGross : 0)}</td>
                            <td className="num">{count(c.units)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>

            <div>
              <h3 className="panel-title">10 Produk Teratas</h3>
              {topProds.length === 0 ? (
                <p className="sub">Tidak ada penjualan pada pilihan ini.</p>
              ) : (
                <>
                  <RankBars
                    data={topProds.map((p) => ({
                      name: p.name.length > 34 ? `${p.name.slice(0, 33)}…` : p.name,
                      value: p.gross,
                    }))}
                    height={Math.max(180, topProds.length * 26 + 24)}
                  />
                  <div className="table-wrap" style={{ marginTop: 10 }}>
                    <table className="data">
                      <thead>
                        <tr>
                          <th className="rank">#</th>
                          <th>Kode</th>
                          <th>Produk</th>
                          <th>Penjualan</th>
                          <th>Unit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topProds.map((p, i) => (
                          <tr key={`${p.code}-${i}`}>
                            <td className="rank">{i + 1}</td>
                            <td>{p.code}</td>
                            <td>{p.name}</td>
                            <td className="num">{rupiahShort(p.gross)}</td>
                            <td className="num">{count(p.units)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Tren 8 Toko Teratas</h2>
        <p className="sub">
          Semua panel memakai sumbu-y yang sama, sehingga tinggi antar toko benar-benar
          sebanding.
        </p>
        <SparkGrid groups={groups} />
      </div>

      <div className="card">
        <h2>Rincian</h2>
        <p className="sub">
          Kolom kontribusi kumulatif menggantikan garis Pareto — dua satuan tidak berbagi sumbu.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th className="rank">#</th>
                <th>Toko</th>
                <th>Penjualan</th>
                <th>Kontribusi</th>
                <th>Kumulatif</th>
                <th>Transaksi</th>
                <th>ATV</th>
                <th>UPT</th>
                <th>Member</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const share = total ? r.gross / total : 0;
                cumulative += share;
                return (
                  <tr key={r.id}>
                    <td className="rank">{i + 1}</td>
                    <td>{r.name}</td>
                    <td className="num">{rupiah(r.gross)}</td>
                    <td className="num">{percent(share)}</td>
                    <td className="num">{percent(cumulative)}</td>
                    <td className="num">{count(r.transactions)}</td>
                    <td className="num">{rupiahShort(r.atv)}</td>
                    <td className="num">{decimal(r.upt)}</td>
                    <td className="num">{percent(r.memberShare)}</td>
                  </tr>
                );
              })}
              <tr style={{ fontWeight: 650 }}>
                <td />
                <td>Total</td>
                <td className="num">{rupiah(total)}</td>
                <td className="num">100,0%</td>
                <td colSpan={5} />
              </tr>
            </tbody>
          </table>
        </div>

        {silent.length > 0 && (
          <div className="note" style={{ marginTop: 14 }}>
            <strong>Tanpa penjualan pada rentang ini:</strong>{" "}
            {silent.map((s) => s.name).join(", ")}. Toko seperti ini hilang dari agregasi biasa,
            jadi ditampilkan terpisah.
          </div>
        )}
      </div>
    </>
  );
}
