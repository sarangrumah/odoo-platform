import { api } from "@/lib/session";

import { updateVertical } from "../actions";
import RowForm from "../row-form";

interface Vertical {
  id: number;
  code: string;
  name: string;
  legal_entity: string;
  brand_group: string;
  vertical_po: { id: number; name: string } | null;
  ba: Array<{ id: number; name: string }>;
  pic: Array<{ id: number; name: string }>;
  sequence: number;
  active: boolean;
  project_count: number;
  task_count: number;
}

export const dynamic = "force-dynamic";

export default async function VerticalsPage() {
  const rows = (await api<Vertical[]>("/vaspmo/api/admin/verticals")) ?? [];
  const pending = rows.filter((row) => !row.legal_entity).length;

  return (
    <div className="card">
      <header>
        <h2>Vertical / brand</h2>
        <span className="hint">
          {rows.length} brand · {pending} badan hukum belum dikonfirmasi
        </span>
      </header>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Brand</th>
              <th>Grup</th>
              <th>PO</th>
              <th>BA</th>
              <th>PIC brand</th>
              <th className="num">Project</th>
              <th className="num">Task</th>
              <th style={{ minWidth: 420 }}>Badan hukum · urutan · aktif</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className={row.legal_entity ? "" : "sev warn"}>
                <td>
                  <span className="vert">
                    <i />
                    {row.code}
                  </span>
                </td>
                <td className="strong">{row.name}</td>
                <td className="dim">{row.brand_group}</td>
                <td className="dim">{row.vertical_po?.name ?? "—"}</td>
                <td className="dim">{row.ba.map((u) => u.name).join(", ") || "—"}</td>
                <td className="dim">{row.pic.map((p) => p.name).join(", ") || "—"}</td>
                <td className="num">{row.project_count}</td>
                <td className="num">{row.task_count}</td>
                <td>
                  <RowForm action={updateVertical} id={row.id}>
                    <input
                      name="legal_entity"
                      type="text"
                      defaultValue={row.legal_entity}
                      placeholder="kosongkan bila belum dikonfirmasi"
                      style={{ width: 230 }}
                    />
                    <input
                      name="sequence"
                      type="text"
                      defaultValue={String(row.sequence)}
                      style={{ width: 60 }}
                      aria-label="urutan"
                    />
                    <label
                      style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}
                    >
                      <input name="active" type="checkbox" defaultChecked={row.active} />
                      aktif
                    </label>
                  </RowForm>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="body" style={{ borderTop: "1px solid var(--line-soft)" }}>
        <p className="dim" style={{ margin: 0, fontSize: 12 }}>
          Kolom badan hukum yang kosong dibiarkan kosong dengan sengaja — sel kosong itu
          jujur, nama PT yang ditebak akan pelan-pelan dianggap data.
        </p>
      </div>
    </div>
  );
}
