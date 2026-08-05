import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { isValidStaffKey, STAFF_COOKIE, STAFF_COOKIE_MAX_AGE } from "@/lib/staff";
import { absolute, BASE_PATH } from "@/lib/url";

export const dynamic = "force-dynamic";

const COOKIE_SECURE = process.env.COOKIE_SECURE !== "false";

/**
 * `/signin/staff?key=<staff key>` — unlocks the internal environments for this
 * browser and bounces straight back to the chooser, so the key never stays in
 * the address bar, the history, or a Referer header.
 *
 * A wrong or missing key redirects to the same place without a cookie. It
 * deliberately does not say which: there is nothing to gain from telling an
 * outsider that a staff key exists and theirs was close.
 */
export async function GET(request: NextRequest) {
  const key = request.nextUrl.searchParams.get("key");
  const target = await absolute(`${BASE_PATH}/`);

  if (isValidStaffKey(key)) {
    const store = await cookies();
    store.set(STAFF_COOKIE, "1", {
      httpOnly: true,
      secure: COOKIE_SECURE,
      sameSite: "lax",
      path: BASE_PATH,
      maxAge: STAFF_COOKIE_MAX_AGE,
    });
  }

  return NextResponse.redirect(target, 302);
}
