// =============================================================================
// POST /finance/api/agent — the assistant's only public entry point.
//
// Session-gated by hand: middleware.ts guards the page routes by cookie
// PRESENCE only and cannot verify the HMAC on the edge runtime, so the real
// check has to happen here, exactly as it does in (app)/layout.tsx.
//
// There is no model fallback wired in this build. The sidecar the sales cockpit
// escalates to is not running on this host, and an accounting assistant that
// guesses is worse than one that says it does not know — so an unmatched
// question gets an honest refusal rather than a plausible sentence.
// =============================================================================

import { NextResponse, type NextRequest } from "next/server";

import { answerFromCatalog, giveUp, SUGGESTIONS, type Answer } from "@/lib/agent/answer";
import { getSession } from "@/lib/auth";
import { today } from "@/lib/finance-filters";
import { defaultCompanyIds } from "@/lib/queries/common";
import { rateLimit } from "@/lib/ratelimit";

export const dynamic = "force-dynamic";

const MAX_BODY = 8 * 1024;
const MAX_QUESTION = 500;
const PER_MINUTE = 30;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function json(answer: Answer, status = 200, extra: Record<string, unknown> = {}) {
  return NextResponse.json({ ...answer, ...extra }, { status });
}

export async function POST(req: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY) {
    return NextResponse.json({ error: "payload too large" }, { status: 413 });
  }

  let parsed: { question?: unknown; asOf?: unknown };
  try {
    parsed = JSON.parse(raw || "{}");
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const question = typeof parsed.question === "string" ? parsed.question.trim() : "";
  if (!question) return NextResponse.json({ error: "question required" }, { status: 400 });
  if (question.length > MAX_QUESTION) {
    return NextResponse.json({ error: "question too long" }, { status: 413 });
  }

  if (!rateLimit(`agent:${session.uid}`, PER_MINUTE, 60_000)) {
    return NextResponse.json(
      { error: "rate limited" },
      { status: 429, headers: { "Retry-After": "30" } },
    );
  }

  const now = today();
  // The cut-off the reader is looking at, never trusted blindly: it arrives
  // from the client and goes straight into a date parameter.
  const asOf =
    typeof parsed.asOf === "string" && ISO_DATE.test(parsed.asOf) ? parsed.asOf : now;

  try {
    const companies = await defaultCompanyIds();
    const outcome = await answerFromCatalog(question, { companies, today: now, asOf });

    if (outcome) {
      console.log(
        `[agent] uid=${session.uid} skill=${outcome.answer.skill ?? outcome.answer.source} ` +
          `asOf=${outcome.asOf} q=${JSON.stringify(question.slice(0, 120))}`,
      );
      return json(outcome.answer, 200, { asOf: outcome.asOf });
    }

    console.log(`[agent] uid=${session.uid} unmatched q=${JSON.stringify(question.slice(0, 120))}`);
    return json(giveUp(), 200, { asOf });
  } catch (error) {
    console.error("[agent] failed", error);
    return json(
      {
        source: "unmatched",
        headline: "Ada kendala saat membaca database. Coba lagi sebentar lagi.",
        suggestions: SUGGESTIONS.slice(0, 3),
      },
      500,
    );
  }
}
