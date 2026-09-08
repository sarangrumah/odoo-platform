import { NextResponse } from "next/server";
import { q } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * Liveness plus a real round-trip to Postgres — a cockpit that cannot read is
 * down. This is the one route the middleware leaves open, because the
 * container's own healthcheck calls it unauthenticated, so it reports no
 * business figures: `SELECT 1`, not a row count.
 */
export async function GET() {
  const started = performance.now();
  try {
    await q(`SELECT 1`);
    return NextResponse.json({
      ok: true,
      db: "up",
      latencyMs: Math.round(performance.now() - started),
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, db: "down", error: error instanceof Error ? error.message : String(error) },
      { status: 503 },
    );
  }
}
