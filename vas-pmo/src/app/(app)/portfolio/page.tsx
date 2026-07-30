import Link from "next/link";

import { api } from "@/lib/session";

interface Summary {
  sprint: string;
  projects_active: number;
  projects_at_risk: number;
  tasks_open: number;
  tasks_hold: number;
  tasks_waiting_user: number;
  tasks_overdue: number;
  tasks_unassigned: number;
  cr_intake: number;
  cr_waiting_approval: number;
  cr_active: number;
}

interface Project {
  id: number;
  code: string;
  name: string;
  vertical: { code: string; name: string; legal_entity: string } | null;
  po: string;
  ba: string;
  health: "on_track" | "at_risk" | "blocked";
  health_note: string;
  progress: number;
  overdue: number;
  hold: number;
  waiting_user: number;
}

const HEALTH_LABEL: Record<Project["health"], string> = {
  on_track: "On-track",
  at_risk: "Berisiko",
  blocked: "Blocked",
};
const HEALTH_CLASS: Record<Project["health"], string> = {
  on_track: "ok",
  at_risk: "warn",
  blocked: "crit",
};

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  const [summary, projects] = await Promise.all([
    api<Summary>("/vaspmo/api/dashboard/summary"),
    api<Project[]>("/vaspmo/api/projects"),
  ]);

  // Worst health first: this page exists to answer "what is slipping".
  const order = { blocked: 0, at_risk: 1, on_track: 2 } as const;
  const rows = [...(projects ?? [])].sort((a, b) => order[a.health] - order[b.health]);

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Portfolio VAS</h1>
          <div className="sub">
            sprint {summary?.sprint ?? "—"} · {summary?.projects_active ?? 0} project aktif
          </div>
        </div>
      </header>

      <div className="content">
        <div className="grid g4">
          <div className="card stat">
            <span className="eyebrow">Project aktif</span>
            <span className="val">{summary?.projects_active ?? 0}</span>
            <span className="foot">{summary?.projects_at_risk ?? 0} perlu perhatian</span>
          </div>
          <div className="card stat">
            <span className="eyebrow">Menunggu verifikasi user</span>
            <span className="val warn">{summary?.tasks_waiting_user ?? 0}</span>
            <span className="foot">jam SLA di sisi user</span>
          </div>
          <div className="card stat">
            <span className="eyebrow">Hold</span>
            <span className="val hold">{summary?.tasks_hold ?? 0}</span>
            <span className="foot">jam SLA dijeda</span>
          </div>
          <div className="card stat">
            <span className="eyebrow">Lewat deadline</span>
            <span className="val crit">{summary?.tasks_overdue ?? 0}</span>
            <span className="foot">
              {summary?.tasks_open ?? 0} task berjalan · {summary?.cr_intake ?? 0} CR intake
            </span>
          </div>
        </div>

        <div className="card">
          <header>
            <h2>Kesehatan project per vertical</h2>
            <span className="hint">paling berisiko dulu</span>
          </header>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Vertical</th>
                  <th>PO / BA</th>
                  <th>Progress</th>
                  <th className="num">Lewat DL</th>
                  <th className="num">Hold</th>
                  <th className="num">Verifikasi</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="dim">
                      Belum ada project. Buat satu di Odoo, atau lewat Change Request.
                    </td>
                  </tr>
                ) : (
                  rows.map((project) => (
                    <tr key={project.id} className={`sev ${HEALTH_CLASS[project.health]}`}>
                      <td className="strong">
                        <Link href={`/board?project=${project.id}`}>{project.name}</Link>
                        {project.code ? <div className="eyebrow">{project.code}</div> : null}
                      </td>
                      <td>
                        {project.vertical ? (
                          <span className="vert">
                            <i />
                            {project.vertical.code}
                          </span>
                        ) : (
                          <span className="dim">—</span>
                        )}
                      </td>
                      <td className="mono dim">
                        {project.po || "—"} / {project.ba || "—"}
                      </td>
                      <td>
                        <div className="bar">
                          <i
                            className={HEALTH_CLASS[project.health] === "ok" ? "" : HEALTH_CLASS[project.health]}
                            style={{ width: `${Math.min(project.progress, 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="num">{project.overdue}</td>
                      <td className="num">{project.hold}</td>
                      <td className="num">{project.waiting_user}</td>
                      <td>
                        <span className={`pill ${HEALTH_CLASS[project.health]}`}>
                          {HEALTH_LABEL[project.health]}
                        </span>
                        {project.health_note ? (
                          <div className="dim" style={{ fontSize: 11.5, marginTop: 3 }}>
                            {project.health_note}
                          </div>
                        ) : null}
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
