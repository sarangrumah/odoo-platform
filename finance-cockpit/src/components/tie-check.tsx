import { count, rupiah } from "@/lib/format";
import type { TieCheck as Check } from "@/lib/queries/tie";

const STATE_WORD: Record<Check["state"], string> = {
  ok: "cocok",
  bad: "tidak cocok",
  info: "penjelasan",
};

/**
 * One check, rendered so it can be argued with.
 *
 * Colour is never the only signal: the state is spelled out in a word, and the
 * difference is always printed as a number next to what it was expected to be.
 */
export function TieCheckCard({ check, isCount = false }: { check: Check; isCount?: boolean }) {
  const fmt = (v: number) => (isCount ? count(v) : rupiah(v));
  const cls = check.state === "ok" ? "tie-ok" : check.state === "bad" ? "tie-bad" : "tie-info";

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>
          {check.id}. {check.title}
        </h2>
        <span className="tie-status" data-state={check.state}>
          {STATE_WORD[check.state]}
        </span>
      </div>
      <p className="sub">{check.description}</p>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>{check.leftLabel}</th>
              {check.rightLabel && <th>{check.rightLabel}</th>}
              <th>Selisih</th>
              <th>Harapan</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="num">{fmt(check.left)}</td>
              {check.rightLabel && <td className="num">{fmt(check.right)}</td>}
              <td className={`num ${cls}`}>{fmt(check.difference)}</td>
              <td style={{ textAlign: "left", whiteSpace: "normal" }}>{check.expectation}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {check.note && (
        <div className={`note ${check.state === "ok" ? "ok" : ""}`} style={{ marginTop: 12 }}>
          {check.note}
        </div>
      )}

      {check.rows && check.rows.length > 0 && (
        <details className="sql" style={{ marginTop: 10 }}>
          <summary>Rincian ({check.rows.length} baris)</summary>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Rincian</th>
                  <th>{check.leftLabel}</th>
                  <th>{check.rightLabel || "Pembanding"}</th>
                  <th>Selisih</th>
                </tr>
              </thead>
              <tbody>
                {check.rows.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td className="num">{fmt(row.left)}</td>
                    <td className="num">{fmt(row.right)}</td>
                    <td className="num">{fmt(row.difference)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
