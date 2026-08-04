"use server";

import { redirect } from "next/navigation";

import { odooFetch } from "@/lib/odoo";
import { storeSession } from "@/lib/session";

export interface LoginState {
  error?: string;
}

export async function login(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const loginName = String(formData.get("login") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/portfolio");

  if (!loginName || !password) {
    return { error: "Isi email dan password." };
  }

  const result = await odooFetch<{
    access: string;
    refresh: string;
    expires_in: number;
  }>("/vaspmo/api/auth/login", {
    method: "POST",
    body: { login: loginName, password },
  });

  if (!result.ok || !result.data) {
    // Odoo answers the same way for unknown user and wrong password, and so does this.
    if (result.error?.code === "NO_ACCESS") {
      return { error: "Akun ini belum diberi akses VAS PMO. Hubungi administrator." };
    }
    if (result.status === 0) {
      return { error: "Tidak bisa menghubungi Odoo. Coba lagi sebentar." };
    }
    return { error: "Email atau password salah." };
  }

  await storeSession(result.data.access, result.data.refresh, result.data.expires_in);
  redirect(next.startsWith("/") ? next : "/portfolio");
}
