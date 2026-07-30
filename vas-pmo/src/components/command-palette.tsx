"use client";

// =============================================================================
// Command palette (Ctrl/Cmd+K) — the Linear pattern.
//
// Two kinds of row, in one list: static destinations (always there, filtered locally) and
// live records from Odoo (debounced, fetched through /api/search). Keyboard first: the
// mouse is optional throughout.
// =============================================================================

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface Row {
  icon: string;
  label: string;
  hint: string;
  url: string;
}

const DESTINATIONS: Row[] = [
  { icon: "→", label: "Portfolio", hint: "G P", url: "/portfolio" },
  { icon: "→", label: "Board", hint: "G B", url: "/board" },
  { icon: "→", label: "Weekly Progress", hint: "G W", url: "/weekly" },
  { icon: "→", label: "Change Request", hint: "G C", url: "/cr" },
  { icon: "→", label: "Timeline", hint: "G L", url: "/timeline" },
  { icon: "→", label: "Log transaksi", hint: "G G", url: "/logs" },
  { icon: "→", label: "Pengaturan — Vertical & brand", hint: "G S", url: "/settings/verticals" },
  { icon: "→", label: "Pengaturan — Stage & jam SLA", hint: "", url: "/settings/stages" },
  { icon: "→", label: "Pengaturan — Aturan notifikasi", hint: "", url: "/settings/rules" },
  { icon: "→", label: "Pengaturan — Pengguna & peran", hint: "", url: "/settings/users" },
];

const TYPE_ICON: Record<string, string> = { task: "#", cr: "±", project: "▣" };

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [remote, setRemote] = useState<Row[]>([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const local = DESTINATIONS.filter((row) =>
    (row.label + row.hint).toLowerCase().includes(term.toLowerCase()),
  );
  const rows = [...local, ...remote];

  // Debounced remote search. An in-flight request is abandoned when the term moves on, so
  // a slow response cannot overwrite a newer one.
  useEffect(() => {
    if (!open) return;
    const query = term.trim();
    if (query.length < 2) {
      setRemote([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as {
          results?: Array<{ type: string; label: string; hint: string; stage: string; url: string }>;
        };
        setRemote(
          (data.results ?? []).map((hit) => ({
            icon: TYPE_ICON[hit.type] ?? "•",
            label: hit.label,
            hint: [hit.hint, hit.stage].filter(Boolean).join(" · "),
            url: hit.url,
          })),
        );
      } catch {
        setRemote([]);
      }
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [term, open]);

  const close = useCallback(() => {
    setOpen(false);
    setTerm("");
    setRemote([]);
    setSelected(0);
  }, []);

  const run = useCallback(
    (row: Row | undefined) => {
      if (!row) return;
      close();
      router.push(row.url);
    },
    [close, router],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
        return;
      }
      if (!open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((value) => Math.min(value + 1, rows.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((value) => Math.max(value - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        run(rows[selected]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, rows, selected, close, run]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  return (
    <>
      <button className="kbd-hint" onClick={() => setOpen(true)} type="button">
        <span style={{ flex: "1 1 auto" }}>Cari atau buka…</span>
        <kbd>Ctrl</kbd>
        <kbd>K</kbd>
      </button>

      {open ? (
        <div
          className="scrim on"
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
          onClick={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <div className="palette">
            <input
              ref={inputRef}
              type="text"
              value={term}
              placeholder="Cari task, change request, project — atau buka layar…"
              autoComplete="off"
              onChange={(event) => {
                setTerm(event.target.value);
                setSelected(0);
              }}
            />
            <ul>
              {rows.length === 0 ? (
                <li className="empty">
                  Tidak ada yang cocok. Coba nama task, nomor CR, atau kode vertical.
                </li>
              ) : (
                rows.map((row, index) => (
                  <li
                    key={`${row.url}-${row.label}-${index}`}
                    data-sel={index === selected}
                    onMouseEnter={() => setSelected(index)}
                    onClick={() => run(row)}
                  >
                    <span className="ic">{row.icon}</span>
                    <span>{row.label}</span>
                    <span className="k">{row.hint}</span>
                  </li>
                ))
              )}
            </ul>
            <div className="pfoot">
              <span>↑↓ pilih</span>
              <span>⏎ buka</span>
              <span>esc tutup</span>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
