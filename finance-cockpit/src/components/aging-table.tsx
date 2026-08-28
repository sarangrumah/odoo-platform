import { BUCKETS, type AgingRow, type AgingTotals } from "@/lib/queries/ap";
import { count, rupiah } from "@/lib/format";

/**
 * The seven-bucket aging grid.
 *
 * Every bucket column is shown even when empty: a reader scanning for "> 365
 * hari" needs the column to be where they expect it, and a grid that changes
 * shape between pages is harder to trust than one with zeroes in it.
 */
export function AgingTable({
  rows,
  totals,
  href,
  emptyLabel = "Tidak ada saldo terbuka pada tanggal ini.",
}: {
  rows: AgingRow[];
  totals: AgingTotals;
  href?: (row: AgingRow) => string | null;
  emptyLabel?: string;
}) {
  if (!rows.length) return <p className="sub">{emptyLabel}</p>;

  return (
    <div className="aging-grid">
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Lawan transaksi</th>
              <th>Item</th>
              <th>Terlama (hari)</th>
              {BUCKETS.map((b) => (
                <th key={b.code}>{b.label}</th>
              ))}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const link = href?.(row) ?? null;
              return (
                <tr key={row.partnerId}>
                  <td>{link ? <a href={link}>{row.partnerName}</a> : row.partnerName}</td>
                  <td className="num">{count(row.itemCount)}</td>
                  <td className="num">{count(row.maxOverdueDays)}</td>
                  {BUCKETS.map((b) => (
                    <td key={b.code} className="num">
                      {row.buckets[b.code] ? rupiah(row.buckets[b.code]) : "—"}
                    </td>
                  ))}
                  <td className="num">{rupiah(row.total)}</td>
                </tr>
              );
            })}
            <tr className="total-row">
              <td>Total</td>
              <td className="num">{count(totals.itemCount)}</td>
              <td className="num">—</td>
              {BUCKETS.map((b) => (
                <td key={b.code} className="num">
                  {rupiah(totals.buckets[b.code])}
                </td>
              ))}
              <td className="num">{rupiah(totals.total)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
