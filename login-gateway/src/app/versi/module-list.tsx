"use client";

import { useMemo, useState } from "react";

import type { Bucket, PublicModule } from "@/lib/versions";

/**
 * The module table: search, bucket filter, and a per-module drawer holding the
 * commits that touched it.
 *
 * Filtering is done over the array already in props — the whole document is a
 * few hundred kB and arrives with the page, so there is nothing to fetch and
 * no loading state to design.
 */
export default function ModuleList({
  buckets,
  modules,
  hidden,
}: {
  buckets: Bucket[];
  modules: PublicModule[];
  hidden: number;
}) {
  const [q, setQ] = useState("");
  const [bucket, setBucket] = useState("");

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return modules.filter((m) => {
      if (bucket && m.bucket !== bucket) return false;
      if (!needle) return true;
      return (
        m.module.toLowerCase().includes(needle) ||
        m.name.toLowerCase().includes(needle) ||
        m.summary.toLowerCase().includes(needle) ||
        m.version.includes(needle)
      );
    });
  }, [modules, q, bucket]);

  const groups = buckets
    .map((b) => ({ bucket: b, rows: shown.filter((m) => m.bucket === b.key) }))
    .filter((g) => g.rows.length > 0);

  return (
    <section className="card">
      <header>
        <h2>Modul kustom</h2>
        <span className="eyebrow">
          {shown.length} dari {modules.length}
        </span>
      </header>

      <div className="body">
        <div className="toolbar">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Cari modul, fitur, atau versi…"
            aria-label="Cari modul"
          />
          <select
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
            aria-label="Saring per kelompok"
          >
            <option value="">Semua kelompok</option>
            {buckets.map((b) => (
              <option key={b.key} value={b.key}>
                {b.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {groups.length === 0 ? (
        <p className="note">Tidak ada modul yang cocok dengan pencarian itu.</p>
      ) : null}

      {groups.map(({ bucket: b, rows }) => (
        <div className="bucket" key={b.key}>
          <div className="bucket-head" style={{ padding: "14px 16px 6px" }}>
            <h3>{b.label}</h3>
            <span className="count">{rows.length}</span>
          </div>
          {b.note ? (
            <p className="hint" style={{ padding: "0 16px 8px" }}>
              {b.note}
            </p>
          ) : null}
          {rows.map((m) => (
            <details className="mod" key={`${m.bucket}/${m.module}`}>
              <summary>
                <span className="mod-head">
                  <span className="mod-name">{m.name}</span>
                  <span className="mod-tech">{m.module}</span>
                </span>
                <span className="mod-ver">{m.version}</span>
                {m.summary ? <span className="mod-sum">{m.summary}</span> : null}
              </summary>
              <ul className="changes">
                {m.changes.length ? (
                  m.changes.map((c) => (
                    <li key={c.sha}>
                      <span className="when">{c.date}</span>
                      <span className="what">
                        {c.subject} <span className="sha">{c.sha}</span>
                      </span>
                    </li>
                  ))
                ) : m.change_count ? (
                  // Subjects are staff-only; see publicVersions() in
                  // lib/versions.ts for why.
                  <li className="none">
                    {m.change_count} perubahan tercatat, terakhir{" "}
                    {m.last_change || "tidak diketahui"}. Rincian riwayat hanya untuk staf.
                  </li>
                ) : (
                  <li className="none">Belum ada riwayat perubahan yang tercatat.</li>
                )}
              </ul>
            </details>
          ))}
        </div>
      ))}

      {hidden > 0 ? (
        <p className="note">
          {hidden} modul khusus tenant disembunyikan dari daftar publik karena namanya menyebut
          klien, dan rincian riwayat perubahan diringkas dengan alasan yang sama. Buka dengan
          tautan staf untuk melihat keduanya secara utuh.
        </p>
      ) : null}
    </section>
  );
}
