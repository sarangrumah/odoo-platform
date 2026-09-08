"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Mascot, type MascotState } from "@/components/agent/mascot";

/** Mirrors the API response; kept structural so the two can evolve apart. */
interface AnswerPayload {
  source?: string;
  headline?: string;
  table?: { columns: string[]; rows: (string | number)[][] };
  href?: string;
  note?: string;
  suggestions?: string[];
}

interface Turn {
  role: "user" | "assistant";
  text: string;
  table?: AnswerPayload["table"];
  href?: string;
  note?: string;
  suggestions?: string[];
}

const GREETING =
  "Halo. Saya membaca buku besar, rekening koran dan kliring POS di prd_levis_begbal. " +
  "Setiap jawaban saya menyebut tanggal potongnya.";

const OPENING_CHIPS = [
  "Berapa hutang yang lewat jatuh tempo?",
  "Apa yang perlu saya kerjakan hari ini?",
  "Apakah buku bisa ditutup?",
];

/**
 * The app is mounted under basePath "/finance", which next/link prefixes for us
 * but fetch() does not. usePathname() reports the path WITHOUT the basePath, so
 * the difference against location.pathname is the prefix — more reliable than a
 * relative URL, which would break the moment a page gains a trailing slash.
 */
function useApiBase(): string {
  const pathname = usePathname();
  if (typeof window === "undefined") return "";
  const full = window.location.pathname;
  return full.endsWith(pathname) ? full.slice(0, full.length - pathname.length) : "";
}

export function AgentWidget() {
  const params = useSearchParams();
  const apiBase = useApiBase();
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);

  const state: MascotState = busy ? "thinking" : open ? "listening" : "idle";

  useEffect(() => {
    if (open && turns.length === 0) {
      setTurns([{ role: "assistant", text: GREETING, suggestions: OPENING_CHIPS }]);
    }
    if (open) field.current?.focus();
  }, [open, turns.length]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  // Escape closes the panel, the way every other overlay on the web does.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;

    setInput("");
    setTurns((prev) => [...prev, { role: "user", text }]);
    setBusy(true);

    try {
      const res = await fetch(`${apiBase}/api/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // The filter bar IS the reader's context: send the cut-off so a question
        // with no period in it answers about the date already on screen, rather
        // than quietly about today.
        body: JSON.stringify({ question: text, asOf: params.get("asOf") ?? undefined }),
      });

      if (res.status === 401) {
        setTurns((prev) => [
          ...prev,
          { role: "assistant", text: "Sesi Anda sudah berakhir. Muat ulang halaman untuk masuk lagi." },
        ]);
        return;
      }

      const data = (await res.json()) as AnswerPayload;
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.headline ?? "Maaf, jawabannya tidak terbaca.",
          table: data.table,
          href: data.href,
          note: data.note,
          suggestions: data.suggestions,
        },
      ]);
    } catch {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: "Gagal menghubungi server. Coba lagi sebentar lagi." },
      ]);
    } finally {
      setBusy(false);
      field.current?.focus();
    }
  }

  return (
    <>
      <button
        type="button"
        className="agent-launcher"
        aria-expanded={open}
        aria-label={open ? "Tutup asisten" : "Buka asisten"}
        onClick={() => setOpen((v) => !v)}
      >
        <Mascot state={state} size={48} />
      </button>

      {open && (
        <section className="agent-panel" role="dialog" aria-label="Asisten finance">
          <header className="agent-head">
            <Mascot state={state} size={32} />
            <div>
              <strong>Asisten Finance</strong>
              <span>buku besar prd_levis_begbal</span>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Tutup">
              ✕
            </button>
          </header>

          <div className="agent-log" ref={scroller}>
            {turns.map((turn, i) => (
              <article key={i} className={`agent-turn agent-turn-${turn.role}`}>
                <p>{turn.text}</p>

                {turn.table && (
                  <div className="agent-table-wrap">
                    <table className="agent-table">
                      <thead>
                        <tr>
                          {turn.table.columns.map((c) => (
                            <th key={c}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {turn.table.rows.map((row, r) => (
                          <tr key={r}>
                            {row.map((cell, c) => (
                              <td key={c}>{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {turn.note && <p className="agent-note">{turn.note}</p>}

                {turn.href && (
                  <Link className="agent-link" href={turn.href} onClick={() => setOpen(false)}>
                    Buka di dashboard →
                  </Link>
                )}

                {turn.suggestions && (
                  <div className="agent-chips">
                    {turn.suggestions.map((s) => (
                      <button key={s} type="button" onClick={() => ask(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}

            {busy && (
              <article className="agent-turn agent-turn-assistant">
                <p className="agent-thinking">Sedang menghitung…</p>
              </article>
            )}
          </div>

          <form
            className="agent-form"
            onSubmit={(e) => {
              e.preventDefault();
              void ask(input);
            }}
          >
            <input
              ref={field}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Tanya posisi, umur, atau kesiapan tutup buku…"
              maxLength={500}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !input.trim()}>
              Kirim
            </button>
          </form>
        </section>
      )}
    </>
  );
}
