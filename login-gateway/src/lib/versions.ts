import { readFile } from "node:fs/promises";

/**
 * Reader for `config/versions.json`, the file scripts/gen_module_versions.py
 * writes from the addon manifests and the git log.
 *
 * Same contract as tenants.ts: read per request from the bind-mounted config
 * directory, validate hard, and hand the browser a filtered view rather than
 * the raw document. Refreshing the version list is a script run plus a
 * container restart, not an image rebuild.
 */

export interface Change {
  sha: string;
  date: string;
  subject: string;
}

export interface ModuleEntry {
  module: string;
  bucket: string;
  name: string;
  version: string;
  summary: string;
  category: string;
  depends: number;
  /** False for modules whose name identifies a client — staff view only. */
  public: boolean;
  /** Date of the most recent commit, "" if none. Survives into the public view
   *  when `changes` does not. */
  last_change: string;
  /** Every commit that ever touched the module, not just the listed ones. */
  change_count: number;
  changes: Change[];
}

export interface Bucket {
  key: string;
  label: string;
  note: string;
}

export interface Platform {
  odoo: { edition: string; version: string; digest: string };
  postgres: string;
  python: string;
  commit: string;
  branch: string;
}

export interface Versions {
  schema: number;
  generated_at: string;
  platform: Platform;
  buckets: Bucket[];
  modules: ModuleEntry[];
}

/** What the browser gets: no `public` flag to reason about, just the rows. */
export type PublicModule = Omit<ModuleEntry, "public">;

const CONFIG_PATH = process.env.VERSIONS_CONFIG_PATH ?? "/app/config/versions.json";

/** Bumped by the generator when the shape changes; refuse anything else rather
 *  than render half a page off a document we do not understand. */
const SCHEMA = 1;

function str(v: unknown, at: string): string {
  if (typeof v !== "string") throw new Error(`versions.json: ${at} must be a string`);
  return v;
}

function parse(raw: string): Versions {
  const doc: unknown = JSON.parse(raw);
  if (!doc || typeof doc !== "object") throw new Error("versions.json: not an object");
  const d = doc as Record<string, unknown>;

  if (d.schema !== SCHEMA) {
    throw new Error(`versions.json: schema ${String(d.schema)}, expected ${SCHEMA}`);
  }
  if (!Array.isArray(d.modules) || !Array.isArray(d.buckets)) {
    throw new Error("versions.json: `modules` and `buckets` must be arrays");
  }
  const p = d.platform as Record<string, unknown> | undefined;
  const odoo = p?.odoo as Record<string, unknown> | undefined;
  if (!p || !odoo) throw new Error("versions.json: `platform.odoo` is required");

  const buckets = d.buckets.map((b, i) => {
    const o = b as Record<string, unknown>;
    return {
      key: str(o.key, `buckets[${i}].key`),
      label: str(o.label, `buckets[${i}].label`),
      note: str(o.note ?? "", `buckets[${i}].note`),
    } satisfies Bucket;
  });

  const modules = d.modules.map((m, i) => {
    const o = m as Record<string, unknown>;
    const at = `modules[${i}]`;
    return {
      module: str(o.module, `${at}.module`),
      bucket: str(o.bucket, `${at}.bucket`),
      name: str(o.name, `${at}.name`),
      version: str(o.version, `${at}.version`),
      summary: str(o.summary ?? "", `${at}.summary`),
      category: str(o.category ?? "", `${at}.category`),
      depends: typeof o.depends === "number" ? o.depends : 0,
      // Omitted means private. A typo must not publish a client's name — same
      // fail-closed rule as tenants.json's `visibility`.
      public: o.public === true,
      last_change: str(o.last_change ?? "", `${at}.last_change`),
      change_count: typeof o.change_count === "number" ? o.change_count : 0,
      changes: Array.isArray(o.changes)
        ? (o.changes as Record<string, unknown>[]).map((c, j) => ({
            sha: str(c.sha, `${at}.changes[${j}].sha`),
            date: str(c.date, `${at}.changes[${j}].date`),
            subject: str(c.subject, `${at}.changes[${j}].subject`),
          }))
        : [],
    } satisfies ModuleEntry;
  });

  return {
    schema: SCHEMA,
    generated_at: str(d.generated_at ?? "", "generated_at"),
    platform: {
      odoo: {
        edition: str(odoo.edition ?? "Community", "platform.odoo.edition"),
        version: str(odoo.version, "platform.odoo.version"),
        digest: str(odoo.digest ?? "", "platform.odoo.digest"),
      },
      postgres: str(p.postgres ?? "", "platform.postgres"),
      python: str(p.python ?? "", "platform.python"),
      commit: str(p.commit ?? "", "platform.commit"),
      branch: str(p.branch ?? "", "platform.branch"),
    },
    buckets,
    modules,
  };
}

export async function loadVersions(): Promise<Versions> {
  return parse(await readFile(CONFIG_PATH, "utf8"));
}

export interface PublicVersions {
  generated_at: string;
  platform: Platform;
  buckets: Bucket[];
  modules: PublicModule[];
  /** How many rows the filter removed, so the page can say so instead of
   *  quietly presenting a partial list as the whole thing. */
  hidden: number;
}

/**
 * The filtered view.
 *
 * Two things are withheld from a non-staff caller, and the second one is the
 * non-obvious one:
 *
 *  1. modules in a bucket whose names identify a client (`public: false`), and
 *  2. EVERY commit subject, on every module.
 *
 * (2) is not paranoia. Commit messages on perfectly generic modules read
 * "feat(arkaaim): …", "feat: Gentlewoman headless storefront", "fix(lint):
 * restore the warehouse-jds ruff ignore" — so publishing the changelog would
 * hand out the client list that (1) and tenants.json go to some trouble to
 * withhold. Redacting names from free text would mean maintaining a deny-list
 * and being wrong the first time someone writes a new client's name, so the
 * public view drops the subjects entirely and shows the shape of the history
 * instead: when the module last changed, and how many commits it has.
 *
 * To publish the subjects anyway, return `m.changes` unconditionally below.
 */
export async function publicVersions(includePrivate: boolean): Promise<PublicVersions> {
  const doc = await loadVersions();
  const visible = doc.modules.filter((m) => includePrivate || m.public);
  return {
    generated_at: doc.generated_at,
    platform: doc.platform,
    // Drop buckets that have nothing left in them for this viewer.
    buckets: doc.buckets.filter((b) => visible.some((m) => m.bucket === b.key)),
    modules: visible.map(({ public: _public, changes, ...rest }) => ({
      ...rest,
      changes: includePrivate ? changes : [],
    })),
    hidden: doc.modules.length - visible.length,
  };
}
