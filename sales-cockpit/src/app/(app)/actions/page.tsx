import { dayLabel, count, rupiahShort } from "@/lib/format";
import { parseFilters, previousPeriod } from "@/lib/filters";
import { briefing, type Finding } from "@/lib/queries/insights";
import { dataExtent } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const SEVERITY_LABEL: Record<Finding["severity"], string> = {
  peluang: "Peluang",
  perhatian: "Perhatian",
  risiko: "Risiko",
};

function FindingCard({ finding, rank }: { finding: Finding; rank: number }) {
  return (
    <article className="card finding">
      <header>
        <span className="rank">{rank}</span>
        <div>
          <h2>{finding.title}</h2>
          <p className="meta">
            <span className="tag" data-severity={finding.severity}>
              {SEVERITY_LABEL[finding.severity]}
            </span>
            <span>{finding.owner}</span>
          </p>
        </div>
        <div className="impact">
          {finding.impactPerMonth > 0 ? (
            <>
              <span className="value">{rupiahShort(finding.impactPerMonth)}</span>
              <span className="label">potensi / bulan</span>
            </>
          ) : (
            <span className="label">tidak dinilai rupiah</span>
          )}
        </div>
      </header>

      <p className="narrative">{finding.narrative}</p>

      <div className="evidence">
        {finding.evidence.map((e) => (
          <div key={e.label} className="item">
            <span className="k">{e.label}</span>
            <span className="v">{e.value}</span>
          </div>
        ))}
      </div>

      <h3>Langkah yang disarankan</h3>
      <ol className="actions">
        {finding.actions.map((action) => (
          <li key={action}>{action}</li>
        ))}
      </ol>

      <p className="note assumption">
        <strong>Dasar perhitungan.</strong> {finding.assumption}
      </p>
    </article>
  );
}

export default async function ActionsPage({ searchParams }: { searchParams: SearchParams }) {
  const [params, extent] = await Promise.all([searchParams, dataExtent()]);
  const filters = parseFilters(params, extent);
  const prev = previousPeriod(filters);
  const result = await briefing(filters, extent);
  // The preceding window can fall entirely before the first loaded day; saying
  // "Pembanding: 4 Apr – 11 Jun" when nothing was sold then invites a reader to
  // trust a comparison the narrative itself refuses to make.
  const comparable = prev.to >= extent.start;

  const quantified = result.findings.filter((f) => f.impactPerMonth > 0);
  const total = quantified.reduce((sum, f) => sum + f.impactPerMonth, 0);

  return (
    <>
      <div className="page-head">
        <h1>Rekomendasi Aksi</h1>
        <p>
          {dayLabel(filters.from)} – {dayLabel(filters.to)} ({count(result.generatedFor.days)} hari).{" "}
          {comparable
            ? `Pembanding: ${dayLabel(prev.from)} – ${dayLabel(prev.to)}.`
            : "Rentang pembanding berada di luar data yang termuat, jadi temuan yang butuh perbandingan periode tidak muncul."}{" "}
          Seluruh temuan dihitung ulang dari data setiap halaman ini dibuka dan mengikuti filter di
          atas.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Ringkasan Periode</h2>
        <p className="sub">Disusun dari angka periode ini, bukan dari opini.</p>
        <p className="narrative">{result.headline}</p>
        {quantified.length > 0 && (
          <p className="narrative" style={{ marginBottom: 0 }}>
            Ada {count(result.findings.length)} temuan; {count(quantified.length)} di antaranya bisa
            dinilai dengan total potensi {rupiahShort(total)} per bulan bila seluruh asumsinya
            terpenuhi. Angka itu batas atas untuk menyusun prioritas, bukan target.
          </p>
        )}
      </div>

      {result.findings.length === 0 ? (
        <div className="card">
          <div className="note ok">
            <strong>Tidak ada temuan material pada rentang ini.</strong> Setiap aturan punya ambang
            minimum Rp 25 juta per bulan; melebarkan rentang tanggal biasanya memunculkan kembali
            pola yang tersembunyi di rentang pendek.
          </div>
        </div>
      ) : (
        <div className="findings">
          {result.findings.map((finding, i) => (
            <FindingCard key={finding.id} finding={finding} rank={i + 1} />
          ))}
        </div>
      )}

      <div className="card" style={{ marginTop: 14 }}>
        <h2>Konteks Pasar</h2>
        <p className="sub">
          Alamat dibaca langsung dari Odoo (<code>pos_config → operating_unit → res_partner</code>);
          pemetaan wilayah dari tabel referensi <code>cockpit_area</code> dan{" "}
          <code>cockpit_store_area</code>.
        </p>
        {result.market.mapped ? (
          <div className="note ok">
            <strong>Pemetaan wilayah aktif.</strong> Aturan ATV membandingkan toko dengan sesama toko
            dalam satu aglomerasi, bukan dengan seluruh jaringan.
          </div>
        ) : (
          <div className="note unavailable">
            <strong>Pemetaan wilayah belum ada.</strong> Jalankan{" "}
            <code>sql/002_cockpit_area.sql</code> agar pembanding ATV berpindah dari median jaringan
            ke median wilayah.
          </div>
        )}
        {result.market.mapped && !result.market.figuresComplete && (
          <div className="note unavailable" style={{ marginTop: 10 }}>
            <strong>Indeks fair-share belum aktif.</strong> Jumlah penduduk 15–44 tahun belum diisi
            untuk {result.market.missingFigures.length} wilayah:{" "}
            {result.market.missingFigures.join(", ")}. Temuan ini sengaja diam sampai seluruh
            wilayah terisi — indeks pasar yang dihitung dari sebagian jaringan memeringkatkan toko
            terhadap patokan yang tidak memuat mereka.
          </div>
        )}
        {result.market.figuresComplete && (
          <div className="note ok" style={{ marginTop: 10 }}>
            <strong>Indeks fair-share aktif.</strong> Besar pasar dihitung dari{" "}
            {result.market.basis === "belanja"
              ? "penduduk 15–44 tahun dikali belanja pakaian per kapita"
              : "jumlah penduduk 15–44 tahun"}
            , sumber BPS Long Form SP2020 (SP2022).
            {result.market.basis === "populasi" && (
              <>
                {" "}
                Daya beli belum ditimbang — belanja pakaian per kapita (Susenas) belum terisi untuk{" "}
                {result.market.missingSpend.length} wilayah, sehingga satu penduduk Bekasi dihitung
                setara satu penduduk Jakarta Selatan. Perlu diingat juga bahwa penduduk bukan
                katchment: toko di Jakarta Pusat melayani jauh lebih banyak orang daripada
                penduduknya sendiri, dan kolom <code>catchment_weight</code> masih 1,00 di semua
                toko.
              </>
            )}
          </div>
        )}
        {result.market.stores.length > 0 && (
          <>
            {result.market.withoutAddress > 0 && (
              <div className="note unavailable" style={{ marginTop: 10 }}>
                <strong>
                  {result.market.withoutAddress} toko belum punya alamat di Odoo.
                </strong>{" "}
                Kolom Alamat dan Kota di bawah dibaca langsung dari{" "}
                <code>pos_config → operating_unit → res_partner</code>, jadi kolom itu terisi
                sendiri begitu alamatnya dimasukkan ke Odoo. Kolom Wilayah tidak bergantung pada
                Odoo — sumbernya tabel pemetaan.
              </div>
            )}
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Toko</th>
                    <th>Alamat (Odoo)</th>
                    <th>Kota (Odoo)</th>
                    <th>Wilayah</th>
                    <th>Aglomerasi</th>
                  </tr>
                </thead>
                <tbody>
                  {result.market.stores.map((s) => (
                    <tr key={s.store}>
                      <td>{s.store}</td>
                      <td>{s.address ?? "—"}</td>
                      <td>{s.city ?? "—"}</td>
                      <td>{s.area ?? "—"}</td>
                      <td>{s.agglomeration ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {result.market.needsVerification.length > 0 && (
          <div className="note" style={{ marginTop: 10 }}>
            <strong>Perlu diverifikasi.</strong> {result.market.needsVerification.join("; ")}.
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2>Yang Tidak Bisa Dijawab Data Ini</h2>
        <p className="sub">
          Dicantumkan supaya tidak ada rekomendasi yang diminta melewati batas datanya.
        </p>
        <ul className="caveats">
          {result.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </>
  );
}
