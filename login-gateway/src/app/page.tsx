import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { STAFF_COOKIE } from "@/lib/staff";
import { publicVerticals } from "@/lib/tenants";
import { absolute, BASE_PATH } from "@/lib/url";

import SelectForm from "./select-form";

// The tenant list is read per request from a file that ops can edit, and what it
// shows depends on a cookie; caching this page would serve a stale list and,
// worse, risk a shared cache handing the staff view to a client.
export const dynamic = "force-dynamic";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = (await searchParams).staff;
  if (typeof raw === "string") {
    // `/signin?staff=<key>` is the documented entry point; the validation and
    // the cookie live in the route handler, which then bounces back here with a
    // clean URL. Absolute, so basePath is not prepended a second time.
    redirect(await absolute(`${BASE_PATH}/staff?key=${encodeURIComponent(raw)}`));
  }

  const isStaff = (await cookies()).get(STAFF_COOKIE)?.value === "1";

  // publicVerticals() drops every `db`, and every internal entry unless this is
  // a staff browser, before the config reaches the client component below —
  // whose props are serialised into the HTML.
  const verticals = await publicVerticals(isStaff);

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

  return <SelectForm verticals={verticals} isStaff={isStaff} />;
}
