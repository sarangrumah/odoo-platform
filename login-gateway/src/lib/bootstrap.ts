/**
 * Bootstraps an Odoo session that is already pinned to one database, without
 * ever telling the browser which database that is.
 *
 * How it works. Odoo's `ensure_db()` helper (odoo/addons/web/controllers/utils.py)
 * runs at the top of `/web/login`: when the request carries no session yet and a
 * `db` query parameter is present, it validates the name against `db_filter()`,
 * writes `session.db`, and aborts with a 302 back to the same URL. The response
 * to that 302 carries `Set-Cookie: session_id=...`, and that cookie now means
 * "this session belongs to database X".
 *
 * So we make that one request from the server, keep the cookie, hand it to the
 * browser, and send the browser to a plain `/web/login` with no query string.
 * Odoo then renders its own login form — with MFA, password reset and per-DB
 * branding intact — for the right database, and the database name never appears
 * in any HTML, URL or response the client can see.
 *
 * The alternative, POSTing credentials to `/web/session/authenticate` with a
 * `db`, was rejected: it would put user passwords through this app, and its
 * controller answers `{'uid': None}` for MFA users, which is indistinguishable
 * from a wrong password.
 *
 * The `X-Odoo-Database` header is NOT an option here. Odoo 19 marks any request
 * carrying it as stateless (`session.can_save = False`) and returns 403 when it
 * disagrees with an existing `session.db` (odoo/http.py, `_get_session_and_dbname`).
 * It is for server-to-server calls only.
 */

const ODOO_URL = (process.env.ODOO_FRONT_URL ?? "http://odoo-front:8069").replace(/\/+$/, "");
const TIMEOUT_MS = Number(process.env.ODOO_TIMEOUT_MS ?? 10_000);

export type BootstrapResult =
  | { ok: true; cookie: string; maxAge?: number }
  | { ok: false; reason: "unreachable" | "rejected" | "no-cookie" };

/**
 * Pulls session_id out of the response's Set-Cookie headers, along with the
 * lifetime Odoo chose for it (7 days at the time of writing). Re-issuing the
 * cookie without that Max-Age would silently downgrade every session to a
 * browser-session cookie that dies when the tab closes.
 */
function readSessionCookie(headers: Headers): { value: string; maxAge?: number } | null {
  // getSetCookie() is the only correct way to read repeated Set-Cookie headers;
  // joining them into one string breaks on the commas inside Expires dates.
  const raw = (headers as Headers & { getSetCookie?: () => string[] }).getSetCookie?.() ?? [];
  for (const line of raw) {
    const match = /^\s*session_id=([^;]*)/.exec(line);
    if (!match || !match[1]) continue;
    const age = /;\s*Max-Age=(\d+)/i.exec(line);
    return { value: match[1], maxAge: age ? Number(age[1]) : undefined };
  }
  return null;
}

export async function bootstrapSession(db: string): Promise<BootstrapResult> {
  const url = `${ODOO_URL}/web/login?db=${encodeURIComponent(db)}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      // Must not follow: the cookie rides on the 302 itself, and following it
      // would land on the rendered login page and discard the Set-Cookie.
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { ok: false, reason: "unreachable" };
  }

  const location = res.headers.get("location") ?? "";
  // ensure_db() sends a 303 to the database selector when it could NOT resolve
  // the database — i.e. the name in tenants.json does not exist or the target
  // Odoo's dbfilter refuses it. Treat that as a configuration error, not a
  // session: following it would hand the browser a cookie bound to nothing.
  if (location.includes("/web/database/selector")) {
    return { ok: false, reason: "rejected" };
  }

  const session = readSessionCookie(res.headers);
  if (!session) return { ok: false, reason: "no-cookie" };

  return { ok: true, cookie: session.value, maxAge: session.maxAge };
}
