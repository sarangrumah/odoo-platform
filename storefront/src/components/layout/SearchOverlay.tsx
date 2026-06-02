"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Search, X } from "lucide-react";
import { useLocale } from "@/store/locale-store";

/**
 * Full-width search overlay dropped from the header. Submits to the PLP with a
 * `?q=` query, which the products page reads and feeds to the catalog API's
 * existing `q` (name ilike) filter.
 */
export function SearchOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const t = useLocale((s) => s.t);
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQ("");
      // focus after the open animation kicks in
      const id = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(id);
    }
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    onClose();
    router.push(`/products?q=${encodeURIComponent(term)}`);
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className="fixed left-0 right-0 top-0 z-50 bg-bone"
            initial={{ y: "-100%" }}
            animate={{ y: 0 }}
            exit={{ y: "-100%" }}
            transition={{ type: "tween", duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="mx-auto max-w-3xl px-6 py-10">
              <div className="mb-2 flex items-center justify-between">
                <p className="eyebrow">{t("search.title")}</p>
                <button onClick={onClose} aria-label={t("search.close")} className="text-ink/50 hover:text-accent">
                  <X className="h-5 w-5" strokeWidth={1.4} />
                </button>
              </div>
              <form onSubmit={submit} className="flex items-center gap-4 border-b border-ink/30 py-3">
                <Search className="h-6 w-6 text-ink/50" strokeWidth={1.4} />
                <input
                  ref={inputRef}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={t("search.placeholder")}
                  className="w-full bg-transparent font-editorial text-2xl placeholder:text-ink/30 focus:outline-none md:text-3xl"
                  aria-label={t("search.title")}
                />
              </form>
              <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-ink/35">{t("search.hint")}</p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
