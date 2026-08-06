import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { isStaffCookieValid, STAFF_COOKIE } from "@/lib/staff";
import { publicVersions } from "@/lib/versions";

import { BrandCompact } from "../brand";
import OdooMark from "../odoo-mark";
import ModuleList from "./module-list";

// versions.json is bind-mounted and regenerated out of band, and what it shows
// depends on the staff cookie. Same reasoning as the chooser: never cache.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "EAL-Hub — Versi & riwayat rilis",
  description: "Versi Odoo Community dan seluruh modul kustom yang berjalan di EAL-Hub",
};

function fmt(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short", timeZone: "Asia/Jakarta" });
}

export default async function VersiPage() {
  const isStaff = isStaffCookieValid((await cookies()).get(STAFF_COOKIE)?.value);
  // Staff only, and 404 rather than 403: an anonymous visitor should not learn
  // that this page exists. Even its "public" rendering was an inventory -- the
  // platform branch and commit, the base image digest, the runtime versions, and
  // all 139 custom modules by technical name, version and date of last change.
  // That is a target list, and it sat one click below the login form.
  if (!isStaff) notFound();

  const { platform, buckets, modules, hidden, generated_at } = await publicVersions(isStaff);

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <BrandCompact className="page-head-logo" />
          <h1>Versi &amp; riwayat rilis</h1>
        </div>
        <Link href="/" className="btn">
          ← Kembali ke login
        </Link>
      </div>

      <section className="card">
        <header>
          <h2>Platform</h2>
          <span className="eyebrow">
            {platform.branch}
            {platform.commit ? ` · ${platform.commit}` : ""}
          </span>
        </header>
        <dl className="facts">
          <div className="fact">
            <dt>Aplikasi</dt>
            <dd>
              <OdooMark className="odoo-mark" /> {platform.odoo.version}
              <span className="sub">{platform.odoo.edition} Edition</span>
            </dd>
          </div>
          <div className="fact">
            <dt>Modul kustom</dt>
            <dd>
              {modules.length}
              <span className="sub">{buckets.length} kelompok</span>
            </dd>
          </div>
          <div className="fact">
            <dt>PostgreSQL</dt>
            <dd>{platform.postgres || "—"}</dd>
          </div>
          <div className="fact">
            <dt>Python</dt>
            <dd>{platform.python || "—"}</dd>
          </div>
          <div className="fact">
            <dt>Data per</dt>
            <dd>
              <span style={{ fontSize: 13 }}>{fmt(generated_at)}</span>
              <span className="sub">WIB</span>
            </dd>
          </div>
        </dl>
        {platform.odoo.digest ? (
          <p className="note">
            Image dasar dipatok ke digest <code>{platform.odoo.digest}</code> — tag{" "}
            <code>odoo:{platform.odoo.version}</code> yang bergulir tidak bisa berganti diam-diam di
            bawah database yang sedang berjalan.
          </p>
        ) : null}
      </section>

      <ModuleList buckets={buckets} modules={modules} hidden={hidden} />
    </main>
  );
}
