import Link from "next/link";

import ViewSwitcher from "@/components/view-switcher";
import { api } from "@/lib/session";

interface Stage {
  id: number;
  name: string;
  code: string;
  sla_clock: "running" | "paused" | "user_side" | "stopped";
  is_hold: boolean;
  is_waiting_user: boolean;
  is_closed: boolean;
}

interface Task {
  id: number;
  name: string;
  vertical: { code: string } | null;
  stage: Stage | null;
  assignees: Array<{ id: number; name: string }>;
  priority: string;
  story_points: number;
  source: string;
  cr_code: string | null;
  blocked: boolean;
  hold: { reason: string; hours: number };
  verification: { due: string | null };
}

const CLOCK_LABEL: Record<Stage["sla_clock"], string> = {
  running: "jam SLA · jalan",
  paused: "jam SLA · dijeda",
  user_side: "jam SLA · pindah ke sisi user",
  stopped: "jam SLA · berhenti",
};
const CLOCK_CLASS: Record<Stage["sla_clock"], string> = {
  running: "",
  paused: "paused",
  user_side: "user",
  stopped: "",
};

export const dynamic = "force-dynamic";

export default async function BoardPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string; view?: string }>;
}) {
  const params = await searchParams;
  const query = params.project ? `?project_id=${encodeURIComponent(params.project)}` : "";
  const view = params.view === "list" ? "list" : "board";
  const extra = params.project ? `&project=${encodeURIComponent(params.project)}` : "";

  const [stages, tasks] = await Promise.all([
    api<Stage[]>("/vaspmo/api/meta/stages?applies_to=task"),
    api<Task[]>(`/vaspmo/api/tasks${query}`),
  ]);

  const columns = (stages ?? []).sort((a, b) => a.id - b.id);
  const byStage = new Map<number, Task[]>();
  for (const task of tasks ?? []) {
    if (!task.stage) continue;
    const bucket = byStage.get(task.stage.id) ?? [];
    bucket.push(task);
    byStage.set(task.stage.id, bucket);
  }

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Board</h1>
          <div className="sub">
            {tasks?.length ?? 0} task · Hold &amp; Waiting User Verification punya perilaku jam SLA sendiri
          </div>
        </div>
        <ViewSwitcher current={view} base="/board" extra={extra} />
      </header>

      <div className="content">
        {view === "list" ? (
          <div className="card">
            <header>
              <h2>Semua task</h2>
              <span className="hint">data sama dengan Board, tata letak berbeda</span>
            </header>
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Vertical</th>
                    <th>Stage</th>
                    <th>Jam SLA</th>
                    <th>PIC</th>
                    <th className="num">Poin</th>
                    <th>Prioritas</th>
                    <th>Catatan</th>
                  </tr>
                </thead>
                <tbody>
                  {(tasks ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={8} className="dim">
                        Belum ada task.
                      </td>
                    </tr>
                  ) : (
                    (tasks ?? []).map((task) => (
                      <tr
                        key={task.id}
                        className={`sev ${
                          task.blocked
                            ? "crit"
                            : task.stage?.is_hold
                              ? "hold"
                              : task.stage?.is_waiting_user
                                ? "warn"
                                : ""
                        }`}
                      >
                        <td className="strong">
                          <Link href={`/tasks/${task.id}`}>{task.name}</Link>
                          <div className="eyebrow">{task.cr_code ?? `VAS-${task.id}`}</div>
                        </td>
                        <td>
                          {task.vertical ? (
                            <span className="vert">
                              <i />
                              {task.vertical.code}
                            </span>
                          ) : (
                            <span className="dim">—</span>
                          )}
                        </td>
                        <td>{task.stage?.name ?? "—"}</td>
                        <td className="mono dim">{task.stage?.sla_clock ?? "—"}</td>
                        <td className="dim">
                          {task.assignees.map((a) => a.name).join(", ") || "belum ada"}
                        </td>
                        <td className="num">{task.story_points}</td>
                        <td>
                          {task.priority === "critical" || task.priority === "high" ? (
                            <span className="pill crit">{task.priority}</span>
                          ) : (
                            <span className="dim">{task.priority}</span>
                          )}
                        </td>
                        <td className="dim" style={{ fontSize: 12 }}>
                          {task.stage?.is_hold && task.hold.reason
                            ? task.hold.reason
                            : task.stage?.is_waiting_user && task.verification.due
                              ? `verifikasi s.d. ${String(task.verification.due).slice(0, 10)}`
                              : ""}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
        <div className="card">
          <div className="body">
            <div className="board">
              {columns.map((stage) => {
                const items = byStage.get(stage.id) ?? [];
                return (
                  <div className={`col${stage.is_hold ? " aside" : ""}`} key={stage.id}>
                    <header>
                      <b>{stage.name}</b>
                      <span className="count">{items.length}</span>
                    </header>
                    <div className={`clock ${CLOCK_CLASS[stage.sla_clock]}`}>
                      {CLOCK_LABEL[stage.sla_clock]}
                    </div>
                    <div className="stack">
                      {items.map((task) => (
                        <Link
                          href={`/tasks/${task.id}`}
                          key={task.id}
                          className={`tcard${task.blocked ? " blocked" : ""}${
                            stage.is_hold ? " onhold" : ""
                          }`}
                        >
                          <span className="code">
                            {task.cr_code ? task.cr_code : `VAS-${task.id}`}
                          </span>
                          <div className="title">{task.name}</div>
                          <div className="meta">
                            {task.vertical ? (
                              <span className="vert">
                                <i />
                                {task.vertical.code}
                              </span>
                            ) : null}
                            {task.story_points ? (
                              <span className="pill">{task.story_points} pts</span>
                            ) : null}
                            {task.priority === "critical" || task.priority === "high" ? (
                              <span className="pill crit">{task.priority}</span>
                            ) : null}
                            {task.blocked ? <span className="pill crit">Blocked</span> : null}
                            {stage.is_hold && task.hold.reason ? (
                              <span className="pill hold">Hold</span>
                            ) : null}
                            {stage.is_waiting_user && task.verification.due ? (
                              <span className="pill warn">
                                s.d. {String(task.verification.due).slice(0, 10)}
                              </span>
                            ) : null}
                          </div>
                        </Link>
                      ))}
                      {items.length === 0 ? (
                        <p className="dim" style={{ fontSize: 12, margin: "4px 2px" }}>
                          kosong
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        )}
      </div>
    </>
  );
}
