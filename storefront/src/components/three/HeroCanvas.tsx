"use client";

import dynamic from "next/dynamic";

// ssr:false is only permitted inside a Client Component — this thin wrapper
// lets the server-rendered home page embed the 3D hero safely.
const HeroScene = dynamic(() => import("./HeroScene"), { ssr: false });

export function HeroCanvas() {
  return <HeroScene />;
}
