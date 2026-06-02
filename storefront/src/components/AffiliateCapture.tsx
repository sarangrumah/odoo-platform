"use client";

import { useEffect } from "react";
import { captureAffiliate } from "@/lib/affiliate";

/** Invisible: on every load, capture `?aff=CODE` into the attribution cookie. */
export function AffiliateCapture() {
  useEffect(() => {
    captureAffiliate();
  }, []);
  return null;
}
