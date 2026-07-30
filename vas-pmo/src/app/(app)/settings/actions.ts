"use server";

import { revalidatePath } from "next/cache";

import { odooFetch } from "@/lib/odoo";
import { getValidToken } from "@/lib/session";

export interface SettingsState {
  error?: string;
  message?: string;
}

function bool(formData: FormData, key: string): boolean {
  return formData.get(key) === "on" || formData.get(key) === "true";
}

async function patch(
  path: string,
  body: Record<string, unknown>,
  revalidate: string,
  reason?: string,
): Promise<SettingsState> {
  const token = await getValidToken();
  if (!token) return { error: "Sesi berakhir. Masuk lagi." };

  const result = await odooFetch(path, { method: "PATCH", token, body });
  if (!result.ok) {
    // Odoo's own constraint message is passed through: "stage marked as Hold must have
    // its clock paused" is more useful than anything this layer could invent.
    return { error: result.error?.message ?? "Perubahan ditolak." };
  }
  revalidatePath(revalidate);
  return {
    message: reason ? `Tersimpan — tercatat di log (${reason}).` : "Tersimpan dan tercatat di log.",
  };
}

export async function updateVertical(
  _prev: SettingsState,
  formData: FormData,
): Promise<SettingsState> {
  const id = String(formData.get("id") ?? "");
  return patch(
    `/vaspmo/api/admin/verticals/${id}`,
    {
      legal_entity: String(formData.get("legal_entity") ?? ""),
      sequence: Number(formData.get("sequence") ?? 10),
      active: bool(formData, "active"),
    },
    "/settings/verticals",
  );
}

export async function updateStage(
  _prev: SettingsState,
  formData: FormData,
): Promise<SettingsState> {
  const id = String(formData.get("id") ?? "");
  return patch(
    `/vaspmo/api/admin/stages/${id}`,
    {
      custom_sla_clock: String(formData.get("sla_clock") ?? "running"),
      custom_auto_close_days: Number(formData.get("auto_close_days") ?? 0),
      custom_require_reason: bool(formData, "require_reason"),
      sequence: Number(formData.get("sequence") ?? 10),
    },
    "/settings/stages",
  );
}

export async function updateRule(
  _prev: SettingsState,
  formData: FormData,
): Promise<SettingsState> {
  const id = String(formData.get("id") ?? "");
  return patch(
    `/vaspmo/api/admin/notify-rules/${id}`,
    {
      channel_wa: bool(formData, "channel_wa"),
      channel_email: bool(formData, "channel_email"),
      channel_odoo: bool(formData, "channel_odoo"),
      active: bool(formData, "active"),
    },
    "/settings/rules",
  );
}
