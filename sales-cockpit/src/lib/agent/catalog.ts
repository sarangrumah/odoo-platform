// =============================================================================
// The entity catalogue the matcher resolves names against.
//
// Store and category names are read from the database, never hard-coded: a
// store that opens next month has to become answerable without a redeploy, and
// the category label has exactly one definition (CATEGORY_LABEL in filters.ts)
// which filterOptions() already applies.
// =============================================================================

import { filterOptions } from "@/lib/queries/sales";

export interface Catalog {
  stores: { id: number; name: string }[];
  categories: string[];
  byStoreId: Map<number, string>;
}

const TTL_MS = 5 * 60 * 1000;

let cached: { at: number; value: Promise<Catalog> } | null = null;

/**
 * Cached for five minutes. Every answer needs it, it changes about quarterly,
 * and a failed load must not be cached — otherwise one blip during a deploy
 * would leave the assistant unable to name a store until the process restarts.
 */
export function catalog(): Promise<Catalog> {
  const now = Date.now();
  if (cached && now - cached.at < TTL_MS) return cached.value;

  const value = filterOptions()
    .then((o) => ({
      stores: o.stores,
      categories: o.categories,
      byStoreId: new Map(o.stores.map((s) => [s.id, s.name])),
    }))
    .catch((err) => {
      cached = null;
      throw err;
    });

  cached = { at: now, value };
  return value;
}
