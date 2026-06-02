"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useLocale } from "@/store/locale-store";

/**
 * Size-guide modal shown from the PDP. Body measurements in centimetres,
 * mirroring the official Gentlewoman apparel sizing (XS–XL).
 */
const ROWS: { size: string; bust: string; waist: string; hip: string }[] = [
  { size: "XS", bust: "78–82", waist: "60–64", hip: "84–88" },
  { size: "S", bust: "82–86", waist: "64–68", hip: "88–92" },
  { size: "M", bust: "86–90", waist: "68–72", hip: "92–96" },
  { size: "L", bust: "90–95", waist: "72–77", hip: "96–101" },
  { size: "XL", bust: "95–101", waist: "77–83", hip: "101–107" },
];

export function SizeGuide({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useLocale((s) => s.t);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-[60] bg-ink/50 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className="fixed left-1/2 top-1/2 z-[60] w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 bg-bone p-8 shadow-xl"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.25 }}
          >
            <div className="mb-5 flex items-start justify-between">
              <h3 className="font-editorial text-2xl">{t("sizeGuide.title")}</h3>
              <button onClick={onClose} aria-label={t("search.close")} className="text-ink/50 hover:text-accent">
                <X className="h-5 w-5" strokeWidth={1.4} />
              </button>
            </div>
            <p className="mb-6 text-sm leading-relaxed text-ink/60">{t("sizeGuide.intro")}</p>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink/20 text-left text-[11px] uppercase tracking-[0.16em] text-ink/50">
                  <th className="py-2 pr-3 font-medium">{t("sizeGuide.size")}</th>
                  <th className="py-2 pr-3 font-medium">{t("sizeGuide.bust")}</th>
                  <th className="py-2 pr-3 font-medium">{t("sizeGuide.waist")}</th>
                  <th className="py-2 font-medium">{t("sizeGuide.hip")}</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r) => (
                  <tr key={r.size} className="border-b border-ink/10">
                    <td className="py-2.5 pr-3 font-medium">{r.size}</td>
                    <td className="py-2.5 pr-3 text-ink/70">{r.bust}</td>
                    <td className="py-2.5 pr-3 text-ink/70">{r.waist}</td>
                    <td className="py-2.5 text-ink/70">{r.hip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-5 text-[11px] leading-relaxed text-ink/40">{t("sizeGuide.note")}</p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
