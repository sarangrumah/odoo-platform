import { api } from "@/lib/session";

interface UserRow {
  id: number;
  name: string;
  login: string;
  email: string;
  phone_masked: string;
  has_phone: boolean;
  roles: string[];
  verticals: string[];
  active: boolean;
}

const ROLE_CLASS: Record<string, string> = {
  admin: "acc",
  lead: "acc",
  po: "",
  ba: "",
  member: "",
  brand_pic: "warn",
};

export const dynamic = "force-dynamic";

export default async function UsersPage() {
  const rows = (await api<UserRow[]>("/vaspmo/api/admin/users")) ?? [];
  const noPhone = rows.filter((row) => !row.has_phone && !row.roles.includes("brand_pic")).length;

  return (
    <>
      <div className="card">
        <header>
          <h2>Pengguna &amp; peran</h2>
          <span className="hint">
            {rows.length} akun · {noPhone} tanpa nomor WA
          </span>
        </header>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Nama</th>
                <th>Login</th>
                <th>Email</th>
                <th>Nomor WA</th>
                <th>Peran</th>
                <th>Vertical dipegang</th>
                <th>Aktif</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="dim">
                    Belum ada akun dengan grup VAS PMO.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id} className={row.has_phone ? "" : "sev warn"}>
                    <td className="strong">{row.name}</td>
                    <td className="mono dim">{row.login}</td>
                    <td className="dim">{row.email || "—"}</td>
                    <td className="mono">
                      {row.has_phone ? (
                        row.phone_masked
                      ) : (
                        <span className="pill warn">belum ada</span>
                      )}
                    </td>
                    <td>
                      {row.roles.map((role) => (
                        <span key={role} className={`pill ${ROLE_CLASS[role] ?? ""}`}>
                          {role}
                        </span>
                      ))}
                    </td>
                    <td>
                      {row.verticals.length
                        ? row.verticals.map((code) => (
                            <span key={code} className="vert" style={{ marginRight: 6 }}>
                              <i />
                              {code}
                            </span>
                          ))
                        : <span className="dim">—</span>}
                    </td>
                    <td>{row.active ? "ya" : "tidak"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="body">
          <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
            Nomor ditampilkan ter-mask: daftar ini dibaca banyak admin dan nomornya PII.
            Akun tanpa nomor WA tetap menerima e-mail — kegagalannya tercatat di log kirim
            sebagai <code>no phone number on record</code>, bukan hilang diam-diam. Penambahan
            akun, reset password, dan penetapan peran dilakukan di backend Odoo; layar ini
            sengaja read-only supaya manajemen identitas tidak punya dua pintu.
          </p>
        </div>
      </div>
    </>
  );
}
