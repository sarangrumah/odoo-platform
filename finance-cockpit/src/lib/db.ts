// =============================================================================
// Postgres access for the finance cockpit.
//
// The pool logs in as `finance_ro`, whose sessions are read-only at the server
// (`ALTER ROLE ... SET default_transaction_read_only = on`) and which only
// holds SELECT on the tables listed in sql/001_finance_ro_role.sql. Nothing
// here can write to prd_levis_begbal even if a query tried to, and pg_hba only
// lets the role reach that one database.
//
// A separate role from the sales dashboard's `cockpit_ro` on purpose: finance
// reads the ledger, the bank statements and the clearing runs, and that grant
// list has no business being attached to a sales dashboard's credential.
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
  var __financePool: Pool | undefined;
}

function createPool(): Pool {
  const password = process.env.FINANCE_DB_PASSWORD;
  if (!password) throw new Error("FINANCE_DB_PASSWORD is not set");

  return new Pool({
    host: process.env.FINANCE_DB_HOST ?? "postgres",
    port: Number(process.env.FINANCE_DB_PORT ?? 5432),
    database: process.env.FINANCE_DB_NAME ?? "prd_levis_begbal",
    user: process.env.FINANCE_DB_USER ?? "finance_ro",
    password,
    max: Number(process.env.FINANCE_DB_POOL_MAX ?? 8),
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
    application_name: "finance-cockpit",
  });
}

export function pool(): Pool {
  if (!global.__financePool) global.__financePool = createPool();
  return global.__financePool;
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
