import Link from "next/link";
import { Suspense } from "react";

import { Kpi } from "@/components/kpi";
import { q } from "@/lib/db";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import { focusPartner as narrowToPartner } from "@/lib/netting";
import { accountCodeSql, accountNameSql, defaultCompanyIds, rootCompanyId } from "@/lib/queries/common";
import { nettedForAccount, partnerBreakdown } from "@/lib/queries/openitems";

export const dynamic = "force-dynamic";

const ROW_LIMIT = 500;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type Params = Promise<{ accountId: string }>;

export default async function AccountDrillPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const [{ accountId }, sp, defaults] = await Promise.all([
    params,
    searchParams,
    defaultCompanyIds(),
  ]);
  const filters = parseFinanceFilters(sp, defaults);
  const id = Number(accountId);
  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();

  const root = await rootCompanyId();
  const accountRows = await q<Record<string, string | null>>(
    `SELECT ${accountCodeSql("$2")} AS code, ${accountNameSql()} AS name, aa.account_type
       FROM account_account aa WHERE aa.id = $1`,
    [id, String(root)],
  );
  const account = accountRows[0];

  return (
    <>
      <div className="page-head">
        <h1>
          {String(account?.code ?? "")} {String(account?.name ?? `Akun #${id}`)}
        </h1>
        <p>
          Open item per {dayLabel(filters.asOf)}, setelah netting FIFO.{" "}
          <Link href={qs ? `/openitems?${qs}` : "/openitems"}>Kembali ke ringkasan akun</Link>
        </p>
      </div>

      {/* Netting an account like GR/IR holds tens of thousands of rows in
          memory for a moment. Its own boundary, so the heading and the
          breadcrumb are on screen while it runs. */}
      <Suspense fallback={<div className="card skeleton" style={{ height: 260 }} />}>
        <NettedBody
          accountId={id}
          asOf={filters.asOf}
          companies={filters.companies}
          focus={filters.focusPartner}
          qs={qs}
        />
      </Suspense>
    </>
  );
}

async function NettedBody({
  accountId,
  asOf,
  companies,
  focus,
  qs,
}: {
  accountId: number;
  asOf: string;
  companies: number[];
  focus: number | "none" | null;
  qs: string;
}) {
  const netted = await nettedForAccount(accountId, asOf, companies);
  const partners = await partnerBreakdown(netted);

  // Narrowing happens HERE, on the netted rows, never in the query. Partnerless
  // rows offset across partners in pass 2 of the netting, so filtering earlier
  // would leave them out of that pass and print a larger remainder than the
  // account summary promised.
  const rows = narrowToPartner(netted.rows, focus);
  const shown = rows.slice(0, ROW_LIMIT);
  const shownTotal = rows.reduce((s, r) => s + r.outstanding, 0);

  const partnerLink = (value: number | "none" | null) => {
    const next = new URLSearchParams(qs);
    if (value === null) next.delete("focusPartner");
    else next.set("focusPartner", String(value));
    const s = next.toString();
    return s ? `?${s}` : "?";
  };

  return (
    <>
      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Outstanding" value={rupiahShort(netted.outstandingAfter)} />
        <Kpi
          label="Baris sebelum netting"
          value={count(netted.linesBefore)}
          hint={`${rupiah(netted.outstandingBefore)}`}
        />
        <Kpi
          label="Baris setelah netting"
          value={count(netted.linesAfter)}
          hint={`${count(netted.linesBefore - netted.linesAfter)} baris saling menghapus`}
        />
        <Kpi label="Lawan transaksi tersisa" value={count(partners.length)} />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Per lawan transaksi</h2>
        <p className="sub">
          Dihitung dari baris yang sudah dinetting, bukan dari query terpisah. Baris tanpa lawan
          transaksi ikut saling menghapus lintas partner — di akun GR/IR itulah yang membuat kredit
          penerimaan barang bertemu debit tagihan vendor.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Lawan transaksi</th>
                <th>Baris</th>
                <th>Terlama</th>
                <th>Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {partners.map((p) => (
                <tr key={String(p.partnerId ?? "none")}>
                  <td>
                    <Link href={partnerLink(p.partnerId ?? "none")}>{p.partnerName}</Link>
                  </td>
                  <td className="num">{count(p.lineCount)}</td>
                  <td>{p.oldestDate ? dayLabel(p.oldestDate) : "—"}</td>
                  <td className="num">{rupiah(p.outstanding)}</td>
                </tr>
              ))}
              <tr className="total-row">
                <td>Total</td>
                <td className="num">{count(netted.linesAfter)}</td>
                <td />
                <td className="num">{rupiah(netted.outstandingAfter)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>
          Baris terbuka
          {focus !== null && (
            <>
              {" "}
              <Link href={partnerLink(null)} style={{ fontSize: 12, fontWeight: 400 }}>
                (hapus filter lawan transaksi)
              </Link>
            </>
          )}
        </h2>
        <p className="sub">
          {count(rows.length)} baris, {rupiah(shownTotal)}.
          {rows.length > ROW_LIMIT
            ? ` Menampilkan ${ROW_LIMIT} teratas — netting tetap dijalankan atas seluruhnya, karena memotong sebelum netting akan menghasilkan angka yang salah.`
            : ""}
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Jurnal</th>
                <th>Referensi</th>
                <th>Tanggal</th>
                <th>Debit/Kredit asal</th>
                <th>Residual as-of</th>
                <th>Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.id}>
                  <td>{String(row.moveName ?? "")}</td>
                  <td>{String(row.ref ?? "") || "—"}</td>
                  <td>{dayLabel(row.date)}</td>
                  <td className="num">{rupiah(row.balance as number)}</td>
                  <td className="num">{rupiah(row.residualAsOf)}</td>
                  <td className="num">{rupiah(row.outstanding)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
