import { notFound } from "next/navigation";

import { api } from "@/lib/session";

import StageForm from "./stage-form";

interface Stage {
  id: number;
  name: string;
  code: string;
  sla_clock: string;
  is_hold: boolean;
  is_waiting_user: boolean;
  is_closed: boolean;
}

interface AuditRow {
  ts: string;
  actor: string;
  action: string;
  changes: Record<string, unknown>;
  reason: string;
}

interface TaskDetail {
  id: number;
  name: string;
  description: string;
  project: { id: number; name: string } | null;
  vertical: { code: string; name: string; legal_entity: string } | null;
  stage: Stage | null;
  assignees: Array<{ id: number; name: string }>;
  priority: string;
  task_type: string;
  story_points: number;
  source: string;
  cr_code: string | null;
  sprint: string | null;
  deadline: string | null;
  sla_due: string | null;
  blocked: boolean;
  hold: {
    reason: string;
    since: string | null;
    until: string | null;
    hours: number;
    expired_notified: boolean;
  };
  verification: {
    owner: string;
    requested_at: string | null;
    due: string | null;
    hours: number;
    reminders: number;
    auto_closed: boolean;
  };
  cycle_time_team: number;
  lead_time_total: number;
  closed_at: string | null;
  log: AuditRow[];
}

export const dynamic = "force-dynamic";

function fmt(value: string | null | undefined) {
  if (!value) return "—";
  return String(value).replace("T", " ").slice(0, 16);
}

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [task, stages] = await Promise.all([
    api<TaskDetail>(`/vaspmo/api/tasks/${id}`),
    api<Stage[]>("/vaspmo/api/meta/stages?applies_to=task"),
  ]);
  if (!task) notFound();

  return (
    <>
      <header className="topbar">
        <div>
          <h1>{task.name}</h1>
          <div className="sub">
            {task.cr_code ? `${task.cr_code} · ` : ""}
            {task.vertical?.code ?? "tanpa vertical"} · {task.stage?.name ?? "tanpa stage"}
          </div>
        </div>
      </header>

      <div className="content">
        <div className="grid g2-1">
          <div className="stackv">
            <div className="card">
              <header>
                <h2>Detail</h2>
                {task.blocked ? <span className="pill crit">Blocked</span> : null}
                {task.stage?.is_hold ? <span className="pill hold">Hold</span> : null}
                {task.stage?.is_waiting_user ? (
                  <span className="pill warn">Menunggu verifikasi user</span>
                ) : null}
              </header>
              <div className="body">
                <dl className="kv">
                  <dt>Project</dt>
                  <dd>{task.project?.name ?? "—"}</dd>
                  <dt>Vertical</dt>
                  <dd>
                    {task.vertical
                      ? `${task.vertical.name}${
                          task.vertical.legal_entity ? ` (${task.vertical.legal_entity})` : ""
                        }`
                      : "—"}
                  </dd>
                  <dt>Induk</dt>
                  <dd>{task.cr_code ?? "project langsung"}</dd>
                  <dt>Sprint</dt>
                  <dd className="mono">{task.sprint ?? "—"}</dd>
                  <dt>PIC</dt>
                  <dd>{task.assignees.map((a) => a.name).join(", ") || "belum ada"}</dd>
                  <dt>Prioritas</dt>
                  <dd>{task.priority}</dd>
                  <dt>Poin</dt>
                  <dd className="mono">{task.story_points}</dd>
                  <dt>Jatuh tempo</dt>
                  <dd className="mono">{fmt(task.deadline)}</dd>
                  <dt>SLA deadline</dt>
                  <dd className="mono">{fmt(task.sla_due)}</dd>
                </dl>
              </div>
            </div>

            <div className="card">
              <header>
                <h2>Dua angka yang jujur</h2>
                <span className="hint">selisihnya = waktu yang bukan milik tim</span>
              </header>
              <div className="body">
                <dl className="kv">
                  <dt>Cycle time tim</dt>
                  <dd className="mono strong">{task.cycle_time_team.toFixed(2)} jam</dd>
                  <dt>Lead time total</dt>
                  <dd className="mono">{task.lead_time_total.toFixed(2)} jam</dd>
                  <dt>Total hold</dt>
                  <dd className="mono">{task.hold.hours.toFixed(2)} jam</dd>
                  <dt>Total tunggu user</dt>
                  <dd className="mono">{task.verification.hours.toFixed(2)} jam</dd>
                </dl>
              </div>
            </div>

            <div className="card">
              <header>
                <h2>Log transaksi</h2>
                <span className="hint">append-only, rantai hash</span>
              </header>
              <div className="body" style={{ paddingTop: 4 }}>
                <ul className="feed">
                  {task.log.length === 0 ? (
                    <li>
                      <time>—</time>
                      <div className="dim">Belum ada perubahan tercatat.</div>
                    </li>
                  ) : (
                    task.log.map((row, index) => (
                      <li key={`${row.ts}-${index}`}>
                        <time>{fmt(row.ts)}</time>
                        <div>
                          <span className="strong">{row.actor || "sistem"}</span>{" "}
                          <span className="pill">{row.action}</span>
                          {row.reason ? (
                            <div className="dim" style={{ marginTop: 4 }}>
                              {row.reason}
                            </div>
                          ) : null}
                          {Object.keys(row.changes ?? {}).length ? (
                            <div className="mono dim" style={{ marginTop: 4, fontSize: 11 }}>
                              {JSON.stringify(row.changes)}
                            </div>
                          ) : null}
                        </div>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>
          </div>

          <div className="stackv">
            <div className="card">
              <header>
                <h2>Aksi</h2>
              </header>
              <div className="body">
                <StageForm
                  taskId={task.id}
                  stages={stages ?? []}
                  currentCode={task.stage?.code ?? ""}
                  currentStageName={task.stage?.name ?? "—"}
                />
              </div>
            </div>

            <div className="card">
              <header>
                <h2>Hold</h2>
              </header>
              <div className="body">
                <dl className="kv">
                  <dt>Alasan</dt>
                  <dd>{task.hold.reason || "—"}</dd>
                  <dt>Sejak</dt>
                  <dd className="mono">{fmt(task.hold.since)}</dd>
                  <dt>Batas</dt>
                  <dd className="mono">{fmt(task.hold.until)}</dd>
                  <dt>Batas lewat</dt>
                  <dd>{task.hold.expired_notified ? "ya, sudah dinotifikasi" : "tidak"}</dd>
                </dl>
              </div>
            </div>

            <div className="card">
              <header>
                <h2>Verifikasi user</h2>
              </header>
              <div className="body">
                <dl className="kv">
                  <dt>PIC brand</dt>
                  <dd>{task.verification.owner || "—"}</dd>
                  <dt>Diminta</dt>
                  <dd className="mono">{fmt(task.verification.requested_at)}</dd>
                  <dt>Batas</dt>
                  <dd className="mono">{fmt(task.verification.due)}</dd>
                  <dt>Reminder</dt>
                  <dd className="mono">{task.verification.reminders}</dd>
                  <dt>Auto-close</dt>
                  <dd>{task.verification.auto_closed ? "ya" : "tidak"}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
