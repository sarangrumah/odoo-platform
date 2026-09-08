import { RankBars } from "@/components/charts";
import { parseFilters } from "@/lib/filters";
import { count, dayLabel, percent, rupiah, rupiahShort } from "@/lib/format";
import { categoryMix, dataExtent, topProducts } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function ProductsPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, extent] = await Promise.all([searchParams, dataExtent()]);
  const filters = parseFilters(params, extent);

  const [mix, products] = await Promise.all([categoryMix(filters), topProducts(filters, 50)]);

  const total = mix.reduce((sum, n) => sum + n.gross, 0);
  const selected = new Set(filters.categories);

  // Level 2 is the useful cut here: level 1 is "Textile" for essentially
  // everything, so rolling up to it would draw a single bar.
  const byLevel2 = Object.values(
    mix.reduce<Record<string, { name: string; gross: number; units: number }>>((acc, node) => {
      acc[node.level2] ??= { name: node.level2, gross: 0, units: 0 };
      acc[node.level2].gross += node.gross;
      acc[node.level2].units += node.units;
      return acc;
    }, {}),
  ).sort((a, b) => b.gross - a.gross);

  // Level 3 is only shown once the view is narrowed, otherwise it is a wall of
  // forty near-identical bars.
  const byLevel3 = selected.size
    ? Object.values(
        mix
          .filter((n) => selected.has(n.level2))
          .reduce<Record<string, { name: string; gross: number; units: number }>>((acc, node) => {
            const key = `${node.level2} / ${node.level3}`;
            acc[key] ??= { name: key, gross: 0, units: 0 };
            acc[key].gross += node.gross;
            acc[key].units += node.units;
            return acc;
          }, {}),
      ).sort((a, b) => b.gross - a.gross)
    : [];

  return (
    <>
      <div className="page-head">
        <h1>Bauran Produk</h1>
        <p>
          {dayLabel(filters.from)} – {dayLabel(filters.to)}. Klik sebuah kategori untuk menelusuri
          ke sub-kategorinya.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Kategori</h2>
        <p className="sub">Level 2 dari hierarki kategori Odoo.</p>
        <RankBars
          data={byLevel2.map((c) => ({
            name: c.name,
            value: c.gross,
            id: c.name,
            selected: selected.has(c.name),
          }))}
          paramKey="categories"
        />
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Kategori</th>
                <th>Penjualan</th>
                <th>Kontribusi</th>
                <th>Unit</th>
              </tr>
            </thead>
            <tbody>
              {byLevel2.map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td className="num">{rupiah(c.gross)}</td>
                  <td className="num">{percent(total ? c.gross / total : 0)}</td>
                  <td className="num">{count(c.units)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {byLevel3.length > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <h2>Sub-kategori</h2>
          <p className="sub">Dalam {[...selected].join(", ")}.</p>
          <RankBars data={byLevel3.map((c) => ({ name: c.name, value: c.gross }))} />
        </div>
      )}

      <div className="card">
        <h2>50 Produk Teratas</h2>
        <p className="sub">
          Kolom &laquo;Toko&raquo; menghitung berapa gerai menjual produk itu — pembeda antara
          produk laris nasional dan lonjakan di satu toko.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th className="rank">#</th>
                <th>Kode</th>
                <th>Produk</th>
                <th>Penjualan</th>
                <th>Unit</th>
                <th>Toko</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p, i) => (
                <tr key={`${p.code}-${i}`}>
                  <td className="rank">{i + 1}</td>
                  <td>{p.code}</td>
                  <td>{p.name}</td>
                  <td className="num">{rupiahShort(p.gross)}</td>
                  <td className="num">{count(p.units)}</td>
                  <td className="num">{count(p.stores)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
