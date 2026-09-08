// =============================================================================
// Postgres access for the cockpit.
//
// The pool logs in as `cockpit_ro`, whose sessions are read-only at the server
// (`ALTER ROLE ... SET default_transaction_read_only = on`) and which only holds
// SELECT on the seventeen tables the dashboard reads. Nothing here can write to
// prd_levis_begbal even if a query tried to, and pg_hba only lets the role reach
// that one database.
// =============================================================================

import { Pool, types, type QueryResultRow } from "pg";

// node-postgres turns a DATE column into a JS Date at *local* midnight. Two
// things go wrong with that here: `String(date).slice(0, 10)` yields "Thu Jun 1"
// instead of "2026-06-12" (every date in the UI read "Invalid Date"), and the
// local-midnight conversion can shift the day across a timezone boundary.
// Handing DATE back as the raw 'YYYY-MM-DD' text avoids both — the queries
// already cast to ::date precisely so the value is a calendar day, not an
// instant.
types.setTypeParser(types.builtins.DATE, (value) => value);

declare global {
  // Next's dev server re-evaluates modules on every edit; without this the pool
  // would be recreated on each reload until the connection limit is reached.
  // eslint-disable-next-line no-var
  var __cockpitPool: Pool | undefined;
}

function createPool(): Pool {
  const password = process.env.COCKPIT_DB_PASSWORD;
  if (!password) throw new Error("COCKPIT_DB_PASSWORD is not set");

  return new Pool({
    host: process.env.COCKPIT_DB_HOST ?? "postgres",
    port: Number(process.env.COCKPIT_DB_PORT ?? 5432),
    database: process.env.COCKPIT_DB_NAME ?? "prd_levis_begbal",
    user: process.env.COCKPIT_DB_USER ?? "cockpit_ro",
    password,
    max: Number(process.env.COCKPIT_DB_POOL_MAX ?? 8),
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
    application_name: "sales-cockpit",
  });
}

export function pool(): Pool {
  if (!global.__cockpitPool) global.__cockpitPool = createPool();
  return global.__cockpitPool;
}

/** Run a parameterised query. Never interpolate values into `text`. */
export async function q<T extends QueryResultRow>(
  text: string,
  params: unknown[] = [],
): Promise<T[]> {
  const started = performance.now();
  try {
    const result = await pool().query<T>(text, params);
    const ms = performance.now() - started;
    if (ms > 300) {
      console.warn(`[db] slow query ${ms.toFixed(0)}ms: ${text.slice(0, 90).replace(/\s+/g, " ")}`);
    }
    return result.rows;
  } catch (error) {
    console.error(`[db] query failed: ${text.slice(0, 120).replace(/\s+/g, " ")}`, error);
    throw error;
  }
}

/** Postgres returns numeric/bigint as strings to preserve precision. */
export function num(value: unknown): number {
  if (value === null || value === undefined) return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}
