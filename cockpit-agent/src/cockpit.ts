// =============================================================================
// The only thing this service can talk to.
//
// There is no database driver in this package and no credentials for one. Every
// figure comes back through the cockpit's HMAC-signed skill endpoint, which
// accepts a skill NAME and validated arguments — never SQL, never a table name.
// If this process were fully compromised it could ask the eleven catalogued
// questions about prd_levis_begbal and nothing else.
// =============================================================================

import { createHmac } from "node:crypto";

export interface SkillSpec {
  id: string;
  description: string;
  slots: string[];
}

export interface SkillResult {
  headline: string;
  table?: { columns: string[]; rows: (string | number)[][] };
  href?: string;
  note?: string;
  skill?: string;
}

export interface Filters {
  from: string;
  to: string;
  stores: number[];
  categories: string[];
  membership: "member" | "guest" | null;
  associate: string | null;
}

const BASE = process.env.COCKPIT_URL ?? "http://sales-cockpit:8080/cockpit";
const TIMEOUT_MS = 30_000;

function secret(): string {
  const value = process.env.COCKPIT_AGENT_SECRET;
  if (!value || value.length < 32) {
    throw new Error("COCKPIT_AGENT_SECRET is missing or shorter than 32 characters");
  }
  return value;
}

/** ai-gateway's scheme: HMAC-SHA256 over "<ts>.<body>", one header. */
function sign(body: string): Record<string, string> {
  const ts = Math.floor(Date.now() / 1000).toString();
  const mac = createHmac("sha256", secret()).update(`${ts}.${body}`, "utf8").digest("hex");
  return { "X-Custom-Signature": `t=${ts},v1=${mac}` };
}

async function post<T>(payload: unknown): Promise<T> {
  const body = JSON.stringify(payload);
  const res = await fetch(`${BASE}/api/agent/skill`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...sign(body) },
    body,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) {
    throw new Error(`cockpit skill endpoint returned ${res.status}`);
  }
  return (await res.json()) as T;
}

/** The catalogue, fetched at startup so the tool list has one definition. */
export function describeSkills(): Promise<{ skills: SkillSpec[] }> {
  return post<{ skills: SkillSpec[] }>({ describe: true });
}

export function runSkill(
  skill: string,
  filters: Record<string, string>,
  limit?: number,
): Promise<SkillResult> {
  return post<SkillResult>({ skill, filters, limit });
}
