import Link from "next/link";

import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah } from "@/lib/format";
import { q } from "@/lib/db";
import { BUCKETS, agingDocuments, type AgingSide } from "@/lib/queries/ap";
import { defaultCompanyIds } from "@/lib/queries/common";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type Params = Promise<{ partnerId: string }>;

const BUCKET_LABEL = Object.fromEntries(BUCKETS.map((b) => [b.code, b.label]));

export default async function PartnerDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const [{ partnerId }, sp, defaults] = await Promise.all([
    params,
    searchParams,
    defaultCompanyIds(),
  ]);
  const filters = parseFinanceFilters(sp, defaults);
  const rawSide = Array.isArray(sp.side) ? sp.side[0] : sp.side;
  const side: AgingSide = rawSide === "receivable" ? "receivable" : "payable";

  const id = Number(partnerId);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [docs, partner] = await Promise.all([
    agingDocuments(side, id, scope),
    id
      ? q<Record<string, string | null>>(`SELECT name FROM res_partner WHERE id = $1`, [id])
      : Promise.resolve([]),
  ]);

  const name = partner[0]?.name ? String(partner[0].name) : "Tanpa lawan transaksi";
  const total = docs.reduce((s, d) => s + d.outstanding, 0);
  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();

  return (
    <>
      <div className="page-head">
        <h1>{name}</h1>
        <p>
          {side === "payable" ? "Hutang" : "Piutang"} terbuka per {dayLabel(filters.asOf)} —{" "}
          {count(docs.length)} dokumen, {rupiah(Math.abs(total))}.{" "}
          <Link href={qs ? `/ap?${qs}` : "/ap"}>Kembali ke ringkasan</Link>
        </p>
      </div>

      <div className="card">
        {docs.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Nomor</th>
                  <th>Referensi</th>
                  <th>Akun</th>
                  <th>Tanggal</th>
                  <th>Jatuh tempo</th>
                  <th>Lewat (hari)</th>
                  <th>Bucket</th>
                  <th>Nilai asal</th>
                  <th>Terbayar</th>
                  <th>Sisa</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d, i) => (
                  <tr key={`${d.moveId}-${i}`}>
                    <td>{d.docNo}</td>
                    <td>{d.reference || "—"}</td>
                    <td>{d.accountCode}</td>
                    <td>{dayLabel(d.docDate)}</td>
                    <td>{d.dueDate ? dayLabel(d.dueDate) : "—"}</td>
                    <td className="num">{d.overdueDays ? count(d.overdueDays) : "—"}</td>
                    <td>{BUCKET_LABEL[d.bucket]}</td>
                    <td className="num">{rupiah(Math.abs(d.original))}</td>
                    <td className="num">{rupiah(Math.abs(d.paid))}</td>
                    <td className="num">{rupiah(Math.abs(d.outstanding))}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={9}>Total</td>
                  <td className="num">{rupiah(Math.abs(total))}</td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada dokumen terbuka untuk lawan transaksi ini.</p>
        )}
      </div>
    </>
  );
}
