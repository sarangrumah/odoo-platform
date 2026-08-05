"use client";

import { useActionState, useState } from "react";

import type { PublicVertical } from "@/lib/tenants";

import { chooseTenant, type ChooseState } from "./actions";

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
    <main className="login-wrap">
      <div className="card login-card">
        <header>
          <div>
            <h2>Erajaya Odoo</h2>
            <span className="eyebrow">{isStaff ? "Pilih tujuan · mode staf" : "Pilih tujuan"}</span>
          </div>
        </header>
        <form action={formAction} className="body stackv">
          {state.error ? <p className="alert">{state.error}</p> : null}
          <div>
            <label htmlFor="vertical">Vertical</label>
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
          <p className="dim" style={{ fontSize: 12, margin: 0 }}>
            Email dan password diisi di halaman login Odoo berikutnya.
          </p>
        </form>
      </div>
    </main>
  );
}
