import { NextResponse } from "next/server";

import { odooFetch } from "@/lib/odoo";

export const dynamic = "force-dynamic";

/**
 * Container health. Reports the Odoo hop separately: the app being up while its engine is
 * unreachable is a different problem, and hiding it behind one green tick wastes an hour.
 */
export async function GET() {
  const odoo = await odooFetch<{ status: string; db: string }>("/vaspmo/api/health", {
    timeoutMs: 5_000,
  });
  return NextResponse.json(
    {
      status: "up",
      odoo: odoo.ok ? "up" : "unreachable",
      db: odoo.data?.db ?? null,
    },
    { status: 200 },
  );
}
