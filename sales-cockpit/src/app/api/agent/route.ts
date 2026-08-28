// =============================================================================
// POST /cockpit/api/agent — the assistant's only public entry point.
//
// Session-gated by hand: middleware.ts guards the page routes by cookie
// PRESENCE only and cannot verify the HMAC on the edge runtime, so the real
// check has to happen here, exactly as it does in (app)/layout.tsx. Adding the
// path to the middleware matcher is defence in depth, not the boundary.
// =============================================================================

import { NextResponse, type NextRequest } from "next/server";

import { answerFromCatalog, giveUp, SUGGESTIONS, type Answer } from "@/lib/agent/answer";
import { askFallback, fallbackConfigured } from "@/lib/agent/fallback";
import { getSession } from "@/lib/auth";
import { parseFilters, type Filters } from "@/lib/filters";
import { dataExtent } from "@/lib/queries/sales";
import { once, rateLimit } from "@/lib/ratelimit";

export const dynamic = "force-dynamic";

const MAX_BODY = 8 * 1024;
const MAX_QUESTION = 500;

/** A SQL query is cheap; a model call is not. Two budgets, deliberately. */
const CATALOG_PER_MINUTE = 30;
const FALLBACK_PER_MINUTE = 6;

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

  let parsed: { question?: unknown; filters?: unknown };
  try {
    parsed = JSON.parse(raw || "{}");
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const question = typeof parsed.question === "string" ? parsed.question.trim() : "";
  if (!question) {
    return NextResponse.json({ error: "question required" }, { status: 400 });
  }
  if (question.length > MAX_QUESTION) {
    return NextResponse.json({ error: "question too long" }, { status: 413 });
  }

  if (!rateLimit(`agent:${session.uid}`, CATALOG_PER_MINUTE, 60_000)) {
    return NextResponse.json({ error: "rate limited" }, { status: 429, headers: { "Retry-After": "30" } });
  }

  const started = Date.now();
  const extent = await dataExtent();

  // The filter bar is the reader's context: a question with no period in it is
  // about whatever range is on screen, not about the whole dataset.
  const filters: Filters = parseFilters(
    (parsed.filters && typeof parsed.filters === "object" ? parsed.filters : {}) as Record<
      string,
      string
    >,
    extent,
  );

  let answer: Answer;
  try {
    const outcome = await answerFromCatalog(question, filters, extent);
    if (outcome) {
      answer = outcome.answer;
    } else if (fallbackConfigured()) {
      if (!rateLimit(`agent-llm:${session.uid}`, FALLBACK_PER_MINUTE, 60_000)) {
        answer = {
          source: "unmatched",
          headline:
            "Pertanyaan ini perlu waktu berpikir lebih lama, dan sudah beberapa kali dalam semenit. " +
            "Coba lagi sebentar lagi.",
          suggestions: SUGGESTIONS.slice(0, 3),
        };
      } else {
        const escalated = await once(`agent-llm:${session.uid}`, () =>
          askFallback({ question, filters, extent }),
        );
        answer = escalated ?? giveUp(extent);
      }
    } else {
      answer = giveUp(extent);
    }
  } catch (err) {
    console.error("[agent] failed:", err);
    return NextResponse.json(
      {
        source: "unmatched",
        headline: "Ada gangguan saat mengambil datanya. Coba lagi sebentar lagi.",
      },
      { status: 500 },
    );
  }

  const tookMs = Date.now() - started;

  // The audit line doubles as the backlog: a question that keeps landing on
  // source=unmatched is the next skill worth writing deterministically.
  console.info(
    JSON.stringify({
      at: "agent",
      uid: session.uid,
      login: session.login,
      question,
      source: answer.source,
      skill: answer.skill ?? null,
      from: filters.from,
      to: filters.to,
      stores: filters.stores.length,
      tookMs,
    }),
  );

  return json(answer, 200, { tookMs });
}
