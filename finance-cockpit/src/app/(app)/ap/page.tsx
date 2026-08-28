import Link from "next/link";

import { AgingTable } from "@/components/aging-table";
import { Kpi } from "@/components/kpi";
import { parseFinanceFilters, serialiseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel, rupiah, rupiahShort } from "@/lib/format";
import {
  agingByPartner,
  totalsOf,
  unpaidBills,
  upcomingDue,
  unappliedPayments,
} from "@/lib/queries/ap";
import { defaultCompanyIds } from "@/lib/queries/common";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function ApPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const scope = { asOf: filters.asOf, companies: filters.companies };

  const [payable, receivable, bills, due, unapplied] = await Promise.all([
    agingByPartner("payable", scope),
    agingByPartner("receivable", scope),
    unpaidBills({ ...scope, limit: 50 }),
    upcomingDue(scope),
    unappliedPayments(scope),
  ]);

  const apTotals = totalsOf(payable);
  const arTotals = totalsOf(receivable);

  // Overdue is everything except the not-due bucket. Stated rather than
  // inferred, because "overdue" is the number people quote in meetings.
  const overdue = (t: typeof apTotals) => t.total - t.buckets.not_due;
  const severe = (t: typeof apTotals) =>
    t.buckets.d_91_180 + t.buckets.d_181_365 + t.buckets.d_over_365;

  const qs = serialiseFinanceFilters(filters, { asOf: today() }).toString();
  const partnerHref = (side: "payable" | "receivable") => (row: { partnerId: number }) =>
    row.partnerId
      ? `/ap/${row.partnerId}?${new URLSearchParams(qs ? `${qs}&side=${side}` : `side=${side}`).toString()}`
      : null;

  return (
    <>
      <div className="page-head">
        <h1>Hutang &amp; Pembayaran</h1>
        <p>
          Posisi per {dayLabel(filters.asOf)}. Aging memakai varian paritas — residual saat ini,
          tanpa pengecualian jurnal — sehingga totalnya sama dengan Aged Payable di Odoo. Selisih
          terhadap varian as-of dijelaskan di halaman Pembuktian Angka.
        </p>
      </div>

      <div className="grid kpis" style={{ marginBottom: 14 }}>
        <Kpi label="Total hutang terbuka" value={rupiahShort(Math.abs(apTotals.total))} />
        <Kpi
          label="Jatuh tempo terlewat"
          value={rupiahShort(Math.abs(overdue(apTotals)))}
          hint={`${count(apTotals.itemCount)} item, ${count(apTotals.partnerCount)} vendor`}
        />
        <Kpi
          label="Lewat 90 hari"
          value={rupiahShort(Math.abs(severe(apTotals)))}
          hint="Bucket 91–180, 181–365 dan > 365 hari"
        />
        <Kpi
          label="Total piutang terbuka"
          value={rupiahShort(Math.abs(arTotals.total))}
          hint={`${count(arTotals.itemCount)} item`}
        />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Jatuh tempo empat pekan ke depan</h2>
        <p className="sub">
          Hutang terbuka yang jatuh tempo setelah {dayLabel(filters.asOf)}, dikelompokkan per pekan.
        </p>
        {due.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Pekan mulai</th>
                  <th>Item</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {due.map((w) => (
                  <tr key={w.weekStart}>
                    <td>{dayLabel(w.weekStart)}</td>
                    <td className="num">{count(w.itemCount)}</td>
                    <td className="num">{rupiah(Math.abs(w.amount))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada yang jatuh tempo dalam empat pekan ke depan.</p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Umur hutang per vendor</h2>
        <p className="sub">
          Klik nama vendor untuk melihat dokumen yang membentuk saldonya.
        </p>
        <AgingTable rows={payable} totals={apTotals} href={partnerHref("payable")} />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Umur piutang per lawan transaksi</h2>
        <p className="sub">
          Sebagian besar piutang di database ini adalah piutang POS per tender, yang tidak mencatat
          pelanggan — semuanya jatuh ke baris &ldquo;Tanpa lawan transaksi&rdquo;. Pergerakannya
          ditangani di halaman Clearing POS, bukan lewat penagihan.
        </p>
        <AgingTable rows={receivable} totals={arTotals} href={partnerHref("receivable")} />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Tagihan yang belum lunas</h2>
        <p className="sub">
          Bill terposting dengan payment_state &ldquo;not_paid&rdquo; atau &ldquo;partial&rdquo;,
          diurutkan menurut jatuh tempo. 50 teratas.
        </p>
        {bills.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Nomor</th>
                  <th>Vendor</th>
                  <th>Tanggal</th>
                  <th>Jatuh tempo</th>
                  <th>Status</th>
                  <th>Nilai</th>
                  <th>Sisa</th>
                </tr>
              </thead>
              <tbody>
                {bills.map((b) => (
                  <tr key={b.moveId}>
                    <td>{b.name}</td>
                    <td>{b.partnerName || "—"}</td>
                    <td>{b.invoiceDate ? dayLabel(b.invoiceDate) : "—"}</td>
                    <td>{b.dueDate ? dayLabel(b.dueDate) : "—"}</td>
                    <td>{b.paymentState}</td>
                    <td className="num">{rupiah(Math.abs(b.amountTotal))}</td>
                    <td className="num">{rupiah(Math.abs(b.amountResidual))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada tagihan terbuka.</p>
        )}
      </div>

      <div className="card">
        <h2>Pembayaran yang belum dialokasikan</h2>
        <p className="sub">
          Pembayaran terposting yang belum dikaitkan ke tagihan mana pun. Kolom{" "}
          <code>is_unapplied</code> berasal dari modul custom_account_reconcile; bila modulnya tidak
          terpasang, bagian ini kosong dan bukan berarti tidak ada.
        </p>
        {unapplied.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Nomor</th>
                  <th>Lawan transaksi</th>
                  <th>Tanggal</th>
                  <th>Arah</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {unapplied.map((p) => (
                  <tr key={p.paymentId}>
                    <td>{p.moveName}</td>
                    <td>{p.partnerName || "—"}</td>
                    <td>{dayLabel(p.date)}</td>
                    <td>{p.paymentType}</td>
                    <td className="num">{rupiah(p.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sub">Tidak ada pembayaran menggantung.</p>
        )}
      </div>

      <p style={{ marginTop: 18, fontSize: 12, color: "var(--text-muted)" }}>
        Angka di halaman ini dibuktikan di{" "}
        <Link href={qs ? `/tie?${qs}` : "/tie"}>Pembuktian Angka</Link>, cek 3, 4 dan 5.
      </p>
    </>
  );
}
