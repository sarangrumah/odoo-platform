import Link from "next/link";
import { redirect } from "next/navigation";

import CommandPalette from "@/components/command-palette";
import { getSessionUser } from "@/lib/session";

const NAV = [
  {
    group: "Monitor",
    items: [
      { href: "/portfolio", label: "Portfolio" },
      { href: "/board", label: "Board" },
      { href: "/weekly", label: "Weekly" },
      { href: "/timeline", label: "Timeline" },
    ],
  },
  {
    group: "Pekerjaan",
    items: [{ href: "/cr", label: "Change Request" }],
  },
  {
    group: "Sistem",
    items: [
      { href: "/logs", label: "Log transaksi" },
      { href: "/settings/verticals", label: "Pengaturan", adminOnly: true },
    ],
  },
];

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  const isAdmin = user.roles.includes("admin");

  return (
    <div className="shell">
      <nav className="rail">
        <div className="brand">
          <b>VAS PMO</b>
          <span>Product Owner · VAS</span>
        </div>

        <CommandPalette />

        {NAV.map((section) => {
          const items = section.items.filter((item) => !item.adminOnly || isAdmin);
          if (items.length === 0) return null;
          return (
            <div className="rail-group" key={section.group}>
              <div className="rail-label">{section.group}</div>
              {items.map((item) => (
                <Link className="navlink" href={item.href} key={item.href}>
                  {item.label}
                </Link>
              ))}
            </div>
          );
        })}

        <div className="rail-foot">
          <div>
            <b style={{ fontSize: 12.5 }}>{user.name}</b>
            <div className="eyebrow">{user.roles.join(" · ") || "member"}</div>
          </div>
          <div className="rail-note">
            {user.verticals.length
              ? `vertical: ${user.verticals.map((v) => v.code).join(", ")}`
              : "vertical: semua"}
            <br />
            Next.js · engine Odoo 19
          </div>
        </div>
      </nav>
      <div className="main">{children}</div>
    </div>
  );
}
