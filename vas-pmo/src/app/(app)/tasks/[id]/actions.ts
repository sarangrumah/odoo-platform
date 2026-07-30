"use server";

import { revalidatePath } from "next/cache";

import { odooFetch } from "@/lib/odoo";
import { getValidToken } from "@/lib/session";

export interface StageActionState {
  error?: string;
  message?: string;
}

/**
 * Move a task to a stage. Odoo owns the rules (allowed transitions, mandatory hold
 * reason), so a rejection is surfaced verbatim rather than second-guessed here.
 */
export async function moveStage(
  _prev: StageActionState,
  formData: FormData,
): Promise<StageActionState> {
  const taskId = String(formData.get("task_id") ?? "");
  const stageCode = String(formData.get("stage_code") ?? "");
  const holdReason = String(formData.get("hold_reason") ?? "").trim();

  const token = await getValidToken();
  if (!token) return { error: "Sesi berakhir. Masuk lagi." };

  const body: Record<string, unknown> = { stage_code: stageCode };
  if (holdReason) body.hold_reason = holdReason;

  const result = await odooFetch(`/vaspmo/api/tasks/${taskId}/stage`, {
    method: "POST",
    token,
    body,
  });

  if (!result.ok) {
    return { error: result.error?.message ?? "Perpindahan stage ditolak." };
  }
  revalidatePath(`/tasks/${taskId}`);
  revalidatePath("/board");
  return { message: "Stage diperbarui. Notifikasi masuk antrean outbox Odoo." };
}
