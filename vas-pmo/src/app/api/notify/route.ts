// =============================================================================
// POST /api/notify — the hand-off point from Odoo's outbox.
//
// Verifies the platform HMAC scheme (same as the storefront and the ESB):
//   X-Signature = HMAC-SHA256(secret, ascii(X-Timestamp) + raw_body), 5-minute window.
// Then renders and sends, and answers with a per-channel result list that Odoo mirrors
// into custom.project.notify.log.
// =============================================================================

import { createHmac, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

import { deliver } from "@/lib/services/notification-service";
import type { NotifyPayload } from "@/lib/services/templates";

const SECRET = process.env.VAS_PMO_HMAC_SECRET ?? "";
const REPLAY_WINDOW_SECONDS = 300;

export const dynamic = "force-dynamic";

function signatureValid(rawBody: string, timestamp: string, signature: string): boolean {
  const expected = createHmac("sha256", SECRET)
    .update(Buffer.concat([Buffer.from(timestamp, "ascii"), Buffer.from(rawBody, "utf8")]))
    .digest("hex");
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(signature, "utf8");
  // timingSafeEqual throws on length mismatch, which is itself a signal.
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  if (!SECRET) {
    console.error("[Notify] VAS_PMO_HMAC_SECRET is not set — refusing to accept payloads");
    return NextResponse.json(
      { ok: false, error: "not_configured" },
      { status: 503 },
    );
  }

  const rawBody = await request.text();
  const timestamp = request.headers.get("x-timestamp") ?? "";
  const signature = request.headers.get("x-signature") ?? "";

  if (!timestamp || !signature) {
    return NextResponse.json({ ok: false, error: "missing_signature" }, { status: 401 });
  }
  const skew = Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp));
  if (!Number.isFinite(skew) || skew > REPLAY_WINDOW_SECONDS) {
    return NextResponse.json({ ok: false, error: "stale_timestamp" }, { status: 401 });
  }
  if (!signatureValid(rawBody, timestamp, signature)) {
    return NextResponse.json({ ok: false, error: "bad_signature" }, { status: 401 });
  }

  let payload: NotifyPayload;
  try {
    payload = JSON.parse(rawBody) as NotifyPayload;
  } catch {
    return NextResponse.json({ ok: false, error: "bad_json" }, { status: 400 });
  }
  if (!payload.event || !payload.model) {
    return NextResponse.json({ ok: false, error: "incomplete_payload" }, { status: 400 });
  }

  // Answer only once every channel has been attempted: Odoo writes the delivery log from
  // this response, and a 200 sent early would record sends that never happened.
  const results = await deliver(payload);
  return NextResponse.json({ ok: true, results });
}
