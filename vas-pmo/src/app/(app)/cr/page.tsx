import { api } from "@/lib/session";

interface ChangeRequest {
  id: number;
  code: string;
  name: string;
  vertical: { code: string } | null;
  cr_type: string;
  impact: "low" | "medium" | "high" | "critical";
  priority: string;
  ba: string;
  approval_state: "draft" | "analysis" | "waiting_approval" | "approved" | "rejected";
  approval_progress: string;
  stage: { name: string } | null;
  task_count: number;
  task_done_count: number;
  sla_response_due: string | null;
  sla_response_met: boolean;
  effort_days: number;
}

const STATE_LABEL: Record<ChangeRequest["approval_state"], string> = {
  draft: "Intake",
  analysis: "Analisis",
  waiting_approval: "Menunggu approval",
  approved: "Approved",
  rejected: "Ditolak",
};
const STATE_CLASS: Record<ChangeRequest["approval_state"], string> = {
  draft: "acc",
  analysis: "",
  waiting_approval: "warn",
  approved: "ok",
  rejected: "crit",
};

export const dynamic = "force-dynamic";

export default async function CrPage() {
  const rows = (await api<ChangeRequest[]>("/vaspmo/api/change-requests")) ?? [];
  const intake = rows.filter((row) => row.approval_state === "draft").length;
  const waiting = rows.filter((row) => row.approval_state === "waiting_approval").length;

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Change Request</h1>
          <div className="sub">
            {rows.length} CR · {intake} intake belum di-triage · {waiting} menunggu approval
          </div>
        </div>
      </header>

      <div className="content">
        <div className="card">
          <header>
            <h2>Semua Change Request</h2>
            <span className="hint">record terpisah dari task: ada impact analysis &amp; approval</span>
          </header>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Nomor</th>
                  <th>Vertical</th>
                  <th>Judul</th>
                  <th>Tipe</th>
                  <th>Impact</th>
                  <th>BA</th>
                  <th>Approval</th>
                  <th>Stage</th>
                  <th className="num">Task</th>
                  <th>SLA respons</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="dim">
                      Belum ada change request.
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr
                      key={row.id}
                      className={`sev ${
                        row.approval_state === "rejected"
                          ? "crit"
                          : row.approval_state === "waiting_approval"
                            ? "warn"
                            : row.approval_state === "approved"
                              ? "ok"
                              : ""
                      }`}
                    >
                      <td className="mono strong">{row.code}</td>
                      <td>
                        {row.vertical ? (
                          <span className="vert">
                            <i />
                            {row.vertical.code}
                          </span>
                        ) : (
                          <span className="dim">—</span>
                        )}
                      </td>
                      <td>{row.name}</td>
                      <td className="mono dim">{row.cr_type}</td>
                      <td>
                        <span
                          className={`pill ${
                            row.impact === "critical" ? "crit" : row.impact === "high" ? "warn" : ""
                          }`}
                        >
                          {row.impact}
                        </span>
                      </td>
                      <td>{row.ba || "—"}</td>
                      <td>
                        <span className={`pill ${STATE_CLASS[row.approval_state]}`}>
                          {STATE_LABEL[row.approval_state]}
                        </span>
                        <span className="mono dim" style={{ marginLeft: 6 }}>
                          {row.approval_progress}
                        </span>
                      </td>
                      <td className="dim">{row.stage?.name ?? "—"}</td>
                      <td className="num">
                        {row.task_done_count}/{row.task_count}
                      </td>
                      <td className="mono dim">
                        {row.sla_response_due
                          ? String(row.sla_response_due).replace("T", " ").slice(0, 16)
                          : "—"}
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
