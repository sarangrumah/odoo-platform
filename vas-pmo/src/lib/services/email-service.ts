// =============================================================================
// VAS PMO — Email channel
//
// SMTP through the relay the platform already runs (mailpit in dev, the real relay in
// prod). One shared transporter, created lazily so a broken SMTP config cannot stop the
// app from booting. Never throws — a failed e-mail must not sink the WhatsApp send.
// =============================================================================

import { createTransport, type Transporter } from "nodemailer";

const SMTP_HOST = process.env.SMTP_HOST ?? "mailpit";
const SMTP_PORT = Number(process.env.SMTP_PORT ?? 1025);
const SMTP_USER = process.env.SMTP_USER ?? "";
const SMTP_PASSWORD = process.env.SMTP_PASSWORD ?? "";
const MAIL_FROM = process.env.MAIL_FROM ?? "VAS PMO <no-reply@vas-pmo.internal>";
const TEST_MODE = process.env.NOTIFICATION_TEST_MODE === "true";
const TEST_EMAIL = process.env.NOTIFICATION_TEST_EMAIL ?? "";

export interface SendEmailResult {
  success: boolean;
  error?: string;
  skipped?: string;
}

let transporter: Transporter | null = null;

function getTransporter(): Transporter {
  if (!transporter) {
    transporter = createTransport({
      host: SMTP_HOST,
      port: SMTP_PORT,
      secure: SMTP_PORT === 465,
      auth: SMTP_USER ? { user: SMTP_USER, pass: SMTP_PASSWORD } : undefined,
    });
  }
  return transporter;
}

export async function sendEmail(args: {
  to: string;
  subject: string;
  html: string;
}): Promise<SendEmailResult> {
  if (!args.to) return { success: false, skipped: "no e-mail address on record" };
  const to = TEST_MODE && TEST_EMAIL ? TEST_EMAIL : args.to;
  if (to !== args.to) console.info(`[Email/TestMode] Redirecting ${args.to} -> ${to}`);

  try {
    await getTransporter().sendMail({
      from: MAIL_FROM,
      to,
      subject: args.subject,
      html: args.html,
    });
    return { success: true };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[Email] Send failed: ${message}`);
    return { success: false, error: message };
  }
}
