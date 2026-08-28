import Link from "next/link";

import { Kpi } from "@/components/kpi";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import { defaultCompanyIds } from "@/lib/queries/common";
import { clearingRuns, tenderBalances, unreconciledStatements } from "@/lib/queries/pos";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  computed: "Dihitung",
  generated: "Leg dibuat",
  posted: "Diposting",
  cancel: "Dibatalkan",
};

export default async function PosPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [runs, tenders, statements] = await Promise.all([
    clearingRuns(filters.companies),
    tenderBalances(scope),
    unreconciledStatements(scope),
  ]);

  const tenderTotal = tenders.reduce((s, t) => s + t.balance, 0);
  const tenderLines = tenders.reduce((s, t) => s + t.openLines, 0);
  const stmtLines = statements.reduce((s, r) => s + r.lineCount, 0);
  const latest = runs[0];

  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();

  return (
    <>
      <div className="page-head">
        <h1>Clearing POS &amp; Bank</h1>
        <p>
          Toko menjual lewat kartu, QRIS dan tunai; sesi POS membukukan satu piutang per tender, dan
          beberapa hari kemudian acquirer membayar setelah dipotong MDR. Halaman ini memantau
          seberapa jauh keduanya sudah dipertemukan, per {dayLabel(filters.asOf)}.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi
          label="Piutang POS terbuka"
          value={rupiahShort(tenderTotal)}
          hint={`${count(tenderLines)} baris pada ${count(tenders.length)} akun tender`}
        />
        <Kpi
          label="Baris rekening koran belum cocok"
          value={count(stmtLines)}
          hint="Selama ini belum nol, lock date tidak bisa dipasang"
        />
        <Kpi label="Run clearing tercatat" value={count(runs.length)} />
        <Kpi
          label="Run terakhir"
          value={latest ? STATE_LABEL[latest.state] ?? latest.state : "—"}
          hint={latest ? latest.periodRef : "Belum ada run"}
        />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Run clearing</h2>
        <p className="sub">
          Semua total di tabel ini diagregasi ulang dari baris run. Field ringkasan di model{" "}
          <code>levis.pos.clearing</code> adalah compute tanpa store, jadi tidak ada kolomnya di
          basis data dan tidak bisa dibaca langsung.
        </p>
        {runs.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Periode</th>
                  <th>Status</th>
                  <th>Baris</th>
                  <th>Bruto</th>
                  <th>MDR</th>
                  <th>Teralokasi</th>
                  <th>Kurang (nilai)</th>
                  <th>Baris OK</th>
                  <th>Baris kurang</th>
                  <th>Baris tak terpetakan</th>
                  <th>Baris tak terurai</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link href={qs ? `/pos/${r.id}?${qs}` : `/pos/${r.id}`}>{r.name}</Link>
                    </td>
                    <td>{r.periodRef}</td>
                    <td>{STATE_LABEL[r.state] ?? r.state}</td>
                    <td className="num">{count(r.lineCount)}</td>
                    <td className="num">{rupiah(r.gross)}</td>
                    <td className="num">{rupiah(r.mdr)}</td>
                    <td className="num">{rupiah(r.allocated)}</td>
                    <td className="num">{rupiah(r.short)}</td>
                    <td className="num">{count(r.okCount)}</td>
                    <td className="num">{count(r.shortCount)}</td>
                    <td className="num">{count(r.unmappedCount)}</td>
                    <td className="num">{count(r.unparsedCount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Belum ada run clearing pada database ini.</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Piutang POS per tender</h2>
        <p className="sub">
          Inilah yang seharusnya dikuras oleh clearing. Akun ditemukan lewat prefix kode 11060001
          karena relasi <code>pos_receivable_account_ids</code> pada konfigurasi clearing masih
          kosong; mengandalkan konfigurasi saja akan menampilkan tabel kosong.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Akun</th>
                <th>Baris terbuka</th>
                <th>Terlama</th>
                <th>Saldo</th>
              </tr>
            </thead>
            <tbody>
              {tenders.map((t) => (
                <tr key={t.accountId}>
                  <td>
                    {t.code} {t.name}
                  </td>
                  <td className="num">{count(t.openLines)}</td>
                  <td>{t.oldest ? dayLabel(t.oldest) : "—"}</td>
                  <td className="num">{rupiah(t.balance)}</td>
                </tr>
              ))}
              <tr className="total-row">
                <td>Total</td>
                <td className="num">{count(tenderLines)}</td>
                <td />
                <td className="num">{rupiah(tenderTotal)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Rekening koran yang belum direkonsiliasi</h2>
        <p className="sub">
          Akun suspense sengaja dibuat tidak reconcilable, sehingga clearing menuliskan lawan
          jurnalnya ke jurnal baris rekening koran itu sendiri. Selama sebuah baris masih{" "}
          <code>is_reconciled = false</code>, Odoo menolak memasang lock date atas periodenya — jadi
          angka di kolom pertama adalah penghalang tutup buku, bukan sekadar catatan.
        </p>
        {statements.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Jurnal bank</th>
                  <th>Baris</th>
                  <th>Terlama</th>
                  <th>Nilai</th>
                  <th>Narasi belum terurai</th>
                  <th>MID belum dipetakan</th>
                </tr>
              </thead>
              <tbody>
                {statements.map((s) => (
                  <tr key={s.journalId}>
                    <td>{s.journalCode}</td>
                    <td className="num">{count(s.lineCount)}</td>
                    <td>{s.oldest ? dayLabel(s.oldest) : "—"}</td>
                    <td className="num">{rupiah(s.amount)}</td>
                    <td className="num">{count(s.unparsed)}</td>
                    <td className="num">{count(s.unmappedMid)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Semua baris rekening koran sudah cocok.</p>
        )}
      </div>
    </>
  );
}
