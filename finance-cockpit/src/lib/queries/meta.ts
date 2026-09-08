// Small lookups the shell needs before any page runs.

import { cache } from "react";

import { q } from "@/lib/db";

/**
 * The last day carrying a posted line.
 *
 * Offered as a cut-off preset so "show me everything" does not mean "today",
 * which on a quiet day is the same thing and on a busy one is not.
 */
export const lastPostedDate = cache(async (): Promise<string | null> => {
  const rows = await q<Record<string, string | null>>(
    `SELECT MAX(date)::text AS last_date FROM account_move_line WHERE parent_state = 'posted'`,
  );
  const value = rows[0]?.last_date;
  return value ? String(value).slice(0, 10) : null;
});
