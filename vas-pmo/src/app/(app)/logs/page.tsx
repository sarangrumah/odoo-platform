import Link from "next/link";

import { api } from "@/lib/session";

interface LogRow {
  ts: string;
  actor: string;
  model: string;
  res_id: number;
  action: string;
  changes: Record<string, unknown>;
  reason: string;
  hash: string;
}

const MODELS = [
  { key: "", label: "Semua model" },
  { key: "project.task", label: "Task" },
  { key: "custom.change.request", label: "Change Request" },
  { key: "project.project", label: "Project" },
  { key: "custom.weekly.progress", label: "Weekly" },
  { key: "custom.project.vertical", label: "Vertical" },
  { key: "project.task.type", label: "Stage" },
];

const HIGHLIGHT: Record<string, string> = {
  hold: "hold",
  auto_close: "warn",
  verify_done: "ok",
  cr_reject: "crit",
  cr_approve: "ok",
  master_data_change: "crit",
};

export const dynamic = "force-dynamic";

export default async function LogsPage({
  searchParams,
}: {
  searchParams: Promise<{ model?: string; action?: string }>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.model) query.set("model", params.model);
  if (params.action) query.set("action", params.action);
  query.set("limit", "150");

  const rows = (await api<LogRow[]>(`/vaspmo/api/logs?${query.toString()}`)) ?? [];

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Log transaksi</h1>
          <div className="sub">
            {rows.length} baris · append-only, tiap baris terangkai hash ke baris sebelumnya
          </div>
        </div>
      </header>

      <div className="content">
        <div className="card">
          <header>
            <h2>Riwayat perubahan</h2>
            <span className="hint">sumber: pdp.audit_log_v</span>
          </header>
          <div className="body" style={{ paddingBottom: 0 }}>
            <div className="chipbar row">
              {MODELS.map((model) => (
                <Link
                  key={model.key || "all"}
                  href={model.key ? `/logs?model=${encodeURIComponent(model.key)}` : "/logs"}
                  className="pill"
                  style={
                    (params.model ?? "") === model.key
                      ? { background: "var(--accent-soft)", color: "var(--accent-ink)" }
                      : undefined
                  }
                >
                  {model.label}
                </Link>
              ))}
            </div>
          </div>
          <div className="tablewrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>Waktu</th>
                  <th>Aktor</th>
                  <th>Model</th>
                  <th className="num">ID</th>
                  <th>Aksi</th>
                  <th>Perubahan</th>
                  <th>Alasan</th>
                  <th>Hash</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="dim">
                      Belum ada entri untuk filter ini.
                    </td>
                  </tr>
                ) : (
                  rows.map((row, index) => (
                    <tr
                      key={`${row.ts}-${index}`}
                      className={`sev ${HIGHLIGHT[row.action] ?? ""}`}
                    >
                      <td className="mono">{String(row.ts).replace("T", " ").slice(0, 19)}</td>
                      <td>{row.actor || <span className="dim">sistem</span>}</td>
                      <td className="mono dim">{row.model}</td>
                      <td className="num">{row.res_id}</td>
                      <td>
                        <span className={`pill ${HIGHLIGHT[row.action] ?? ""}`}>{row.action}</span>
                      </td>
                      <td className="mono dim" style={{ fontSize: 11, maxWidth: 380 }}>
                        {Object.keys(row.changes ?? {}).length
                          ? JSON.stringify(row.changes).slice(0, 220)
                          : "—"}
                      </td>
                      <td style={{ fontSize: 12 }}>{row.reason || <span className="dim">—</span>}</td>
                      <td className="mono dim" style={{ fontSize: 11 }}>
                        {row.hash || "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
