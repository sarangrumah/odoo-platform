"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { fetchContent } from "@/lib/client";
import { useLocale } from "@/store/locale-store";
import { useUI } from "@/store/ui-store";
import type { ContentBlock } from "@/lib/types";

const DISMISS_KEY = "gw-announce-dismissed";

/** Thin CMS-driven announcement bar fixed above the header (height h-9 = 36px). */
export function AnnouncementBar() {
  const locale = useLocale((s) => s.locale);
  const setAnnouncement = useUI((s) => s.setAnnouncement);
  const [block, setBlock] = useState<ContentBlock | null>(null);
  const [dismissed, setDismissed] = useState(true); // assume dismissed until checked (no flash)

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_KEY) === "1");
  }, []);

  useEffect(() => {
    fetchContent().then((c) => setBlock(c.announcement ?? null)).catch(() => setBlock(null));
  }, [locale]);

  const visible = !!(block && block.headline && !dismissed);

  useEffect(() => {
    setAnnouncement(visible);
    return () => setAnnouncement(false);
  }, [visible, setAnnouncement]);

  if (!visible || !block) return null;

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  return (
    <div className="fixed inset-x-0 top-0 z-50 flex h-9 items-center justify-center gap-3 bg-ink px-10 text-center text-[11px] uppercase tracking-[0.18em] text-bone">
      <span>
        {block.headline}
        {block.cta_label && (
          <Link href={block.cta_url || "/products"} className="ml-3 underline underline-offset-2 hover:text-bone/70">
            {block.cta_label}
          </Link>
        )}
      </span>
      <button onClick={dismiss} aria-label="Dismiss" className="absolute right-3 text-bone/70 hover:text-bone">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
