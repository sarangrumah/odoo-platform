"use client";

import { useUI } from "@/store/ui-store";

/** Wraps page content; adds top padding for the fixed header (+ announcement bar). */
export function MainShell({ children }: { children: React.ReactNode }) {
  const announcement = useUI((s) => s.announcement);
  return <main className={announcement ? "pt-[7.25rem]" : "pt-20"}>{children}</main>;
}
