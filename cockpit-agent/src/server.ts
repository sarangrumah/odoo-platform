// =============================================================================
// The sidecar's HTTP surface: /health and one POST /ask.
//
// Never exposed through Caddy. It is published on loopback only and reachable
// on the compose network by the cockpit, which is the sole caller — and every
// request is HMAC-verified anyway, on the same scheme the platform already uses
// for ai-gateway and tenant-orchestrator.
// =============================================================================

import { createHmac, timingSafeEqual } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { ask, type AskRequest } from "./agent.js";

const PORT = Number(process.env.PORT ?? 8080);
const MAX_BODY = 16 * 1024;
const REPLAY_WINDOW_S = 300;

function secret(): string {
  const value = process.env.COCKPIT_AGENT_SECRET;
  if (!value || value.length < 32) {
    throw new Error("COCKPIT_AGENT_SECRET is missing or shorter than 32 characters");
  }
  return value;
}

function verify(rawBody: string, header: string | undefined): boolean {
  if (!header) return false;
  const m = /^t=(\d+),v1=([0-9a-f]{64})$/.exec(header);
  if (!m) return false;

  const ts = Number(m[1]);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > REPLAY_WINDOW_S) return false;

  const expected = createHmac("sha256", secret()).update(`${ts}.${rawBody}`, "utf8").digest();
  const given = Buffer.from(m[2]!, "hex");
  return given.length === expected.length && timingSafeEqual(expected, given);
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      // Refuse early rather than buffering something huge before rejecting it.
      if (size > MAX_BODY) {
        reject(new Error("payload too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function json(res: ServerResponse, status: number, payload: unknown) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    return json(res, 200, { ok: true });
  }

  if (req.method !== "POST" || req.url !== "/ask") {
    return json(res, 404, { error: "not found" });
  }

  let raw: string;
  try {
    raw = await readBody(req);
  } catch {
    return json(res, 413, { error: "payload too large" });
  }

  if (!verify(raw, req.headers["x-custom-signature"] as string | undefined)) {
    return json(res, 401, { error: "bad signature" });
  }

  let parsed: Partial<AskRequest>;
  try {
    parsed = JSON.parse(raw) as Partial<AskRequest>;
  } catch {
    return json(res, 400, { error: "invalid json" });
  }

  if (!parsed.question || !parsed.filters || !parsed.extent) {
    return json(res, 400, { error: "question, filters and extent are required" });
  }

  const started = Date.now();
  try {
    const answer = await ask(parsed as AskRequest);
    const tookMs = Date.now() - started;

    // Log which tools ran. An answer that names a figure with an empty `calls`
    // list would mean the model spoke from memory, which is the one thing this
    // service must never do — this line is how you would catch it.
    console.info(
      JSON.stringify({
        at: "ask",
        question: parsed.question,
        calls: answer.calls,
        tookMs,
        empty: !answer.headline,
      }),
    );

    if (!answer.headline) {
      return json(res, 200, {
        headline:
          "Maaf, saya tidak menemukan jawabannya di data POS prd_levis_begbal.",
      });
    }
    return json(res, 200, answer);
  } catch (err) {
    console.error("[ask] failed:", err);
    return json(res, 502, { error: "agent failed" });
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.info(`cockpit-agent listening on ${PORT}`);
});
