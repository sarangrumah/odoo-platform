import Link from "next/link";

import { Kpi } from "@/components/kpi";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import { companies as companyList, defaultCompanyIds } from "@/lib/queries/common";
import {
  closeAnomalies,
  draftMoves,
  excludedJournals,
  lockExceptions,
  sequenceGaps,
  trialBalance,
} from "@/lib/queries/close";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/**
 * The six permanent lock exceptions in prd_levis_begbal are deliberate: June
 * 2026 postings were opened on purpose and left open. The page states the
 * expected number rather than hard-coding the ids, so a SEVENTH one — the thing
 * that would actually matter — shows up as a change instead of blending in.
 */
const EXPECTED_PERMANENT_EXCEPTIONS = 6;

export default async function ClosePage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [list, tb, drafts, anomalies, exceptions, excluded, gaps] = await Promise.all([
    companyList(),
    trialBalance({ from: filters.from, to: filters.asOf, companies: filters.companies }),
    draftMoves(scope),
    closeAnomalies(scope),
    lockExceptions(filters.companies),
    excludedJournals(scope),
    sequenceGaps(scope),
  ]);

  const closingDebit = tb.reduce((s, r) => s + r.closingDebit, 0);
  const closingCredit = tb.reduce((s, r) => s + r.closingCredit, 0);
  const balanced = Math.abs(closingDebit - closingCredit) < 0.005;

  const draftCount = drafts.reduce((s, d) => s + d.moveCount, 0);
  const draftAmount = drafts.reduce((s, d) => s + d.amount, 0);
  const problems = anomalies.filter((a) => a.isProblem && a.count > 0);
  const permanent = exceptions.filter((e) => e.permanent);
  const active = exceptions.filter((e) => e.active);
  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();

  return (
    <>
      <div className="page-head">
        <h1>Kesiapan Tutup Buku</h1>
        <p>
          Apa yang masih menghalangi penutupan per {dayLabel(filters.asOf)}. Neraca saldo memakai
          jendela mutasi {dayLabel(filters.from)} – {dayLabel(filters.asOf)}.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Neraca saldo" value={balanced ? "Seimbang" : "Tidak seimbang"} />
        <Kpi
          label="Jurnal draft"
          value={count(draftCount)}
          hint={rupiahShort(draftAmount)}
          higherIsBetter={false}
        />
        <Kpi
          label="Temuan kualitas data"
          value={count(problems.length)}
          hint={`dari ${count(anomalies.length)} pemeriksaan`}
          higherIsBetter={false}
        />
        <Kpi
          label="Lock exception aktif"
          value={count(active.length)}
          hint={`${count(permanent.length)} permanen`}
        />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Tanggal kunci</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Perusahaan</th>
                <th>Tahun buku</th>
                <th>Pajak</th>
                <th>Penjualan</th>
                <th>Pembelian</th>
                <th>Kunci keras</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.fiscalyearLockDate ? dayLabel(c.fiscalyearLockDate) : "—"}</td>
                  <td>{c.taxLockDate ? dayLabel(c.taxLockDate) : "—"}</td>
                  <td>{c.saleLockDate ? dayLabel(c.saleLockDate) : "—"}</td>
                  <td>{c.purchaseLockDate ? dayLabel(c.purchaseLockDate) : "—"}</td>
                  <td>{c.hardLockDate ? dayLabel(c.hardLockDate) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2 style={{ marginTop: 18 }}>Lock exception</h2>
        <p className="sub">
          Exception mengalahkan tanggal kunci: selama satu exception aktif, periode yang terlihat
          terkunci sebenarnya masih bisa ditulis. {EXPECTED_PERMANENT_EXCEPTIONS} exception permanen
          di database ini memang disengaja dan bukan temuan.
        </p>
        {permanent.length !== EXPECTED_PERMANENT_EXCEPTIONS && (
          <div className="note" style={{ borderLeftColor: "var(--critical)", marginBottom: 12 }}>
            Ada {count(permanent.length)} exception permanen, sementara yang diketahui disengaja ada{" "}
            {EXPECTED_PERMANENT_EXCEPTIONS}. Periksa selisihnya sebelum menutup buku.
          </div>
        )}
        {active.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Field</th>
                  <th>Kunci lama</th>
                  <th>Kunci perusahaan</th>
                  <th>Berakhir</th>
                  <th>Alasan</th>
                </tr>
              </thead>
              <tbody>
                {active.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.lockDateField}</td>
                    <td>{e.lockDate ? dayLabel(e.lockDate) : "—"}</td>
                    <td>{e.companyLockDate ? dayLabel(e.companyLockDate) : "—"}</td>
                    <td>{e.endDatetime ? e.endDatetime.slice(0, 16) : "permanen"}</td>
                    <td style={{ textAlign: "left", whiteSpace: "normal" }}>{e.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada exception aktif.</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Pemeriksaan kualitas data</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Pemeriksaan</th>
                <th>Jumlah</th>
                <th>Nilai</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((a) => (
                <tr key={a.key}>
                  <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                    <strong>{a.label}</strong>
                    <br />
                    <span className="sub">{a.detail}</span>
                  </td>
                  <td className="num">{count(a.count)}</td>
                  <td className="num">{a.amount ? rupiah(a.amount) : "—"}</td>
                  <td>
                    <span
                      className="tie-status"
                      data-state={a.count === 0 ? "ok" : a.isProblem ? "bad" : "info"}
                    >
                      {a.count === 0 ? "bersih" : a.isProblem ? "perlu tindakan" : "pengamatan"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Jurnal draft per jurnal dan periode</h2>
        {drafts.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Jurnal</th>
                  <th>Periode</th>
                  <th>Entry</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {drafts.map((d) => (
                  <tr key={`${d.journalId}-${d.period}`}>
                    <td>
                      {d.journalCode} {d.journalName}
                    </td>
                    <td>{d.period}</td>
                    <td className="num">{count(d.moveCount)}</td>
                    <td className="num">{rupiah(d.amount)}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={2}>Total</td>
                  <td className="num">{count(draftCount)}</td>
                  <td className="num">{rupiah(draftAmount)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada jurnal draft sampai tanggal potong.</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Lompatan nomor jurnal</h2>
        <p className="sub">
          Nomor yang hilang di antara dua entry terposting. Auditor akan menanyakannya, jadi lebih
          baik ditemukan sekarang. 100 lompatan terbesar.
        </p>
        {gaps.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Jurnal</th>
                  <th>Periode</th>
                  <th>Setelah</th>
                  <th>Sebelum</th>
                  <th>Nomor hilang</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((g, i) => (
                  <tr key={`${g.after}-${i}`}>
                    <td>
                      {g.journalCode} {g.journalName}
                    </td>
                    <td>{g.period}</td>
                    <td>{g.after}</td>
                    <td>{g.before}</td>
                    <td className="num">{count(g.missing)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada lompatan nomor.</p>
        )}
      </div>

      <div className="card">
        <h2>Jurnal yang dikecualikan dari laporan</h2>
        <p className="sub">
          Jurnal bertanda <code>x_custom_report_excluded</code> tidak masuk neraca saldo maupun buku
          besar laporan. Inilah seluruh selisih antara buku besar mentah dan neraca saldo, jadi ia
          diberi nama dan angka, bukan dibiarkan sebagai celah.
        </p>
        {excluded.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Jurnal</th>
                  <th>Baris</th>
                  <th>Saldo</th>
                </tr>
              </thead>
              <tbody>
                {excluded.map((j) => (
                  <tr key={j.journalId}>
                    <td>
                      {j.code} {j.name}
                    </td>
                    <td className="num">{count(j.lineCount)}</td>
                    <td className="num">{rupiah(j.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">
            Tidak ada jurnal yang dikecualikan, jadi buku besar mentah dan neraca saldo memuat
            himpunan baris yang sama.
          </p>
        )}
      </div>

      <p style={{ marginTop: 18, fontSize: 12, color: "var(--text-muted)" }}>
        Keseimbangan neraca saldo diuji di{" "}
        <Link href={qs ? `/tie?${qs}` : "/tie"}>Pembuktian Angka</Link>, cek 1, 2 dan 13.
      </p>
    </>
  );
}
