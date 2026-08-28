"use server";

import { redirect } from "next/navigation";
import { authenticate, clearSession, storeSession } from "@/lib/auth";

export interface LoginState {
  error?: string;
}

export async function login(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const username = String(formData.get("login") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "");

  if (!username || !password) return { error: "Isi login dan kata sandi." };

  const result = await authenticate(username, password);
  if (!result.ok || !result.session) return { error: result.error ?? "Login gagal." };

  await storeSession(result.session);

  // Only same-app paths, never an absolute URL from the query string — that
  // would turn the login form into an open redirect.
  const target = next.startsWith("/") && !next.startsWith("//") ? next : "/overview";
  redirect(target);
}

export async function logout() {
  await clearSession();
  redirect("/login");
}
