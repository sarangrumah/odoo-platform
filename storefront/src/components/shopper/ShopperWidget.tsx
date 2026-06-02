"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useLocale } from "@/store/locale-store";
import { ProductCard } from "@/components/product/ProductCard";
import type { ShopperMessage, ShopperResponse } from "@/lib/types";

const WHATSAPP = process.env.NEXT_PUBLIC_SOCIAL_WHATSAPP || "";

/**
 * AI personal shopper — floating launcher + chat panel.
 *
 * Talks to the BFF at /api/shopper, which forwards to the local-Ollama gateway.
 * Conversation history lives client-side (MVP, no server memory); we send the
 * recent turns each request. Product cards are rendered from the REAL catalog
 * items the gateway returns (grounding guard runs server-side).
 */
export function ShopperWidget() {
  const t = useLocale((s) => s.t);
  const locale = useLocale((s) => s.locale);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ShopperMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [escalate, setEscalate] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Seed the greeting the first time the panel opens.
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{ role: "assistant", content: t("shopper.greeting") }]);
    }
  }, [open, messages.length, t]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setEscalate(false);
    const next: ShopperMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setLoading(true);
    try {
      const res = await fetch("/api/shopper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // send only role + content (drop product payloads from history)
          messages: next.map((m) => ({ role: m.role, content: m.content })),
          locale,
        }),
      });
      const data = (await res.json()) as ShopperResponse;
      if (!res.ok || typeof data.reply !== "string") throw new Error("bad response");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, products: data.products || [] },
      ]);
      setEscalate(Boolean(data.escalate));
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: t("shopper.error") }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Launcher */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={t("shopper.launcher")}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-ink text-bone shadow-lg transition-transform hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent md:bottom-8 md:right-8"
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="fixed bottom-24 right-3 z-40 flex max-h-[70vh] w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl border border-ink/10 bg-bone shadow-2xl sm:right-5 sm:w-[400px] md:bottom-28 md:right-8"
          >
            {/* Header */}
            <div className="flex items-start justify-between border-b border-ink/10 bg-sand px-4 py-3">
              <div>
                <p className="font-editorial text-sm tracking-widest text-ink">{t("shopper.title")}</p>
                <p className="mt-0.5 text-xs text-ink/55">{t("shopper.subtitle")}</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label={t("shopper.close")}
                className="text-ink/40 transition-colors hover:text-ink"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
              {messages.map((m, i) => (
                <div key={i}>
                  <div className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                    <div
                      className={
                        m.role === "user"
                          ? "max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-3.5 py-2 text-sm text-bone"
                          : "max-w-[85%] rounded-2xl rounded-bl-sm bg-white px-3.5 py-2 text-sm text-ink/90 shadow-sm"
                      }
                    >
                      {m.content}
                    </div>
                  </div>
                  {m.products && m.products.length > 0 ? (
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      {m.products.slice(0, 4).map((p, idx) => (
                        <ProductCard key={p.id} product={p} index={idx} />
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}

              {loading ? (
                <div className="flex justify-start">
                  <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm bg-white px-3.5 py-3 shadow-sm">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink/40 [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink/40 [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink/40" />
                    <span className="ml-2 text-xs text-ink/50">{t("shopper.thinking")}</span>
                  </div>
                </div>
              ) : null}

              {escalate && WHATSAPP ? (
                <a
                  href={WHATSAPP}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-xl border border-ink/15 bg-white px-3.5 py-2.5 text-center text-sm text-ink transition-colors hover:bg-sand"
                >
                  {t("shopper.human")}
                </a>
              ) : null}
            </div>

            {/* Composer */}
            <div className="border-t border-ink/10 bg-bone px-3 py-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  rows={1}
                  placeholder={t("shopper.placeholder")}
                  className="max-h-28 flex-1 resize-none rounded-xl border border-ink/15 bg-white px-3 py-2 text-sm text-ink placeholder:text-ink/35 focus:border-ink/30 focus:outline-none"
                />
                <button
                  onClick={send}
                  disabled={loading || !input.trim()}
                  className="flex h-9 items-center justify-center rounded-xl bg-ink px-4 text-sm text-bone transition-opacity disabled:opacity-40"
                >
                  {t("shopper.send")}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
