import { publicVerticals } from "@/lib/tenants";

import SelectForm from "./select-form";

// The tenant list is read per request from a file that ops can edit; caching
// this page would serve a stale list and, worse, keep it in a shared cache.
export const dynamic = "force-dynamic";

export default async function Page() {
  // publicVerticals() drops every `db` before the config reaches the client
  // component below — the props of that component are serialised into the HTML.
  const verticals = await publicVerticals();

  if (!verticals.length) {
    return (
      <main className="login-wrap">
        <div className="card login-card">
          <div className="body">
            <p className="alert">Belum ada environment yang dipublikasikan.</p>
          </div>
        </div>
      </main>
    );
  }

  return <SelectForm verticals={verticals} />;
}
