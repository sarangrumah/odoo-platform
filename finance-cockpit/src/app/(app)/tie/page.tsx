import { TieCheckCard } from "@/components/tie-check";
import { parseFinanceFilters, today } from "@/lib/finance-filters";
import { count, dayLabel } from "@/lib/format";
import { defaultCompanyIds } from "@/lib/queries/common";
import { runTieChecks } from "@/lib/queries/tie";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/** Checks whose two sides are counts of things, not amounts of money. */
const COUNT_CHECKS = new Set([12]);

export default async function TiePage({ searchParams }: { searchParams: SearchParams }) {
  const [params, defaults] = await Promise.all([searchParams, defaultCompanyIds()]);
  const filters = parseFinanceFilters(params, defaults);
  const now = today();

  const checks = await runTieChecks(
    { asOf: filters.asOf, from: filters.from, companies: filters.companies },
    now,
  );

  const failed = checks.filter((c) => c.state === "bad");
  const explained = checks.filter((c) => c.state === "info");
  const passed = checks.filter((c) => c.state === "ok");

  return (
    <>
      <div className="page-head">
        <h1>Pembuktian Angka</h1>
        <p>
          Setiap cek di halaman ini dijalankan langsung ke basis data saat halaman dimuat — tidak
          ada angka yang ditulis tetap di kode. Semua diukur per{" "}
          <strong>{dayLabel(filters.asOf)}</strong>, dan separuhnya hanya bermakna pada tanggal
          tertentu, jadi tanggal potong ikut menentukan artinya.
        </p>
      </div>

      <div
        className={`note ${failed.length === 0 ? "ok" : ""}`}
        style={{
          marginBottom: 18,
          ...(failed.length ? { borderLeftColor: "var(--critical)" } : {}),
        }}
      >
        {failed.length === 0 ? (
          <>
            <strong>Nol selisih di setiap cek yang seharusnya nol.</strong> {count(passed.length)}{" "}
            cek cocok, {count(explained.length)} cek adalah penjelasan yang memang tidak nol dan
            sudah dirincikan di bawah.
          </>
        ) : (
          <>
            <strong>
              {count(failed.length)} cek tidak cocok: {failed.map((c) => c.id).join(", ")}.
            </strong>{" "}
            Telusuri dulu sebelum memakai angka di halaman lain — sebuah selisih di sini berarti
            salah satu halaman sedang menjawab pertanyaan yang berbeda dari yang dikiranya.
          </>
        )}
      </div>

      {checks.map((check) => (
        <TieCheckCard key={check.id} check={check} isCount={COUNT_CHECKS.has(check.id)} />
      ))}

      <div className="note" style={{ marginTop: 4 }}>
        <strong>Apa yang TIDAK dibuktikan halaman ini.</strong> Cek 1–13 hanya menunjukkan bahwa
        dasbor konsisten dengan dirinya sendiri dan dengan buku besar. Satu-satunya bukti bahwa
        angkanya sama dengan report Odoo adalah memanggil report itu sendiri, dan itu butuh
        kredensial admin yang sengaja tidak dipegang aplikasi ini. Jalankan{" "}
        <code>npm run test:parity</code> untuk itu.
      </div>
    </>
  );
}
