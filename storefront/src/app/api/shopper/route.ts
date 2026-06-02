import { NextRequest, NextResponse } from "next/server";
import { signGateway } from "@/lib/hmac";
import { rateLimit } from "@/lib/ratelimit";

export const dynamic = "force-dynamic";

const MAX_BODY = 32 * 1024; // 32 KB — chat turns are tiny
const AI_GATEWAY_URL = process.env.AI_GATEWAY_URL || "http://ai-gateway:8080";
const GATEWAY_SECRET = process.env.GATEWAY_SHARED_SECRET || "";
const TENANT_DB = process.env.ODOO_TENANT_DB || "gentlewoman";

function clientIp(req: NextRequest): string {
  return (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
}

/**
 * BFF for the AI personal shopper.
 * Browser → POST /api/shopper  ⇒  ai-gateway → POST /v1/shopper
 *
 * The gateway URL + shared secret stay SERVER-SIDE; the browser never sees them.
 * The tenant DB is injected here so the gateway reads the correct catalog.
 */
export async function POST(req: NextRequest) {
  // Local-LLM inference is CPU-bound; a tight per-IP cap keeps it from being
  // hammered (each request can trigger up to two model passes).
  if (!rateLimit(`${clientIp(req)}:shopper`, 12, 60_000)) {
    return NextResponse.json(
      { ok: false, error_code: "RATE_LIMITED", message: "Sebentar ya, Kak — coba lagi sesaat lagi." },
      { status: 429, headers: { "Retry-After": "30" } },
    );
  }

  if (!GATEWAY_SECRET) {
    return NextResponse.json(
      { ok: false, error_code: "NOT_CONFIGURED", message: "Shopper is not configured." },
      { status: 503 },
    );
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY) {
    return NextResponse.json(
      { ok: false, error_code: "PAYLOAD_TOO_LARGE", message: "Pesan terlalu panjang." },
      { status: 413 },
    );
  }

  let parsed: { messages?: unknown; locale?: unknown };
  try {
    parsed = JSON.parse(raw || "{}");
  } catch {
    return NextResponse.json({ ok: false, error_code: "BAD_JSON", message: "Invalid body." }, { status: 400 });
  }
  if (!Array.isArray(parsed.messages) || parsed.messages.length === 0) {
    return NextResponse.json(
      { ok: false, error_code: "BAD_REQUEST", message: "messages required." },
      { status: 400 },
    );
  }

  const payload = JSON.stringify({
    messages: parsed.messages,
    locale: typeof parsed.locale === "string" ? parsed.locale : "id",
    tenant: TENANT_DB,
  });

  let upstream: Response;
  try {
    upstream = await fetch(`${AI_GATEWAY_URL}/v1/shopper`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": TENANT_DB,
        ...signGateway(GATEWAY_SECRET, payload),
      },
      body: payload,
      cache: "no-store",
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error_code: "UPSTREAM_UNREACHABLE", message: String(e) },
      { status: 502 },
    );
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  });
}
