import { readFile } from "node:fs/promises";

/**
 * The vertical -> environment -> database map.
 *
 * This file is the ONLY place a tenant database name lives on the front door,
 * and it is read server-side only. Nothing here is ever serialised into a page,
 * a form value or an API response — see `publicVerticals()` for what the browser
 * is allowed to see (labels and opaque codes, never `db`).
 *
 * It is a hand-maintained allow-list rather than a query against the server's
 * database list on purpose: a database that nobody has deliberately published
 * must not become reachable just because it exists.
 */

/**
 * "public" is a client-facing environment. "internal" is ours — working copies,
 * R&D, demo builds, anything a client should never see listed. Internal entries
 * are omitted from the page entirely (not disabled, not greyed out: absent) and
 * are refused by `resolveDb` unless the caller is holding the staff key.
 */
export type Visibility = "public" | "internal";

export interface TenantTarget {
  /** Stable, opaque-to-the-client identifier, e.g. "prod", "rnd". */
  code: string;
  /** What the user sees, e.g. "Production". */
  label: string;
  /** Odoo database name. Server-side only. */
  db: string;
  /** Defaults to "public" when the config omits it. */
  visibility: Visibility;
}

export interface Vertical {
  slug: string;
  name: string;
  targets: TenantTarget[];
}

/** The shape handed to the browser: same thing minus every `db`. */
export interface PublicVertical {
  slug: string;
  name: string;
  targets: { code: string; label: string; internal: boolean }[];
}

const CONFIG_PATH = process.env.TENANTS_CONFIG_PATH ?? "/app/config/tenants.json";

/**
 * Odoo database names are used unescaped in a query string and, downstream, as
 * a Postgres database name. Anything outside this set is a configuration error,
 * not something to sanitise into submission.
 */
const DB_NAME_RE = /^[A-Za-z0-9_-]{1,63}$/;
const SLUG_RE = /^[a-z0-9-]{1,40}$/;
const CODE_RE = /^[a-z0-9-]{1,40}$/;

function parse(raw: string): Vertical[] {
  const doc: unknown = JSON.parse(raw);
  if (!doc || typeof doc !== "object" || !Array.isArray((doc as { verticals?: unknown }).verticals)) {
    throw new Error("tenants.json: expected an object with a `verticals` array");
  }

  const verticals = (doc as { verticals: unknown[] }).verticals.map((v, i) => {
    const at = `verticals[${i}]`;
    if (!v || typeof v !== "object") throw new Error(`tenants.json: ${at} is not an object`);
    const { slug, name, targets } = v as Record<string, unknown>;

    if (typeof slug !== "string" || !SLUG_RE.test(slug)) {
      throw new Error(`tenants.json: ${at}.slug must match ${SLUG_RE}`);
    }
    if (typeof name !== "string" || !name.trim()) {
      throw new Error(`tenants.json: ${at}.name is required`);
    }
    if (!Array.isArray(targets) || targets.length === 0) {
      throw new Error(`tenants.json: ${at}.targets must be a non-empty array`);
    }

    const seen = new Set<string>();
    const parsedTargets = targets.map((t, j) => {
      const tAt = `${at}.targets[${j}]`;
      if (!t || typeof t !== "object") throw new Error(`tenants.json: ${tAt} is not an object`);
      const { code, label, db, visibility } = t as Record<string, unknown>;

      if (typeof code !== "string" || !CODE_RE.test(code)) {
        throw new Error(`tenants.json: ${tAt}.code must match ${CODE_RE}`);
      }
      if (seen.has(code)) throw new Error(`tenants.json: ${tAt}.code "${code}" is duplicated`);
      seen.add(code);
      if (typeof label !== "string" || !label.trim()) {
        throw new Error(`tenants.json: ${tAt}.label is required`);
      }
      if (typeof db !== "string" || !DB_NAME_RE.test(db)) {
        throw new Error(`tenants.json: ${tAt}.db must match ${DB_NAME_RE}`);
      }
      // Omitted means public. A typo like "internl" must NOT silently fall back
      // to public — that would publish exactly what it was meant to hide.
      if (visibility !== undefined && visibility !== "public" && visibility !== "internal") {
        throw new Error(`tenants.json: ${tAt}.visibility must be "public" or "internal"`);
      }
      return {
        code,
        label,
        db,
        visibility: (visibility as Visibility | undefined) ?? "public",
      } satisfies TenantTarget;
    });

    return { slug, name, targets: parsedTargets } satisfies Vertical;
  });

  const slugs = new Set<string>();
  for (const v of verticals) {
    if (slugs.has(v.slug)) throw new Error(`tenants.json: duplicate vertical slug "${v.slug}"`);
    slugs.add(v.slug);
  }
  return verticals;
}

/**
 * Re-read on every call. The file is a couple of kilobytes and this is a login
 * page, so the cost is irrelevant next to being able to add a tenant by editing
 * a bind-mounted file instead of rebuilding and recreating the container.
 */
export async function loadVerticals(): Promise<Vertical[]> {
  return parse(await readFile(CONFIG_PATH, "utf8"));
}

/**
 * Strips every `db` before the config can reach a React tree, and drops the
 * internal entries unless the caller is staff. A vertical whose targets are all
 * internal disappears from the list entirely — otherwise the client-facing page
 * would still name the project.
 */
export function toPublic(verticals: Vertical[], includeInternal: boolean): PublicVertical[] {
  return verticals
    .map(({ slug, name, targets }) => ({
      slug,
      name,
      targets: targets
        .filter((t) => includeInternal || t.visibility === "public")
        .map(({ code, label, visibility }) => ({
          code,
          label,
          internal: visibility === "internal",
        })),
    }))
    .filter((v) => v.targets.length > 0);
}

export async function publicVerticals(includeInternal: boolean): Promise<PublicVertical[]> {
  return toPublic(await loadVerticals(), includeInternal);
}

/**
 * Returns the database for a (slug, code) pair, or null if it is not published
 * to this caller. The `includeInternal` check is repeated here on purpose: the
 * page filtering the list is cosmetic, this is the gate. A hand-crafted POST
 * naming an internal pair must fail exactly like a nonexistent one.
 */
export async function resolveDb(
  slug: string,
  code: string,
  includeInternal: boolean,
): Promise<string | null> {
  const vertical = (await loadVerticals()).find((v) => v.slug === slug);
  const target = vertical?.targets.find((t) => t.code === code);
  if (!target) return null;
  if (target.visibility === "internal" && !includeInternal) return null;
  return target.db;
}
