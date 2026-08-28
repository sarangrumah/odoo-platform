// =============================================================================
// POST /cockpit/api/agent/skill — the sidecar's only way to reach the data.
//
// Machine-to-machine, HMAC-signed, never called by a browser. It takes a skill
// NAME and structured arguments, never SQL and never a table name: the sidecar
// gets to choose which catalogued question to ask, and nothing else. That is
// the whole containment story, and it lives in these forty lines.
// =============================================================================

import { NextResponse, type NextRequest } from "next/server";

import { verify } from "@/lib/agent/fallback";
import { SKILL_BY_ID, SKILLS } from "@/lib/agent/skills";
import { parseFilters, type Filters } from "@/lib/filters";
import { dataExtent } from "@/lib/queries/sales";

export const dynamic = "force-dynamic";

const MAX_BODY = 8 * 1024;

export async function POST(req: NextRequest) {
  const secret = process.env.COCKPIT_AGENT_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "fallback not configured" }, { status: 503 });
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY) {
    return NextResponse.json({ error: "payload too large" }, { status: 413 });
  }
  if (!verify(secret, raw, req.headers.get("x-custom-signature"))) {
    return NextResponse.json({ error: "bad signature" }, { status: 401 });
  }

  let parsed: { skill?: unknown; filters?: unknown; limit?: unknown; describe?: unknown };
  try {
    parsed = JSON.parse(raw || "{}");
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  // The sidecar builds its entire tool list from this, so the catalogue has one
  // definition and a skill added here becomes answerable on both paths at once.
  if (parsed.describe === true) {
    return NextResponse.json({
      skills: SKILLS.map((s) => ({ id: s.id, description: s.description, slots: s.slots })),
    });
  }

  const skill = typeof parsed.skill === "string" ? SKILL_BY_ID.get(parsed.skill) : undefined;
  if (!skill) {
    return NextResponse.json(
      { error: "unknown skill", known: [...SKILL_BY_ID.keys()] },
      { status: 400 },
    );
  }

  const extent = await dataExtent();
  // parseFilters is the same validator the URL goes through: unknown keys are
  // dropped, store ids must be positive integers, dates must be ISO. Nothing
  // the sidecar sends can widen that.
  const filters: Filters = parseFilters(
    (parsed.filters && typeof parsed.filters === "object" ? parsed.filters : {}) as Record<
      string,
      string
    >,
    extent,
  );

  try {
    const result = await skill.run({
      filters,
      extent,
      limit: typeof parsed.limit === "number" ? parsed.limit : undefined,
    });
    return NextResponse.json({ ...result, skill: skill.id, filters });
  } catch (err) {
    console.error("[agent/skill] failed:", skill.id, err);
    return NextResponse.json({ error: "skill failed" }, { status: 500 });
  }
}
