import { api } from "@/lib/session";

import { updateRule } from "../actions";
import RowForm from "../row-form";

interface Rule {
  id: number;
  event: string;
  recipient_kind: string;
  group: string;
  channel_wa: boolean;
  channel_email: boolean;
  channel_odoo: boolean;
  active: boolean;
}

const CRITICAL_EVENTS = new Set([
  "overdue",
  "escalation",
  "hold_expired",
  "verify_auto_close",
  "cr_intake_overdue",
]);

export const dynamic = "force-dynamic";

export default async function RulesPage() {
  const rows = (await api<Rule[]>("/vaspmo/api/admin/notify-rules")) ?? [];

  // Grouped by event so "who hears about this" reads as one block per thing that happens.
  const byEvent = new Map<string, Rule[]>();
  for (const row of rows) {
    const bucket = byEvent.get(row.event) ?? [];
    bucket.push(row);
    byEvent.set(row.event, bucket);
  }

  return (
    <>
      <div className="card">
        <header>
          <h2>Aturan notifikasi</h2>
          <span className="hint">
            {rows.length} aturan · perubahan berlaku langsung, tanpa deploy
          </span>
        </header>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Kejadian</th>
                <th>Penerima</th>
                <th>Grup</th>
                <th style={{ minWidth: 420 }}>WA · Email · Odoo · aktif</th>
              </tr>
            </thead>
            <tbody>
              {[...byEvent.entries()].map(([event, items]) =>
                items.map((row, index) => (
                  <tr
                    key={row.id}
                    className={`sev ${CRITICAL_EVENTS.has(event) ? "crit" : ""}`}
                  >
                    <td className="mono strong">{index === 0 ? event : ""}</td>
                    <td>{row.recipient_kind}</td>
                    <td className="dim">{row.group || "—"}</td>
                    <td>
                      <RowForm action={updateRule} id={row.id}>
                        <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
                          <input name="channel_wa" type="checkbox" defaultChecked={row.channel_wa} />
                          WA
                        </label>
                        <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
                          <input
                            name="channel_email"
                            type="checkbox"
                            defaultChecked={row.channel_email}
                          />
                          Email
                        </label>
                        <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
                          <input
                            name="channel_odoo"
                            type="checkbox"
                            defaultChecked={row.channel_odoo}
                          />
                          Odoo
                        </label>
                        <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
                          <input name="active" type="checkbox" defaultChecked={row.active} />
                          aktif
                        </label>
                      </RowForm>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="body">
          <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
            Penerima <code>brand_pic</code> berada di luar tim — ia diresolusi dari kolom PIC
            brand pada vertical, dan biasanya kanal Odoo dimatikan untuknya karena orang itu
            tidak hidup di dalam Odoo. Mematikan semua kanal untuk sebuah kejadian tidak
            menghapus jejaknya: log tetap mencatat bahwa aturan cocok tetapi tidak ada yang
            dikirim.
          </p>
        </div>
      </div>
    </>
  );
}
