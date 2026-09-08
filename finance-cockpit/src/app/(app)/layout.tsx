import { Suspense } from "react";
import { redirect } from "next/navigation";

import { AgentWidget } from "@/components/agent/agent-widget";
import { FilterBar } from "@/components/filter-bar";
import { Nav } from "@/components/nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { getSession } from "@/lib/auth";
import { today } from "@/lib/finance-filters";
import { companies } from "@/lib/queries/common";
import { lastPostedDate } from "@/lib/queries/meta";

// The filter presets read the company's lock dates and the ledger's extent,
// neither of which varies with the filters themselves.
export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // The real gate. Middleware only checks that a cookie is present; here the
  // signature and expiry are verified, and no page renders without a session.
  const session = await getSession();
  if (!session) redirect("/login");

  const [list, lastPosted] = await Promise.all([companies(), lastPostedDate()]);
  const company = list[0];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          Levi&apos;s Finance Cockpit<span>prd_levis_begbal</span>
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
        <FilterBar
          options={{
            fiscalyearLockDate: company?.fiscalyearLockDate ?? null,
            lastPostedDate: lastPosted,
            today: today(),
          }}
        />
      </Suspense>

      <main className="main">{children}</main>

      {/* Rides on every page. Reads the cut-off through useSearchParams, so it
          needs the same Suspense boundary the filter bar gets. */}
      <Suspense fallback={null}>
        <AgentWidget />
      </Suspense>
    </div>
  );
}
