import { headers } from "next/headers";

/**
 * Must match `basePath` in next.config.mjs. Kept as a constant because the
 * places that need it are building URLs that deliberately step OUTSIDE the app
 * (to Odoo's /web/login), where Next's own basePath handling does not apply.
 */
export const BASE_PATH = "/signin";

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
