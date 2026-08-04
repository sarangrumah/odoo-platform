import { api } from "@/lib/session";

interface WeeklyRow {
  id: number;
  week: string;
  vertical: { code: string; name: string } | null;
  project: string;
  author: string;
  state: "draft" | "submitted" | "reviewed";
  health: "on_track" | "at_risk" | "blocked";
  done_count: number;
  done_points: number;
  carry_over: number;
  hours: number;
  cycle_time_team: number;
  hold_count: number;
  waiting_user_count: number;
  plan_this_week: string;
  blocker: string;
  next_week: string;
}

export const dynamic = "force-dynamic";

export default async function WeeklyPage({
  searchParams,
}: {
  searchParams: Promise<{ week?: string }>;
}) {
  const params = await searchParams;
  const query = params.week ? `?week=${encodeURIComponent(params.week)}` : "";
  const rows = (await api<WeeklyRow[]>(`/vaspmo/api/weekly${query}`)) ?? [];

  const submitted = rows.filter((row) => row.state !== "draft").length;
  const week = rows[0]?.week ?? params.week ?? "—";

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Weekly Progress</h1>
          <div className="sub">
            {week} · {submitted}/{rows.length} sudah submit · draft dibuat otomatis Jumat 15:00
          </div>
        </div>
      </header>

      <div className="content">
        {rows.length === 0 ? (
          <div className="card">
            <div className="body dim">
              Belum ada laporan untuk minggu ini. Cron Jumat 15:00 akan membuat draft per
              project aktif, sudah terisi bagian faktualnya.
            </div>
          </div>
        ) : (
          rows.map((row) => (
            <div className="card" key={row.id}>
              <header>
                {row.vertical ? (
                  <span className="vert">
                    <i />
                    {row.vertical.code}
                  </span>
                ) : null}
                <h2>{row.project || "tanpa project"}</h2>
                <span className={`pill ${row.state === "draft" ? "warn" : "ok"}`}>
                  {row.state === "draft" ? "Belum submit" : "Submitted"}
                </span>
                <span className="hint">{row.author}</span>
              </header>
              <div className="body">
                <div className="grid g4" style={{ marginBottom: 14 }}>
                  <div>
                    <div className="eyebrow">Selesai (otomatis)</div>
                    <div className="mono strong">
                      {row.done_count} task · {row.done_points} pts
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow">Carry-over</div>
                    <div className="mono strong">{row.carry_over}</div>
                  </div>
                  <div>
                    <div className="eyebrow">Jam tercatat</div>
                    <div className="mono strong">{row.hours.toFixed(1)}</div>
                  </div>
                  <div>
                    <div className="eyebrow">Cycle time tim</div>
                    <div className="mono strong">{row.cycle_time_team.toFixed(1)} jam</div>
                  </div>
                </div>
                <dl className="kv">
                  <dt>Rencana minggu ini</dt>
                  <dd>{row.plan_this_week || <span className="dim">belum diisi</span>}</dd>
                  <dt>Blocker</dt>
                  <dd>{row.blocker || <span className="dim">tidak ada</span>}</dd>
                  <dt>Rencana minggu depan</dt>
                  <dd>{row.next_week || <span className="dim">belum diisi</span>}</dd>
                  <dt>Hold / verifikasi</dt>
                  <dd className="mono">
                    {row.hold_count} hold · {row.waiting_user_count} menunggu user
                  </dd>
                </dl>
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
