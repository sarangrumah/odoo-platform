// =============================================================================
// VAS PMO — Notification orchestrator
//
// The e-Telekomunikasi contract, kept verbatim:
//   * e-mail and WhatsApp run INDEPENDENTLY — one failing does not stop the other
//   * fire-and-forget safe: this never throws
//   * every attempt is reported back, per channel per recipient
//
// The one structural difference: the event is not raised here. Odoo owns the outbox
// (four different writers can change a task), and this service is the renderer and
// sender it hands off to. Everything downstream of that hand-off is the same code
// shape as e-Telekomunikasi.
// =============================================================================

import { sendEmail, type SendEmailResult } from "./email-service";
import { sendWhatsApp, type SendWhatsAppResult } from "./whatsapp-service";
import { buildEmail, buildWhatsApp, type NotifyPayload, type NotifyRecipient } from "./templates";

export interface ChannelResult {
  channel: "wa" | "email";
  kind: string;
  name: string;
  email?: string;
  phone?: string;
  transport?: string;
  success: boolean;
  skipped?: string;
  error?: string;
}

async function sendWaFor(
  payload: NotifyPayload,
  recipient: NotifyRecipient,
): Promise<ChannelResult> {
  const result: SendWhatsAppResult = await sendWhatsApp(
    recipient.phone,
    buildWhatsApp(payload, recipient),
  ).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[Notify] WhatsApp crashed: ${message}`);
    return { success: false, error: message } as SendWhatsAppResult;
  });
  return {
    channel: "wa",
    kind: recipient.kind,
    name: recipient.name,
    phone: recipient.phone,
    transport: result.provider,
    success: result.success,
    skipped: result.skipped,
    error: result.error,
  };
}

async function sendEmailFor(
  payload: NotifyPayload,
  recipient: NotifyRecipient,
): Promise<ChannelResult> {
  const { subject, html } = buildEmail(payload, recipient);
  const result: SendEmailResult = await sendEmail({ to: recipient.email, subject, html }).catch(
    (error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`[Notify] E-mail crashed: ${message}`);
      return { success: false, error: message } as SendEmailResult;
    },
  );
  return {
    channel: "email",
    kind: recipient.kind,
    name: recipient.name,
    email: recipient.email,
    transport: "smtp",
    success: result.success,
    skipped: result.skipped,
    error: result.error,
  };
}

/**
 * Deliver one queued notification across every requested channel.
 * Returns one row per (recipient x channel) so Odoo's delivery log stays truthful.
 */
export async function deliver(payload: NotifyPayload): Promise<ChannelResult[]> {
  const jobs: Array<Promise<ChannelResult>> = [];

  for (const recipient of payload.recipients ?? []) {
    // `wa` / `email_enabled` are set by the Odoo rule engine. Undefined means the rule
    // did not say, and the historical default in this team is "both on".
    const wantWa = recipient.wa !== false;
    const wantEmail = recipient.email_enabled !== false;

    if (wantWa) {
      if (recipient.phone) {
        jobs.push(sendWaFor(payload, recipient));
      } else {
        jobs.push(
          Promise.resolve<ChannelResult>({
            channel: "wa",
            kind: recipient.kind,
            name: recipient.name,
            success: false,
            skipped: "no phone number on record",
          }),
        );
      }
    }
    if (wantEmail) {
      if (recipient.email) {
        jobs.push(sendEmailFor(payload, recipient));
      } else {
        jobs.push(
          Promise.resolve<ChannelResult>({
            channel: "email",
            kind: recipient.kind,
            name: recipient.name,
            success: false,
            skipped: "no e-mail address on record",
          }),
        );
      }
    }
  }

  // allSettled, not all: one rejected promise must not hide the results of the others.
  const settled = await Promise.allSettled(jobs);
  const results = settled.map((entry, index) =>
    entry.status === "fulfilled"
      ? entry.value
      : ({
          channel: "wa",
          kind: "unknown",
          name: `recipient #${index}`,
          success: false,
          error: String(entry.reason),
        } as ChannelResult),
  );

  const failed = results.filter((r) => !r.success && !r.skipped).length;
  const skipped = results.filter((r) => r.skipped).length;
  console.info(
    `[Notify] ${payload.event} on ${payload.model}:${payload.id} — ` +
      `${results.length - failed - skipped} sent, ${failed} failed, ${skipped} skipped`,
  );
  return results;
}
