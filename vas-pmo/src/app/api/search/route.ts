// =============================================================================
// GET /api/search?q= — BFF proxy for the command palette.
//
// The palette runs in the browser, where the access token is not readable by design
// (httpOnly cookie). So the query goes through here, where the cookie IS available.
// =============================================================================

import { NextResponse } from "next/server";

import { odooFetch } from "@/lib/odoo";
import { getValidToken } from "@/lib/session";

export const dynamic = "force-dynamic";

export interface SearchHit {
  type: "task" | "cr" | "project";
  id: number;
  label: string;
  hint: string;
  stage: string;
  url: string;
}

export async function GET(request: Request) {
  const token = await getValidToken();
  if (!token) {
    return NextResponse.json({ ok: false, error: "unauthenticated" }, { status: 401 });
  }

  const term = new URL(request.url).searchParams.get("q") ?? "";
  const result = await odooFetch<SearchHit[]>(
    `/vaspmo/api/search?q=${encodeURIComponent(term)}&limit=8`,
    { token, timeoutMs: 8_000 },
  );

  // A failed search must degrade to "no results", not to a broken palette.
  return NextResponse.json({ ok: result.ok, results: result.data ?? [] });
}
