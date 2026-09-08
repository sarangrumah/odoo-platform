import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { LoginForm } from "./login-form";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  if (await getSession()) redirect("/ap");

  const raw = (await searchParams).next;
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  const next = candidate?.startsWith("/") && !candidate.startsWith("//") ? candidate : "";

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 20,
        background: "var(--surface-0)",
      }}
    >
      <div className="card" style={{ width: "100%", maxWidth: 380 }}>
        <h1 style={{ margin: "0 0 2px", fontSize: 18, letterSpacing: "-0.01em" }}>
          Levi&apos;s Finance Cockpit
        </h1>
        <p className="sub" style={{ marginBottom: 18 }}>
          Masuk dengan akun Odoo Anda di prd_levis_begbal.
        </p>

        <LoginForm next={next} />

        <p style={{ marginTop: 16, marginBottom: 0, fontSize: 12, color: "var(--text-muted)" }}>
          Kata sandi diperiksa oleh Odoo. Dasbor ini tidak menyimpan kata sandi dan hanya
          membaca data — tidak ada yang bisa diubah dari sini.
        </p>
      </div>
    </div>
  );
}
