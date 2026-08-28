import { Suspense } from "react";
import { redirect } from "next/navigation";
import { AgentWidget } from "@/components/agent/agent-widget";
import { Nav } from "@/components/nav";
import { FilterBar } from "@/components/filter-bar";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { getSession } from "@/lib/auth";
import { dataExtent, filterOptions } from "@/lib/queries/sales";

// The filter pickers list every store and category, not just those in scope,
// so this is fetched once per request and never varies with the filters.
export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // The real gate. Middleware only checks that a cookie is present; here the
  // signature and expiry are verified, and no page renders without a session.
  const session = await getSession();
  if (!session) redirect("/login");

  const [options, extent] = await Promise.all([filterOptions(), dataExtent()]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          Levi&apos;s Sales Cockpit<span>prd_levis_begbal</span>
        </div>
        <Suspense fallback={<div className="nav" />}>
          <Nav />
        </Suspense>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <ThemeToggle />
          <UserMenu name={session.name} />
        </div>
      </header>

      <Suspense fallback={<div className="filters" style={{ height: 56 }} />}>
        <FilterBar options={options} extent={extent} />
      </Suspense>

      <main className="main">{children}</main>

      {/* Rides on every page. Reads the filter bar through useSearchParams, so
          it needs the same Suspense boundary the other client components get. */}
      <Suspense fallback={null}>
        <AgentWidget />
      </Suspense>
    </div>
  );
}
