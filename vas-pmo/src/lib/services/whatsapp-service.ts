// =============================================================================
// VAS PMO — WhatsApp Service
//
// Thin transport layer, ported from e-Telekomunikasi. WaHub is primary; the
// platform's own baileys gateway (compose service `baileys`, :8088) is the
// fallback — that is the pairing the team chose for this app.
//
// Never throws. A notification failure must not take down whatever triggered it.
// =============================================================================

import { isWahubConfigured, wahubFetch } from "./wahub-client";

const WA_PROVIDER = (process.env.WA_PROVIDER ?? "wahub") as "wahub" | "baileys";
const BAILEYS_URL = (process.env.BAILEYS_URL ?? "http://baileys:8088").replace(/\/+$/, "");
const BAILEYS_API_KEY = process.env.BAILEYS_API_KEY ?? "";
const TEST_MODE = process.env.NOTIFICATION_TEST_MODE === "true";
const TEST_PHONE = process.env.NOTIFICATION_TEST_PHONE ?? "";

export interface SendWhatsAppResult {
  success: boolean;
  provider?: string;
  error?: string;
  skipped?: string;
}

/**
 * Normalise an Indonesian number to 628xxx.
 * Handles +6281xxx, 6281xxx, 081xxx, 81xxx.
 */
export function normalizePhoneNumber(phone: string): string {
  let cleaned = phone.replace(/[\s\-()]/g, "");
  if (cleaned.startsWith("+")) cleaned = cleaned.slice(1);
  if (cleaned.startsWith("0")) cleaned = "62" + cleaned.slice(1);
  if (!cleaned.startsWith("62")) cleaned = "62" + cleaned;
  return cleaned;
}

function resolveRecipient(original: string): string {
  if (TEST_MODE && TEST_PHONE) {
    console.info(`[WhatsApp/TestMode] Redirecting ${original} -> ${TEST_PHONE}`);
    return TEST_PHONE;
  }
  return original;
}

async function sendViaWahub(phone: string, message: string): Promise<boolean> {
  if (!isWahubConfigured()) {
    console.warn("[WhatsApp/WaHub] Not configured. Skipping.");
    return false;
  }
  try {
    const { ok, data } = await wahubFetch<{ success?: boolean }>(
      "/messages/send",
      "POST",
      { to: normalizePhoneNumber(phone), content: message, messageType: "text" },
      15_000,
    );
    if (!ok) {
      console.error("[WhatsApp/WaHub] Send failed:", data);
      return false;
    }
    return true;
  } catch (error: unknown) {
    console.error("[WhatsApp/WaHub] Failed to send:", error);
    return false;
  }
}

async function sendViaBaileys(phone: string, message: string): Promise<boolean> {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (BAILEYS_API_KEY) headers.Authorization = `Bearer ${BAILEYS_API_KEY}`;
    const response = await fetch(`${BAILEYS_URL}/api/send`, {
      method: "POST",
      headers,
      body: JSON.stringify({ phone: normalizePhoneNumber(phone), message }),
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "unknown");
      console.error(`[WhatsApp/Baileys] Gateway returned ${response.status}: ${text}`);
      return false;
    }
    const result = (await response.json().catch(() => ({}))) as { success?: boolean };
    return result.success !== false;
  } catch (error: unknown) {
    console.error("[WhatsApp/Baileys] Failed to send:", error);
    return false;
  }
}

export async function sendWhatsApp(phone: string, message: string): Promise<SendWhatsAppResult> {
  if (!phone) return { success: false, skipped: "no phone number on record" };
  const to = resolveRecipient(phone);

  try {
    if (WA_PROVIDER === "baileys") {
      if (await sendViaBaileys(to, message)) return { success: true, provider: "baileys" };
      console.warn("[WhatsApp] baileys failed, falling back to WaHub…");
      return (await sendViaWahub(to, message))
        ? { success: true, provider: "wahub" }
        : { success: false, provider: "baileys", error: "both baileys and wahub failed" };
    }

    if (await sendViaWahub(to, message)) return { success: true, provider: "wahub" };
    console.warn("[WhatsApp] WaHub failed, falling back to baileys…");
    return (await sendViaBaileys(to, message))
      ? { success: true, provider: "baileys" }
      : { success: false, provider: "wahub", error: "both wahub and baileys failed" };
  } catch (error: unknown) {
    const message_ = error instanceof Error ? error.message : String(error);
    console.error(`[WhatsApp] Unexpected error: ${message_}`);
    return { success: false, error: message_ };
  }
}
