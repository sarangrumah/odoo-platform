import { api } from "@/lib/session";

import { updateStage } from "../actions";
import RowForm from "../row-form";

interface Stage {
  id: number;
  name: string;
  code: string;
  sequence: number;
  applies_to: string;
  sla_clock: "running" | "paused" | "user_side" | "stopped";
  is_hold: boolean;
  is_waiting_user: boolean;
  is_closed: boolean;
  auto_close_days: number;
  require_reason: boolean;
  next_stages: Array<{ id: number; name: string }>;
}

const CLOCKS: Array<{ value: Stage["sla_clock"]; label: string }> = [
  { value: "running", label: "running — dihitung ke tim" },
  { value: "paused", label: "paused — dikurangkan dari cycle time" },
  { value: "user_side", label: "user_side — dibukukan ke user" },
  { value: "stopped", label: "stopped — pekerjaan tutup" },
];

export const dynamic = "force-dynamic";

export default async function StagesPage() {
  const rows = (await api<Stage[]>("/vaspmo/api/admin/stages")) ?? [];

  return (
    <>
      <div className="card">
        <header>
          <h2>Stage &amp; jam SLA</h2>
          <span className="hint">{rows.length} stage</span>
        </header>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Stage</th>
                <th>Code</th>
                <th>Berlaku</th>
                <th>Sifat</th>
                <th>Transisi diizinkan</th>
                <th style={{ minWidth: 520 }}>Jam SLA · auto-close · wajib alasan · urutan</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={`sev ${
                    row.is_hold ? "hold" : row.is_waiting_user ? "warn" : row.is_closed ? "ok" : ""
                  }`}
                >
                  <td className="strong">{row.name}</td>
                  <td className="mono">{row.code}</td>
                  <td className="dim">{row.applies_to}</td>
                  <td>
                    {row.is_hold ? <span className="pill hold">hold</span> : null}
                    {row.is_waiting_user ? <span className="pill warn">waiting user</span> : null}
                    {row.is_closed ? <span className="pill ok">closing</span> : null}
                    {!row.is_hold && !row.is_waiting_user && !row.is_closed ? (
                      <span className="dim">urutan</span>
                    ) : null}
                  </td>
                  <td className="dim" style={{ fontSize: 11.5 }}>
                    {row.next_stages.map((stage) => stage.name).join(", ") || "bebas"}
                  </td>
                  <td>
                    <RowForm action={updateStage} id={row.id}>
                      <select name="sla_clock" defaultValue={row.sla_clock} style={{ width: 260 }}>
                        {CLOCKS.map((clock) => (
                          <option key={clock.value} value={clock.value}>
                            {clock.label}
                          </option>
                        ))}
                      </select>
                      <input
                        name="auto_close_days"
                        type="text"
                        defaultValue={String(row.auto_close_days)}
                        style={{ width: 60 }}
                        aria-label="auto-close hari kerja"
                      />
                      <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
                        <input
                          name="require_reason"
                          type="checkbox"
                          defaultChecked={row.require_reason}
                        />
                        alasan
                      </label>
                      <input
                        name="sequence"
                        type="text"
                        defaultValue={String(row.sequence)}
                        style={{ width: 60 }}
                        aria-label="urutan"
                      />
                    </RowForm>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="body">
          <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
            Kolom <b>jam SLA</b> inilah yang membuat metrik jujur: <code>paused</code>{" "}
            mengeluarkan waktu hold dari cycle time tim, <code>user_side</code> mencatat waktu
            sebagai milik user. Mengubah satu baris di sini langsung mengubah perilaku board,
            cron auto-close, dan angka di laporan mingguan — dan tercatat di log sebagai{" "}
            <code>master_data_change</code>. Kombinasi yang tidak koheren (mis. stage Hold
            dengan jam <code>running</code>) akan ditolak Odoo, bukan diterima diam-diam.
          </p>
        </div>
      </div>
    </>
  );
}
