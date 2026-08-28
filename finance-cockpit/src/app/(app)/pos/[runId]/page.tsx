import Link from "next/link";

import { Kpi } from "@/components/kpi";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import { defaultCompanyIds } from "@/lib/queries/common";
import { clearingRuns, diagnostics, legBalances, shortBy, x24Matching } from "@/lib/queries/pos";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type Params = Promise<{ runId: string }>;

const DIAG_LABEL: Record<string, string> = {
  missing_day: "Hari tanpa data",
  no_statement: "Tidak ada rekening koran",
  no_analytic: "Tanpa Operating Unit",
  unmapped_mid: "MID belum dipetakan",
  unmapped_cash: "Setoran tunai belum dipetakan",
  unparsed: "Narasi tidak terurai",
  amount_mismatch: "Nilai tidak cocok",
  short: "Kurang dari piutang",
  unsettled: "Belum diselesaikan",
  consumed: "Sudah dipakai di tempat lain",
  sweep_double: "Sweep ganda",
  no_cash_account: "Tidak ada akun kas",
  overlap: "Periode bertumpang tindih",
};

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const [{ runId }, sp, defaults] = await Promise.all([params, searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(sp, defaults);
  const id = Number(runId);
  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();

  const [runs, diag, byStore, byJournal, byDay, x24, legs] = await Promise.all([
    clearingRuns(filters.companies),
    diagnostics(id),
    shortBy(id, "store"),
    shortBy(id, "journal"),
    shortBy(id, "day"),
    x24Matching(id),
    legBalances(filters.companies),
  ]);

  const run = runs.find((r) => r.id === id);
  if (!run) {
    return (
      <div className="page-head">
        <h1>Run tidak ditemukan</h1>
        <p>
          Tidak ada run clearing dengan id {id}.{" "}
          <Link href={qs ? `/pos?${qs}` : "/pos"}>Kembali ke daftar run</Link>
        </p>
      </div>
    );
  }

  const runLegs = legs.filter((l) => l.runId === id);
  const legBalance = runLegs.reduce((s, l) => s + l.balance, 0);
  const legCount = runLegs.reduce((s, l) => s + l.legCount, 0);
  const legPosted = runLegs.reduce((s, l) => s + l.postedLines, 0);

  const dimensions: { title: string; note: string; rows: typeof byStore }[] = [
    {
      title: "Per Operating Unit",
      note: "Toko mana yang settlement-nya tidak menutup piutangnya.",
      rows: byStore,
    },
    { title: "Per jurnal bank", note: "Rekening bank mana yang bermasalah.", rows: byJournal },
    { title: "Per tanggal settlement", note: "Kapan kekurangan itu terjadi.", rows: byDay },
  ];

  return (
    <>
      <div className="page-head">
        <h1>{run.name}</h1>
        <p>
          {run.periodRef} · {dayLabel(run.dateFrom)} – {dayLabel(run.dateTo)} · status{" "}
          <strong>{run.state}</strong>.{" "}
          <Link href={qs ? `/pos?${qs}` : "/pos"}>Kembali ke daftar run</Link>
        </p>
      </div>

      {run.warningText && (
        <div className="note" style={{ borderLeftColor: "var(--critical)", marginBottom: 14 }}>
          {run.warningText}
        </div>
      )}

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Bruto" value={rupiahShort(run.gross)} hint={`${count(run.lineCount)} baris`} />
        <Kpi label="MDR" value={rupiahShort(run.mdr)} />
        <Kpi
          label="Teralokasi"
          value={rupiahShort(run.allocated)}
          hint={`${count(run.okCount)} baris tuntas`}
        />
        <Kpi
          label="Kurang"
          value={rupiahShort(run.short)}
          hint={`${count(run.shortCount)} baris`}
          higherIsBetter={false}
        />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Saldo sebelum dan sesudah</h2>
        <p className="sub">
          Kolom-kolom ini benar-benar tersimpan pada run — berbeda dari total di atas, yang harus
          dihitung ulang dari barisnya.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Akun</th>
                <th>Sebelum</th>
                <th>Sesudah (aktual)</th>
                <th>Perubahan</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Bank Suspense</td>
                <td className="num">{rupiah(run.suspenseBefore)}</td>
                <td className="num">{rupiah(run.suspenseAfterActual)}</td>
                <td className="num">{rupiah(run.suspenseAfterActual - run.suspenseBefore)}</td>
              </tr>
              <tr>
                <td>Beban MDR</td>
                <td className="num">{rupiah(run.mdrBefore)}</td>
                <td className="num">{rupiah(run.mdrAfterActual)}</td>
                <td className="num">{rupiah(run.mdrAfterActual - run.mdrBefore)}</td>
              </tr>
              <tr>
                <td>Piutang POS terbuka</td>
                <td className="num">{rupiah(run.posrecOpenBefore)}</td>
                <td className="num">{rupiah(run.posrecOpenAfterActual)}</td>
                <td className="num">{rupiah(run.posrecOpenAfterActual - run.posrecOpenBefore)}</td>
              </tr>
              <tr>
                <td>Baris piutang POS terbuka</td>
                <td className="num">{count(run.posrecLinesBefore)}</td>
                <td className="num">{count(run.posrecLinesAfterActual)}</td>
                <td className="num">
                  {count(run.posrecLinesAfterActual - run.posrecLinesBefore)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Diagnostik</h2>
        <p className="sub">
          Temuan yang dicatat run saat menghitung. Yang <span className="sev" data-level="blocking">blocking</span>{" "}
          menghentikan posting; sisanya perlu dibaca sebelum diposting.
        </p>
        {diag.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Temuan</th>
                  <th>Tingkat</th>
                  <th>Kejadian</th>
                  <th>Jumlah</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {diag.map((d) => (
                  <tr key={`${d.kind}-${d.severity}`}>
                    <td>{DIAG_LABEL[d.kind] ?? d.kind}</td>
                    <td>
                      <span className="sev" data-level={d.severity}>
                        {d.severity}
                      </span>
                    </td>
                    <td className="num">{count(d.occurrences)}</td>
                    <td className="num">{count(d.count)}</td>
                    <td className="num">{d.amount ? rupiah(d.amount) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada diagnostik untuk run ini.</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Jurnal yang direncanakan</h2>
        <p className="sub">
          Leg adalah jurnal berpasangan lengkap, jadi jumlahnya wajib nol. Leg tanpa baris jurnal
          berarti rencana yang belum dibukukan — normal selama run belum diposting.
        </p>
        {runLegs.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Peran</th>
                  <th>Leg</th>
                  <th>Terbukukan</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {runLegs.map((l) => (
                  <tr key={l.role}>
                    <td>{l.role}</td>
                    <td className="num">{count(l.legCount)}</td>
                    <td className="num">{count(l.postedLines)}</td>
                    <td className="num">{rupiah(l.balance)}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td>Total</td>
                  <td className="num">{count(legCount)}</td>
                  <td className="num">{count(legPosted)}</td>
                  <td className={`num ${Math.abs(legBalance) < 0.005 ? "tie-ok" : "tie-bad"}`}>
                    {rupiah(legBalance)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">
            Run ini belum mencapai tahap generate, jadi belum ada leg yang direncanakan.
          </p>
        )}
      </div>

      {dimensions.map((dim) => (
        <div className="card" style={{ marginBottom: 14 }} key={dim.title}>
          <h2>{dim.title}</h2>
          <p className="sub">{dim.note}</p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>{dim.title.replace("Per ", "")}</th>
                  <th>Baris</th>
                  <th>Bruto</th>
                  <th>Kurang</th>
                  <th>Tidak cocok</th>
                </tr>
              </thead>
              <tbody>
                {dim.rows.slice(0, 40).map((r) => (
                  <tr key={r.key}>
                    <td>{r.label}</td>
                    <td className="num">{count(r.lineCount)}</td>
                    <td className="num">{rupiah(r.gross)}</td>
                    <td className="num">{r.short ? rupiah(r.short) : "—"}</td>
                    <td className="num">{r.mismatch ? rupiah(r.mismatch) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="card">
        <h2>Kecocokan dengan struk X24</h2>
        <p className="sub">
          Satu MID kartu melayani Visa, Mastercard, JCB dan Amex sekaligus, jadi tender mana yang
          dikreditkan tidak bisa dibaca dari MID — harus ditemukan dari struk. Kolom ini menunjukkan
          seberapa sering itu berhasil.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Kecocokan</th>
                <th>Baris</th>
                <th>Bruto</th>
                <th>Nilai struk</th>
                <th>Selisih</th>
                <th>Tender berbeda</th>
              </tr>
            </thead>
            <tbody>
              {x24.map((m) => (
                <tr key={m.match}>
                  <td>{m.match}</td>
                  <td className="num">{count(m.lineCount)}</td>
                  <td className="num">{rupiah(m.gross)}</td>
                  <td className="num">{rupiah(m.matchedTotal)}</td>
                  <td className="num">{rupiah(m.gap)}</td>
                  <td className="num">{count(m.tenderMismatch)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
