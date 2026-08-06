"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import type { PublicVertical } from "@/lib/tenants";

import { chooseTenant, type ChooseState } from "./actions";

// Note: no import from @/lib/url here. That module pulls in next/headers, which
// cannot be bundled for the client. <Link> prepends basePath by itself, which is
// what the footer link needs anyway.

export default function SelectForm({
  verticals,
  isStaff,
}: {
  verticals: PublicVertical[];
  isStaff: boolean;
}) {
  const [state, formAction, pending] = useActionState<ChooseState, FormData>(chooseTenant, {});
  const [slug, setSlug] = useState(verticals[0]?.slug ?? "");

  const targets = verticals.find((v) => v.slug === slug)?.targets ?? [];

  return (
    <>
      {isStaff ? <span className="staff-badge">Mode staf</span> : null}
      <div>
        <h2>Masuk ke sistem</h2>
        <p className="lede">Pilih unit bisnis dan environment tujuan Anda.</p>
      </div>
      <form action={formAction} className="stackv">
        {state.error ? (
          <p className="alert" role="alert">
            {state.error}
          </p>
        ) : null}
        <div>
          <label htmlFor="vertical">Unit bisnis</label>
          <select
            id="vertical"
            name="vertical"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          >
            {verticals.map((v) => (
              <option key={v.slug} value={v.slug}>
                {v.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="environment">Environment</label>
          {/* Remount on vertical change so the browser never keeps a code
              from the previous vertical selected. */}
          <select key={slug} id="environment" name="environment" required>
            {targets.map((t) => (
              <option key={t.code} value={t.code}>
                {/* The marker only ever renders in staff mode — a client's
                    list contains no internal entries to mark. */}
                {t.internal ? `${t.label} · internal` : t.label}
              </option>
            ))}
          </select>
        </div>
        <button className="btn pri" type="submit" disabled={pending || !targets.length}>
          {pending ? "Menyiapkan…" : "Lanjut ke login"}
        </button>
        <p className="hint">Email dan password diisi di halaman login Odoo berikutnya.</p>
      </form>
      {/* The release history, the module inventory and the exact version are a
          staff view. A client at the login form gets neither the numbers nor a
          link telling them the page exists -- and the page itself 404s for them. */}
      {isStaff ? (
        <div className="panel-foot">
          <span>Odoo Community 19.0</span>
          <Link href="/versi">Versi &amp; riwayat rilis</Link>
        </div>
      ) : null}
    </>
  );
}
