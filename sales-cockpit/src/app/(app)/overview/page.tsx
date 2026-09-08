import { Kpi } from "@/components/kpi";
import { CountTrend, TrendChart } from "@/components/charts";
import {
  daysInMonth,
  daysInRange,
  monthToDate,
  parseFilters,
  previousPeriod,
  sameSpanPreviousMonth,
  type Filters,
} from "@/lib/filters";
import { count, dayLabel, decimal, monthLabel, percent, rupiah, rupiahShort } from "@/lib/format";
import { dailyTrend, dataExtent, kpis, storeRanking } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function OverviewPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, extent] = await Promise.all([searchParams, dataExtent()]);
  const filters = parseFilters(params, extent);
  const prev = previousPeriod(filters);
  const prevFilters: Filters = { ...filters, from: prev.from, to: prev.to };

  // Month to date sits OUTSIDE the date filter on purpose: it is the one block
  // that always answers "how is this month going", whatever range is selected.
  // Every other filter (toko, kategori, member, associate) still applies.
  const mtd = monthToDate(extent);
  const lastMonth = sameSpanPreviousMonth(mtd);
  const mtdFilters: Filters = { ...filters, from: mtd.from, to: mtd.to };
  const lastMonthFilters: Filters = { ...filters, from: lastMonth.from, to: lastMonth.to };

  const [now, before, trend, prevTrend, stores, mtdNow, mtdBefore, mtdTrend, mtdPrevTrend] =
    await Promise.all([
      kpis(filters),
      kpis(prevFilters),
      dailyTrend(filters),
      dailyTrend(prevFilters),
      storeRanking(filters),
      kpis(mtdFilters),
      kpis(lastMonthFilters),
      dailyTrend(mtdFilters),
      dailyTrend(lastMonthFilters),
    ]);

  // Cumulative rupiah, aligned by day NUMBER: 5 Aug sits over 5 Jul. Days with
  // no rows carry the running total forward rather than dropping out, so a
  // closed day flattens the curve instead of putting the two months out of step.
  const mtdDays = daysInRange(mtd);
  const firstDayNum = Number(mtd.from.slice(8, 10));
  const cumulative = (points: { day: string; gross: number }[], startDay: number) => {
    const byDay = new Map(points.map((p) => [Number(p.day.slice(8, 10)), p.gross]));
    let running = 0;
    return Array.from({ length: mtdDays }, (_, i) => {
      running += byDay.get(startDay + i) ?? 0;
      return running;
    });
  };

  const mtdCum = cumulative(mtdTrend, firstDayNum);
  const lastCum = cumulative(mtdPrevTrend, Number(lastMonth.from.slice(8, 10)));
  const mtdCurve = Array.from({ length: mtdDays }, (_, i) => ({
    day: `${mtd.from.slice(0, 8)}${String(firstDayNum + i).padStart(2, "0")}`,
    gross: mtdCum[i],
    previous: lastCum[i],
  }));

  // Run rate, not a forecast: today's daily average carried to month end. It is
  // labelled as such because the last days of a month are not average days.
  const mtdDaily = mtdDays ? mtdNow.gross / mtdDays : 0;
  const monthLength = daysInMonth(mtd.to);
  const runRate = mtdDaily * monthLength;

  // Align the comparison series by position, not by date: the two windows are
  // the same length but different calendar days, so day 1 sits over day 1.
  const trendData = trend.map((point, i) => ({
    day: point.day,
    gross: point.gross,
    previous: prevTrend[i]?.gross ?? 0,
    transactions: point.transactions,
  }));

  const best = stores[0];
  const busiest = [...trend].sort((a, b) => b.gross - a.gross)[0];

  return (
    <>
      <div className="page-head">
        <h1>Ringkasan Penjualan</h1>
        <p>
          {dayLabel(filters.from)} – {dayLabel(filters.to)}. Pembanding: {dayLabel(prev.from)} –{" "}
          {dayLabel(prev.to)}.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Bulan Berjalan — {monthLabel(mtd.to)}</h2>
        <p className="sub">
          {dayLabel(mtd.from)} – {dayLabel(mtd.to)} ({count(mtdDays)} hari). Pembanding: rentang
          tanggal yang sama bulan lalu, {dayLabel(lastMonth.from)} – {dayLabel(lastMonth.to)}. Blok
          ini mengikuti hari terakhir yang sudah termuat, bukan filter tanggal di atas — filter toko,
          kategori, member, dan kasir tetap berlaku.
        </p>

        <div className="grid kpis" style={{ marginBottom: 14 }}>
          <Kpi
            label="Bruto MTD"
            value={rupiahShort(mtdNow.gross)}
            current={mtdNow.gross}
            previous={mtdBefore.gross}
            hint="vs periode sama bulan lalu"
          />
          <Kpi
            label="Transaksi MTD"
            value={count(mtdNow.transactions)}
            current={mtdNow.transactions}
            previous={mtdBefore.transactions}
            hint="vs periode sama bulan lalu"
          />
          <Kpi
            label="ATV MTD"
            value={rupiahShort(mtdNow.atv)}
            current={mtdNow.atv}
            previous={mtdBefore.atv}
            hint="rata-rata per transaksi"
          />
          <Kpi
            label="Unit MTD"
            value={count(mtdNow.units)}
            current={mtdNow.units}
            previous={mtdBefore.units}
            hint="vs periode sama bulan lalu"
          />
          <Kpi label="Rata-rata Harian MTD" value={rupiahShort(mtdDaily)} hint={`dibagi ${count(mtdDays)} hari`} />
          <Kpi
            label="Laju Bulan Penuh"
            value={rupiahShort(runRate)}
            hint={`rata-rata harian x ${count(monthLength)} hari, bukan proyeksi`}
          />
        </div>

        <TrendChart
          data={mtdCurve}
          height={220}
          series={[
            { key: "gross", label: `Kumulatif ${monthLabel(mtd.to)}`, color: "var(--series-1)" },
            { key: "previous", label: "Kumulatif bulan lalu", color: "var(--series-3)" },
          ]}
        />
        <p className="sub" style={{ marginTop: 8 }}>
          Kumulatif disejajarkan per tanggal: 5 Agustus berdiri di atas 5 Juli.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Penjualan Bruto" value={rupiahShort(now.gross)} current={now.gross} previous={before.gross} />
        <Kpi label="Transaksi" value={count(now.transactions)} current={now.transactions} previous={before.transactions} />
        <Kpi label="ATV" value={rupiahShort(now.atv)} current={now.atv} previous={before.atv} hint="rata-rata per transaksi" />
        <Kpi label="UPT" value={decimal(now.upt)} current={now.upt} previous={before.upt} hint="unit per transaksi" />
        <Kpi label="ASP" value={rupiahShort(now.asp)} current={now.asp} previous={before.asp} hint="harga rata-rata per unit" />
        <Kpi
          label="Transaksi Member"
          value={percent(now.memberShare)}
          current={now.memberShare}
          previous={before.memberShare}
        />
        <Kpi
          label="Transaksi Berdiskon"
          value={percent(now.discountShare)}
          current={now.discountShare}
          previous={before.discountShare}
          hint="porsi transaksi, bukan nilai"
        />
        <Kpi label="Unit Terjual" value={count(now.units)} current={now.units} previous={before.units} />
      </div>

      <div className="grid" style={{ marginBottom: 14 }}>
        <div className="card">
          <h2>Penjualan Harian</h2>
          <p className="sub">
            Garis pembanding disejajarkan per posisi hari, bukan per tanggal — kedua rentang sama
            panjang tetapi jatuh pada tanggal berbeda.
          </p>
          <TrendChart
            data={trendData}
            series={[
              { key: "gross", label: "Periode ini", color: "var(--series-1)" },
              { key: "previous", label: "Periode sebelumnya", color: "var(--series-3)" },
            ]}
          />
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Jumlah Transaksi Harian</h2>
          <p className="sub">
            Dipisah dari grafik rupiah dengan sengaja: dua satuan berbeda tidak pernah berbagi satu
            sumbu.
          </p>
          <CountTrend data={trend} />
        </div>

        <div className="card">
          <h2>Sorotan</h2>
          <p className="sub">Angka yang biasanya ditanyakan pertama.</p>
          <table className="data">
            <tbody>
              <tr>
                <td>Toko terbaik</td>
                <td>{best ? `${best.name} — ${rupiahShort(best.gross)}` : "—"}</td>
              </tr>
              <tr>
                <td>Hari terbaik</td>
                <td>{busiest ? `${dayLabel(busiest.day)} — ${rupiahShort(busiest.gross)}` : "—"}</td>
              </tr>
              <tr>
                <td>Toko dengan penjualan</td>
                <td>{count(stores.length)}</td>
              </tr>
              <tr>
                <td>Rata-rata harian</td>
                <td>{trend.length ? rupiah(now.gross / trend.length) : "—"}</td>
              </tr>
              <tr>
                <td>Total bruto (nilai penuh)</td>
                <td>{rupiah(now.gross)}</td>
              </tr>
            </tbody>
          </table>

          <div className="note unavailable" style={{ marginTop: 14 }}>
            <strong>Margin belum tersedia.</strong> Seluruh 52.581 baris POS punya{" "}
            <code>total_cost</code> = 0 dan belum ada COGS run yang diposting, sehingga laba kotor
            tidak dapat dihitung dari data ini. Lihat halaman Kualitas Data.
          </div>
        </div>
      </div>
    </>
  );
}
