// =============================================================================
// WhatsAppHub API Client — JWT-authenticated HTTP client for WaHub external API
//
// Ported from e-Telekomunikasi (src/lib/services/wahub-client.ts) with the same
// contract: client-credentials token, proactive refresh, single in-flight request,
// one retry on 401.
// =============================================================================

const WAHUB_API_URL = (process.env.WAHUB_API_URL ?? process.env.WAHUB_URL ?? "").replace(/\/+$/, "");
const WAHUB_APP_ID = process.env.WAHUB_APP_ID ?? "";
const WAHUB_APP_SECRET = process.env.WAHUB_APP_SECRET ?? "";

interface TokenState {
  accessToken: string;
  expiresAt: number; // epoch ms
}

let tokenState: TokenState | null = null;
let tokenPromise: Promise<TokenState> | null = null;

export function isWahubConfigured(): boolean {
  return !!(WAHUB_API_URL && WAHUB_APP_ID && WAHUB_APP_SECRET);
}

async function fetchToken(): Promise<TokenState> {
  const response = await fetch(`${WAHUB_API_URL}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "client_credentials",
      app_id: WAHUB_APP_ID,
      app_secret: WAHUB_APP_SECRET,
    }),
    signal: AbortSignal.timeout(10_000),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`WaHub auth failed (${response.status}): ${body}`);
  }

  const data = (await response.json()) as { access_token: string; expires_in: number };
  return {
    accessToken: data.access_token,
    // Refresh 5 minutes before expiry.
    expiresAt: Date.now() + (data.expires_in - 300) * 1000,
  };
}

/**
 * Get a valid access token, refreshing proactively.
 * A mutex keeps concurrent callers on one in-flight request instead of stampeding.
 */
async function getToken(): Promise<string> {
  if (tokenState && Date.now() < tokenState.expiresAt) {
    return tokenState.accessToken;
  }
  if (!tokenPromise) {
    tokenPromise = fetchToken().finally(() => {
      tokenPromise = null;
    });
  }
  tokenState = await tokenPromise;
  return tokenState.accessToken;
}

function invalidateToken(): void {
  tokenState = null;
}

export async function wahubFetch<T = unknown>(
  path: string,
  method: "GET" | "POST" | "PUT" | "DELETE" = "GET",
  body?: Record<string, unknown>,
  timeoutMs = 15_000,
): Promise<{ ok: boolean; status: number; data: T }> {
  const doRequest = async (token: string) => {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    const init: RequestInit = { method, headers, signal: AbortSignal.timeout(timeoutMs) };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    return fetch(`${WAHUB_API_URL}${path}`, init);
  };

  let response = await doRequest(await getToken());
  if (response.status === 401) {
    invalidateToken();
    response = await doRequest(await getToken());
  }

  const text = await response.text().catch(() => "");
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    // Leave the raw body — a non-JSON error page is still worth logging.
  }
  return { ok: response.ok, status: response.status, data: data as T };
}
