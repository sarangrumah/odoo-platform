"use client";

import { useState } from "react";
import { subscribeNewsletter } from "@/lib/client";
import { useLocale } from "@/store/locale-store";
import type { ContentBlock } from "@/lib/types";

export function Newsletter({ block }: { block: ContentBlock }) {
  const t = useLocale((s) => s.t);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    try {
      await subscribeNewsletter(email);
      setState("done");
      setEmail("");
    } catch {
      setState("error");
    }
  }

  return (
    <section className="bg-ink text-bone">
      <div className="mx-auto max-w-3xl px-6 py-24 text-center">
        {block.eyebrow && <p className="text-[11px] uppercase tracking-[0.24em] text-bone/70">{block.eyebrow}</p>}
        <h2 className="mt-3 font-editorial text-3xl md:text-4xl">{block.headline || "Join the list"}</h2>
        {block.body && <p className="mx-auto mt-4 max-w-md text-sm text-bone/80">{block.body}</p>}

        {state === "done" ? (
          <p className="mt-8 text-sm text-bone">{t("news.success")}</p>
        ) : (
          <form onSubmit={submit} className="mx-auto mt-8 flex max-w-md flex-col gap-3 sm:flex-row">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("news.placeholder")}
              className="flex-1 border border-bone/30 bg-transparent px-4 py-3 text-sm text-bone placeholder:text-bone/40 focus:border-bone focus:outline-none"
            />
            <button
              type="submit"
              disabled={state === "busy"}
              className="bg-bone px-7 py-3 text-xs uppercase tracking-[0.2em] text-ink transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {state === "busy" ? "…" : block.cta_label || "Subscribe"}
            </button>
          </form>
        )}
        {state === "error" && <p className="mt-3 text-sm text-red-300">{t("news.error")}</p>}
      </div>
    </section>
  );
}
