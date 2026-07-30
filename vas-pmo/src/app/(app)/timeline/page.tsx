import { api } from "@/lib/session";

interface Project {
  id: number;
  code: string;
  name: string;
  vertical: { code: string } | null;
  health: "on_track" | "at_risk" | "blocked";
  progress: number;
  overdue: number;
  hold: number;
  waiting_user: number;
  date_start: string | null;
  date_end: string | null;
}

const HEALTH_CLASS: Record<Project["health"], string> = {
  on_track: "",
  at_risk: "warn",
  blocked: "crit",
};

export const dynamic = "force-dynamic";

/** Twelve columns spanning the quarter that contains today. */
function quarterWindow(now: Date) {
  const startMonth = Math.floor(now.getMonth() / 3) * 3;
  const start = new Date(now.getFullYear(), startMonth, 1);
  const end = new Date(now.getFullYear(), startMonth + 3, 0);
  return { start, end, span: end.getTime() - start.getTime() };
}

export default async function TimelinePage() {
  const projects = (await api<Project[]>("/vaspmo/api/projects")) ?? [];
  const now = new Date();
  const { start, end, span } = quarterWindow(now);

  const columns = Array.from({ length: 12 }, (_, index) => {
    const month = new Date(start.getFullYear(), start.getMonth() + Math.floor(index / 4), 1);
    return `${month.toLocaleString("id-ID", { month: "short" }).slice(0, 1).toUpperCase()}${
      (index % 4) + 1
    }`;
  });

  const pct = (value: Date) =>
    Math.max(0, Math.min(100, ((value.getTime() - start.getTime()) / span) * 100));
  const nowLeft = pct(now);

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Timeline portfolio</h1>
          <div className="sub">
            {start.toLocaleDateString("id-ID", { month: "short", year: "numeric" })} –{" "}
            {end.toLocaleDateString("id-ID", { month: "short", year: "numeric" })} · garis
            tegak = hari ini
          </div>
        </div>
      </header>

      <div className="content">
        <div className="card">
          <header>
            <h2>Rentang project</h2>
            <span className="hint">warna bar mengikuti kesehatan project</span>
          </header>
          <div className="body">
            {projects.length === 0 ? (
              <p className="dim" style={{ margin: 0 }}>
                Belum ada project untuk digambar.
              </p>
            ) : (
              <div className="tl">
                <div className="tl-inner">
                  <div className="tl-head">
                    <span>Project</span>
                    {columns.map((label, index) => (
                      <span key={`${label}-${index}`}>{label}</span>
                    ))}
                  </div>

                  {projects.map((project) => {
                    // A project with no dates still deserves a row: "we do not know when
                    // this runs" is information, and hiding it loses it.
                    const from = project.date_start ? new Date(project.date_start) : null;
                    const to = project.date_end ? new Date(project.date_end) : null;
                    const left = from ? pct(from) : 0;
                    const right = to ? pct(to) : Math.max(left + 8, nowLeft);
                    const width = Math.max(right - left, 4);

                    return (
                      <div className="tl-row" key={project.id}>
                        <div className="tl-name">
                          <span className="row" style={{ gap: 6 }}>
                            {project.vertical ? (
                              <span className="vert">
                                <i />
                              </span>
                            ) : null}
                            {project.name}
                          </span>
                          <em>
                            {project.progress.toFixed(0)}% ·{" "}
                            {project.health === "on_track"
                              ? "on-track"
                              : project.health === "at_risk"
                                ? "berisiko"
                                : "blocked"}
                            {project.hold ? ` · ${project.hold} hold` : ""}
                            {!from && !to ? " · tanpa tanggal" : ""}
                          </em>
                        </div>
                        <div className="tl-track">
                          <div className="tl-grid">
                            {Array.from({ length: 12 }, (_, index) => (
                              <i key={index} />
                            ))}
                          </div>
                          <div
                            className={`tl-bar ${HEALTH_CLASS[project.health]}`}
                            style={{ left: `${left}%`, width: `${width}%` }}
                          >
                            <span>{project.code || project.name.slice(0, 22)}</span>
                          </div>
                          <div className="tl-now" style={{ left: `${nowLeft}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
