import { logout } from "@/app/login/actions";

/** Who you are, and the way out. A server action, so logout needs no client JS. */
export function UserMenu({ name }: { name: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{name}</span>
      <form action={logout}>
        <button type="submit" className="btn" title="Keluar">
          Keluar
        </button>
      </form>
    </div>
  );
}
