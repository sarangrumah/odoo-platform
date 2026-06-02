"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { imageUrl } from "@/lib/client";

/**
 * Full-screen image viewer for the PDP gallery. Open from a thumbnail/main
 * image; arrow keys and on-screen chevrons move through `images`.
 */
export function ImageLightbox({
  images,
  index,
  open,
  alt,
  onClose,
  onIndexChange,
}: {
  images: string[];
  index: number;
  open: boolean;
  alt: string;
  onClose: () => void;
  onIndexChange: (i: number) => void;
}) {
  const prev = () => onIndexChange((index - 1 + images.length) % images.length);
  const next = () => onIndexChange((index + 1) % images.length);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    }
    if (open) {
      window.addEventListener("keydown", onKey);
      document.body.style.overflow = "hidden";
    }
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, index, images.length]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/95"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute right-5 top-5 z-10 text-bone/70 hover:text-bone"
          >
            <X className="h-7 w-7" strokeWidth={1.3} />
          </button>

          {images.length > 1 && (
            <>
              <button
                onClick={(e) => { e.stopPropagation(); prev(); }}
                aria-label="Previous"
                className="absolute left-3 z-10 p-3 text-bone/60 hover:text-bone md:left-8"
              >
                <ChevronLeft className="h-9 w-9" strokeWidth={1.2} />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); next(); }}
                aria-label="Next"
                className="absolute right-3 z-10 p-3 text-bone/60 hover:text-bone md:right-8"
              >
                <ChevronRight className="h-9 w-9" strokeWidth={1.2} />
              </button>
            </>
          )}

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <motion.img
            key={index}
            src={imageUrl(images[index])}
            alt={alt}
            className="max-h-[88vh] max-w-[92vw] object-contain"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.25 }}
            onClick={(e) => e.stopPropagation()}
          />

          {images.length > 1 && (
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 text-[11px] uppercase tracking-[0.2em] text-bone/60">
              {index + 1} / {images.length}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
