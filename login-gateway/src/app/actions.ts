"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { bootstrapSession } from "@/lib/bootstrap";
import { isStaffCookieValid, STAFF_COOKIE } from "@/lib/staff";
import { resolveDb } from "@/lib/tenants";
import { absolute } from "@/lib/url";

export interface ChooseState {
  error?: string;
}

/** `secure` must be off for a plain-http dev run, on everywhere else. */
const COOKIE_SECURE = process.env.COOKIE_SECURE !== "false";

export async function chooseTenant(_prev: ChooseState, formData: FormData): Promise<ChooseState> {
  const slug = String(formData.get("vertical") ?? "").trim();
  const code = String(formData.get("environment") ?? "").trim();

  if (!slug || !code) {
    return { error: "Pilih vertical dan environment terlebih dahulu." };
  }

  const store = await cookies();
  const isStaff = isStaffCookieValid(store.get(STAFF_COOKIE)?.value);

  // The browser only ever sends a (slug, code) pair; the database name is
  // produced here, from the server-side allow-list, and stays here. resolveDb
  // re-checks visibility rather than trusting that the page only offered what
  // this browser is allowed to pick.
  const db = await resolveDb(slug, code, isStaff);
  if (!db) {
    // Same message for "no such vertical", "no such environment" and "internal,
    // and you are not staff" — the form cannot produce any of them, so anything
    // reaching this branch is someone probing the pair space, and it should not
    // confirm which guess was close.
    return { error: "Pilihan tidak tersedia. Muat ulang halaman lalu coba lagi." };
  }

  const result = await bootstrapSession(db);
  if (!result.ok) {
    if (result.reason === "unreachable") {
      return { error: "Tidak bisa menghubungi server Odoo. Coba lagi sebentar." };
    }
    // "rejected" and "no-cookie" are both our own misconfiguration (a database
    // listed in tenants.json that the server will not serve). Do not leak which.
    return { error: "Environment ini sedang tidak tersedia. Hubungi administrator." };
  }

  store.set("session_id", result.cookie, {
    httpOnly: true,
    secure: COOKIE_SECURE,
    sameSite: "lax",
    // Odoo owns this cookie from here on, and it lives at the origin root —
    // scoping it to /signin would make it invisible to /web and /odoo.
    path: "/",
    // Mirror the lifetime Odoo issued rather than inventing one.
    ...(result.maxAge ? { maxAge: result.maxAge } : {}),
  });

  // Absolute URL on purpose: `redirect("/web/login")` would be resolved against
  // this app's basePath and send the browser to /signin/web/login, which does
  // not exist. /web/login belongs to Odoo, one route table up in Caddy.
  redirect(await absolute("/web/login"));
}
