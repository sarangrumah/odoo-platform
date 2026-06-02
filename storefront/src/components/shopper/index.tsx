"use client";

import dynamic from "next/dynamic";

/**
 * Client-only mount for the personal shopper. Lazy-loaded (ssr:false) so the
 * chat widget + framer-motion never weigh on the initial server render; it
 * hydrates after the page is interactive.
 */
export const ShopperWidget = dynamic(
  () => import("./ShopperWidget").then((m) => m.ShopperWidget),
  { ssr: false },
);
