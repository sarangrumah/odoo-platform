import Link from "next/link";

import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel } from "@/lib/format";
import { defaultCompanyIds } from "@/lib/queries/common";
import { ASSUME, briefing, ledgerPulse, type Severity } from "@/lib/queries/insights";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "hentikan dulu",
  warning: "perlu tindakan",
  info: "layak dilihat",
};

export default async function ActionsPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [findings, pulse] = await Promise.all([briefing(scope), ledgerPulse(scope)]);
  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();
  const withQs = (href: string) => (qs && !href.includes("?") ? `${href}?${qs}` : href);

  const critical = findings.filter((f) => f.severity === "critical");

  return (
    <>
      <div className="page-head">
        <h1>Rekomendasi</h1>
        <p>
          Temuan berperingkat dari seluruh dasbor per {dayLabel(filters.asOf)}, disusun dari{" "}
          {count(pulse.lines)} baris jurnal dalam 30 hari terakhir. Tidak ada model bahasa di
          halaman ini: setiap temuan adalah ambang yang diterapkan pada angka yang sudah dihitung
          di halaman lain, sehingga aritmetikanya bisa Anda periksa sendiri.
        </p>
      </div>

      {critical.length > 0 && (
        <div className="note" style={{ borderLeftColor: "var(--critical)", marginBottom: 18 }}>
          <strong>Ada {count(critical.length)} temuan yang membatalkan angka lain di dasbor ini.</strong>{" "}
          Selesaikan lebih dulu sebelum memakai halaman mana pun.
        </div>
      )}

      {findings.length === 0 ? (
        <div className="card">
          <h2>Tidak ada temuan</h2>
          <p className="sub">
            Tidak ada yang melewati ambang di bawah pada tanggal potong ini. Itu berarti bersih
            menurut ambang tersebut, bukan bersih menurut segalanya.
          </p>
        </div>
      ) : (
        findings.map((f) => (
          <div className="card" style={{ marginBottom: 14 }} key={f.id}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0 }}>{f.title}</h2>
              <span className="tie-status" data-state={f.severity === "info" ? "info" : "bad"}>
                {SEVERITY_LABEL[f.severity]}
              </span>
              <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                {f.figure}
              </span>
            </div>
            <p style={{ margin: "8px 0 0", fontSize: 13.5, lineHeight: 1.6 }}>{f.detail}</p>
            <p style={{ margin: "10px 0 0" }}>
              <Link className="agent-link" href={withQs(f.href)}>
                Buka halamannya →
              </Link>
            </p>
          </div>
        ))
      )}

      <div className="card">
        <h2>Ambang yang dipakai halaman ini</h2>
        <p className="sub">
          Ini penilaian, bukan konstanta hasil penyetelan. Dicetak di sini supaya pembaca yang
          tidak setuju bisa melihatnya, bukan menemukannya karena ada temuan yang hilang.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ambang</th>
                <th>Nilai</th>
                <th>Artinya</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Item dianggap tua</td>
                <td className="num">{ASSUME.staleDays} hari</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Open item lebih tua dari ini disebut namanya, berapa pun nilainya.
                </td>
              </tr>
              <tr>
                <td>Nilai dianggap material</td>
                <td className="num">Rp {ASSUME.materialAmount.toLocaleString("id-ID")}</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Di bawah ini tidak diberi baris sendiri di halaman ini.
                </td>
              </tr>
              <tr>
                <td>Konsentrasi tunggakan</td>
                <td className="num">{Math.round(ASSUME.concentrationShare * 100)}%</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Bila sedikit vendor memegang porsi sebesar ini, itu dilaporkan sebagai temuan.
                </td>
              </tr>
              <tr>
                <td>Vendor disebut namanya</td>
                <td className="num">&gt; {ASSUME.vendorOverdueDays} hari</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Vendor yang menunggu lebih lama dari ini disebut satu per satu.
                </td>
              </tr>
              <tr>
                <td>Kas dianggap mendesak</td>
                <td className="num">{ASSUME.imminentDays} hari</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Jatuh tempo dalam jendela ini dihitung sebagai kebutuhan kas terdekat.
                </td>
              </tr>
              <tr>
                <td>Akun dianggap penuh derau</td>
                <td className="num">{ASSUME.nettingNoiseRatio}×</td>
                <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                  Bila netting memangkas baris sebanyak ini, akunnya dilaporkan layak dibereskan.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
