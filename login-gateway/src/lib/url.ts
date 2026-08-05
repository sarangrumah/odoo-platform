import { headers } from "next/headers";

/**
 * Must match `basePath` in next.config.mjs. Kept as a constant because the
 * places that need it are building URLs that deliberately step OUTSIDE the app
 * (to Odoo's /web/login), where Next's own basePath handling does not apply.
 */
export const BASE_PATH = "/signin";

/**
 * Path to a file in public/.
 *
 * Next prepends basePath to routes and to static imports, but NOT to a plain
 * string in `<img src>` — `/brand/eal-logo.png` would 404 because the file is
 * actually served at /signin/brand/eal-logo.png. Everything under public/ must
 * go through here.
 */
export function asset(path: string): string {
  return `${BASE_PATH}${path}`;
}

/**
 * Builds an absolute URL on the origin the browser actually used.
 *
 * `redirect("/web/login")` would be resolved against basePath and send the
 * browser to /signin/web/login. An absolute URL is passed through untouched,
 * which is what both the post-selection hop and the staff unlock need.
 */
export async function absolute(path: string): Promise<string> {
  const h = await headers();
  const proto = h.get("x-forwarded-proto") ?? "https";
  const host = h.get("host") ?? "";
  return `${proto}://${host}${path}`;
}
