"use client";

import { useEffect, useState } from "react";

const KEY = "gw-cookie-consent";

/**
 * Privacy-preserving cookie consent banner (spec F6). Defaults to no
 * non-essential tracking until the visitor chooses. The choice is stored in
 * localStorage; affiliate/analytics cookies should gate on `accepted`.
 */
export function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(KEY)) setVisible(true);
  }, []);

  function decide(value: "accepted" | "rejected") {
    localStorage.setItem(KEY, value);
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-ink/15 bg-bone/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-5 text-sm md:flex-row md:items-center md:justify-between">
        <p className="max-w-2xl text-ink/70">
          Kami menggunakan cookie untuk fungsi dasar situs dan, dengan izin Anda, untuk
          analitik &amp; personalisasi. Lihat Kebijakan Privasi kami.
        </p>
        <div className="flex shrink-0 gap-3">
          <button
            onClick={() => decide("rejected")}
            className="border border-ink/30 px-5 py-2 text-[11px] uppercase tracking-[0.16em] transition-colors hover:border-ink"
          >
            Hanya esensial
          </button>
          <button
            onClick={() => decide("accepted")}
            className="bg-ink px-5 py-2 text-[11px] uppercase tracking-[0.16em] text-bone transition-opacity hover:opacity-90"
          >
            Terima semua
          </button>
        </div>
      </div>
    </div>
  );
}
