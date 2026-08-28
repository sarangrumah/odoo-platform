import { count, dayLabel, monthLabel, rupiah } from "@/lib/format";
import { coverage, reconciliation } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

/**
 * The page that decides whether anyone believes the other four.
 *
 * Deliberately not affected by the filter bar: it describes the dataset, not
 * the current selection.
 */
export default async function TrustPage() {
  const [recon, cov] = await Promise.all([reconciliation(), coverage()]);
  const allBalanced = recon.every((r) => Math.round(r.diff) === 0);

  return (
    <>
      <div className="page-head">
        <h1>Kualitas Data</h1>
        <p>
          Apa yang bisa dan tidak bisa dijawab dasbor ini, beserta buktinya. Halaman ini tidak
          terpengaruh filter di atas.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Rekonsiliasi POS terhadap Buku Besar</h2>
        <p className="sub">
          Penjualan POS di luar PPN dibandingkan dengan akun pendapatan yang sudah diposting, per
          bulan.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Bulan</th>
                <th>POS (di luar PPN)</th>
                <th>Pendapatan GL</th>
                <th>Selisih</th>
              </tr>
            </thead>
            <tbody>
              {recon.map((r) => (
                <tr key={r.month}>
                  <td>{monthLabel(r.month)}</td>
                  <td className="num">{rupiah(r.posExTax)}</td>
                  <td className="num">{rupiah(r.glIncome)}</td>
                  <td
                    className="num"
                    style={{ color: Math.round(r.diff) === 0 ? "var(--good)" : "var(--critical)" }}
                  >
                    {rupiah(r.diff)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={`note ${allBalanced ? "ok" : ""}`} style={{ marginTop: 14 }}>
          {allBalanced ? (
            <>
              <strong>Nol selisih di setiap bulan.</strong> Angka penjualan di dasbor ini adalah
              angka yang sama dengan yang dibukukan di jurnal.
            </>
          ) : (
            <>
              <strong>Ada bulan yang tidak cocok.</strong> Telusuri sebelum memakai angka di
              halaman lain.
            </>
          )}
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Cakupan</h2>
          <p className="sub">Apa yang ada di dalam dataset.</p>
          <table className="data">
            <tbody>
              <tr>
                <td>Transaksi pertama</td>
                <td className="num">{dayLabel(cov.firstOrder)}</td>
              </tr>
              <tr>
                <td>Transaksi terakhir</td>
                <td className="num">{dayLabel(cov.lastOrder)}</td>
              </tr>
              <tr>
                <td>Order</td>
                <td className="num">{count(cov.orders)}</td>
              </tr>
              <tr>
                <td>Baris</td>
                <td className="num">{count(cov.lines)}</td>
              </tr>
              <tr>
                <td>Baris retur (qty negatif)</td>
                <td className="num">{count(cov.returnLines)}</td>
              </tr>
              <tr>
                <td>Baris tanpa nama associate</td>
                <td className="num">{count(cov.linesWithoutStaff)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>Yang Tidak Bisa Dijawab</h2>
          <p className="sub">Batas nyata, bukan fitur yang belum dibuat.</p>

          <div className="note unavailable" style={{ marginBottom: 10 }}>
            <strong>Margin kotor.</strong> {count(cov.linesWithCost)} dari {count(cov.lines)} baris
            punya harga pokok, dan belum ada COGS run yang diposting, sehingga laba kotor tidak
            dapat dihitung — baik per SKU, per toko, maupun secara total.
          </div>

          <div className="note unavailable" style={{ marginBottom: 10 }}>
            <strong>Rincian alat pembayaran.</strong> Seluruh pembayaran tercatat pada{" "}
            {count(cov.distinctPaymentMethods)} metode bernama SUSPENSE — konsekuensi desain
            retail-import. Pemisahan tunai/kartu ada di rekonsiliasi bank, bukan di sini.
          </div>

          <div className="note unavailable">
            <strong>Nominal diskon.</strong> <code>price_unit × qty</code> persis sama dengan
            penjualan bruto, artinya harga yang diimpor sudah bersih diskon. Yang tersedia hanya
            penanda jenis diskon, sehingga dasbor melaporkan <em>porsi transaksi berdiskon</em>,
            bukan nilai rupiah diskon.
          </div>
        </div>
      </div>
    </>
  );
}
