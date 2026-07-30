import Link from "next/link";
import { redirect } from "next/navigation";

import { getSessionUser } from "@/lib/session";

const TABS = [
  { href: "/settings/verticals", label: "Vertical / brand" },
  { href: "/settings/stages", label: "Stage & jam SLA" },
  { href: "/settings/rules", label: "Aturan notifikasi" },
  { href: "/settings/users", label: "Pengguna & peran" },
];

export default async function SettingsLayout({ children }: { children: React.ReactNode }) {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  // The API refuses non-admins anyway; this keeps a non-admin from staring at four
  // screens of permission errors.
  if (!user.roles.includes("admin")) redirect("/portfolio");

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Pengaturan</h1>
          <div className="sub">
            master data · apa pun yang bisa berubah tanpa deploy ada di sini
          </div>
        </div>
        <div className="seg" style={{ marginLeft: "auto" }}>
          {TABS.map((tab) => (
            <Link key={tab.href} href={tab.href}>
              {tab.label}
            </Link>
          ))}
        </div>
      </header>
      <div className="content">{children}</div>
    </>
  );
}
