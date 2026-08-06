import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { isStaffCookieValid, STAFF_COOKIE } from "@/lib/staff";
import { publicVerticals } from "@/lib/tenants";
import { absolute, BASE_PATH } from "@/lib/url";

import { BrandCompact, BrandPanel } from "./brand";
import SelectForm from "./select-form";

// The tenant list is read per request from a file that ops can edit, and what it
// shows depends on a cookie; caching this page would serve a stale list and,
// worse, risk a shared cache handing the staff view to a client.
export const dynamic = "force-dynamic";

/** The two-panel sheet both the normal and the empty state sit inside. */
function Sheet({ children }: { children: React.ReactNode }) {
  return (
    <main className="wrap">
      <div className="sheet">
        <BrandPanel />
        <section className="form-panel">
          <BrandCompact caption="EAL-Hub" />
          {children}
        </section>
      </div>
    </main>
  );
}

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

  const isStaff = isStaffCookieValid((await cookies()).get(STAFF_COOKIE)?.value);

  // publicVerticals() drops every `db`, and every internal entry unless this is
  // a staff browser, before the config reaches the client component below —
  // whose props are serialised into the HTML.
  const verticals = await publicVerticals(isStaff);

  if (!verticals.length) {
    return (
      <Sheet>
        <p className="alert" role="alert">
          Belum ada environment yang dipublikasikan.
        </p>
      </Sheet>
    );
  }

  return (
    <Sheet>
      <SelectForm verticals={verticals} isStaff={isStaff} />
    </Sheet>
  );
}
