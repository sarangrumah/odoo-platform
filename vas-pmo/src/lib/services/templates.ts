// =============================================================================
// VAS PMO — message templates
//
// The WhatsApp shape is lifted from e-Telekomunikasi on purpose: bold title, the ━ rule,
// labelled fields, a deep link, and the automatic-message footer. People on this team
// already read that format, so it needs no learning.
// =============================================================================

export interface NotifyRecipient {
  kind: string;
  name: string;
  email: string;
  phone: string;
  wa?: boolean;
  email_enabled?: boolean;
}

export interface NotifyPayload {
  event: string;
  model: string;
  id: number;
  label: string;
  url: string;
  tenant?: string;
  recipients: NotifyRecipient[];
  vertical?: { code: string; name: string; label: string };
  context?: Record<string, unknown>;
}

const EVENT_TITLES: Record<string, string> = {
  task_created: "Task Baru Dibuat",
  assigned: "Task Ditugaskan ke Anda",
  stage_changed: "Task Berpindah Stage",
  task_closed: "Task Selesai",
  on_hold: "Task Di-hold",
  resumed: "Task Dilanjutkan Kembali",
  hold_expired: "Hold Melewati Batas Waktu",
  verify_request: "Mohon Verifikasi Hasil Pekerjaan",
  verify_reminder_h2: "Pengingat Verifikasi (H+2)",
  verify_reminder_h5: "Pengingat Verifikasi (H+5)",
  verify_auto_close: "Ditutup Otomatis Tanpa Verifikasi",
  due_h3: "Jatuh Tempo 3 Hari Lagi",
  due_h1: "Jatuh Tempo Besok",
  overdue: "Melewati Jatuh Tempo",
  escalation: "Eskalasi — Terlambat Lebih dari 3 Hari",
  health_degraded: "Kesehatan Project Menurun",
  cr_created: "Change Request Baru Masuk",
  cr_analysis: "Change Request Masuk Analisis",
  cr_submit: "Change Request Menunggu Approval Anda",
  cr_approve: "Change Request Disetujui",
  cr_reject: "Change Request Ditolak",
  cr_closed: "Change Request Selesai",
  cr_intake_overdue: "Intake Melewati SLA Respons",
  weekly_reminder: "Weekly Progress Belum Disubmit",
  weekly_submitted: "Weekly Progress Disubmit",
  weekly_digest: "Rekap Mingguan",
};

export function eventTitle(event: string): string {
  return EVENT_TITLES[event] ?? event;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/** Field lines shown for an event, in the order they should be read. */
function fieldLines(payload: NotifyPayload): Array<[string, string]> {
  const ctx = (payload.context ?? {}) as Record<string, string | number | boolean>;
  const lines: Array<[string, string]> = [];
  const push = (label: string, value: unknown) => {
    if (value === undefined || value === null || value === "" || value === false) return;
    lines.push([label, String(value)]);
  };

  if (payload.vertical) push("Vertical", payload.vertical.label);
  push("Objek", payload.label);
  push("Project", ctx.project);
  push("CR", ctx.cr_code);
  push("Stage", ctx.stage);
  push("Sprint", ctx.sprint);
  push("Prioritas", ctx.priority);
  push("Impact", ctx.impact);
  push("Approval", ctx.approval_progress);
  push("Jatuh tempo", ctx.deadline || ctx.sla_due);
  push("Alasan hold", ctx.hold_reason);
  push("Batas hold", ctx.hold_until);
  push("Batas verifikasi", ctx.verification_due);
  push("Alasan penolakan", ctx.reject_reason);
  push("Minggu", ctx.week);
  push("Selesai minggu ini", ctx.done_count);
  push("Carry-over", ctx.carry_over);
  push("Blocker", ctx.blocker);
  return lines;
}

export function buildWhatsApp(payload: NotifyPayload, recipient: NotifyRecipient): string {
  const rule = "━━━━━━━━━━━━━━━━━━";
  const lines = fieldLines(payload)
    .map(([label, value]) => `${label}: *${value}*`)
    .join("\n");

  let message = `*VAS PMO — Product Owner VAS*\n${rule}\n${eventTitle(payload.event)}\n\n`;
  message += `Yth. *${recipient.name}*,\n\n`;
  message += `${lines}\n`;

  if (payload.event === "verify_request") {
    const days = (payload.context?.auto_close_days as number) ?? 5;
    message += `\nBila tidak ada tanggapan dalam ${days} hari kerja,\n`;
    message += `item ini ditutup otomatis.\n`;
  }
  message += `\nBuka detail:\n${payload.url}\n`;
  message += `\n${rule}\n_Pesan ini dikirim otomatis oleh sistem._`;
  return message;
}

export function buildEmail(payload: NotifyPayload, recipient: NotifyRecipient): {
  subject: string;
  html: string;
} {
  const title = eventTitle(payload.event);
  const rows = fieldLines(payload)
    .map(
      ([label, value]) => `
        <tr>
          <td style="padding:5px 0;color:#5C7076;width:170px;font-size:13px;">${escapeHtml(label)}</td>
          <td style="padding:5px 0;color:#11262B;font-size:13px;font-weight:600;">${escapeHtml(value)}</td>
        </tr>`,
    )
    .join("");

  const subject = `[VAS PMO] ${title} — ${payload.label}`;
  const html = `<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F4F7F7;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F7F7;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:10px;overflow:hidden;border:1px solid #DDE6E7;">
        <tr><td style="background:#0D6E78;padding:20px 28px;">
          <h1 style="margin:0;font-size:18px;color:#FFFFFF;font-weight:700;">VAS PMO</h1>
          <p style="margin:3px 0 0;font-size:12px;color:#C7E5E8;">Product Owner — Value-Added Services</p>
        </td></tr>
        <tr><td style="padding:24px 28px;">
          <h2 style="margin:0 0 6px;font-size:16px;color:#11262B;">${escapeHtml(title)}</h2>
          <p style="margin:0 0 18px;font-size:13.5px;color:#33484E;">Yth. <strong>${escapeHtml(recipient.name)}</strong>,</p>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="background:#FAFCFC;border:1px solid #EAF0F0;border-radius:8px;">
            <tr><td style="padding:14px 18px;"><table role="presentation" width="100%">${rows}</table></td></tr>
          </table>
          <table role="presentation" width="100%"><tr><td align="center" style="padding:20px 0 4px;">
            <a href="${escapeHtml(payload.url)}"
               style="display:inline-block;background:#0D6E78;color:#FFFFFF;text-decoration:none;padding:11px 28px;border-radius:6px;font-size:13.5px;font-weight:600;">
               Buka detail</a>
          </td></tr></table>
        </td></tr>
        <tr><td style="background:#FAFCFC;padding:14px 24px;border-top:1px solid #EAF0F0;">
          <p style="margin:0;font-size:11.5px;color:#5C7076;text-align:center;">
            Dikirim otomatis oleh sistem VAS PMO. Mohon tidak membalas e-mail ini.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>`;
  return { subject, html };
}
