// =============================================================================
// Every number the cockpit shows comes from this file.
//
// All aggregates are built on the LINE grain and count transactions with
// COUNT(DISTINCT o.id). That choice is deliberate: a category or associate
// filter only makes sense line-by-line, and summing price_subtotal_incl over
// the whole join reproduces SUM(pos_order.amount_total) to the rupiah
// (Rp 27.923.625.458 over the full window), so nothing is lost by not using the
// order grain.
//
// Verified against prd_levis_begbal on 2026-08-14, unfiltered:
//   lines 52.581 · txn 19.268 · gross 27.923.625.458 · units 57.434
//   discount txn 8.582 · member txn 16.602
// =============================================================================

import { cache } from "react";

import { q, num } from "@/lib/db";
import { buildScope, CATEGORY_LABEL, FALLBACK_EXTENT, type Extent, type Filters } from "@/lib/filters";

/** The order-grain join every query starts from; aliases are the contract in filters.ts. */
export const ORDER_JOINS = `
  FROM pos_order_line l
  JOIN pos_order o ON o.id = l.order_id
  JOIN pos_session s ON s.id = o.session_id
  JOIN pos_config c ON c.id = s.config_id`;

/**
 * The product joins, added only when a query selects or filters on product
 * dimensions. product_template holds 348k rows here and the planner seq-scans
 * it, so carrying these joins into the KPI and trend queries costs ~60ms for
 * columns nobody reads.
 */
export const PRODUCT_JOINS = `
  JOIN product_product pp ON pp.id = l.product_id
  JOIN product_template pt ON pt.id = pp.product_tmpl_id
  LEFT JOIN product_category pc ON pc.id = pt.categ_id`;

/** `withProducts` forces the product joins even when no filter needs them. */
export function base(scope: { needsLines: boolean }, withProducts = false): string {
  return ORDER_JOINS + (withProducts || scope.needsLines ? PRODUCT_JOINS : "");
}

/**
 * First and last day with sales, read fresh on every request.
 *
 * The default date range follows the data instead of a constant, so a day
 * loaded by the retail-import feed shows up without a redeploy. `cache` dedupes
 * the call within one request — layout and page both ask for it.
 */
export const dataExtent = cache(async (): Promise<Extent> => {
  const rows = await q<Record<string, string>>(
    `SELECT MIN(date_order)::date AS start_day, MAX(date_order)::date AS end_day
     FROM pos_order`,
  );
  const r = rows[0] ?? {};
  const start = String(r.start_day ?? "").slice(0, 10);
  const end = String(r.end_day ?? "").slice(0, 10);
  return {
    start: start || FALLBACK_EXTENT.start,
    end: end || FALLBACK_EXTENT.end,
  };
});

export interface Kpis {
  gross: number;
  transactions: number;
  units: number;
  atv: number;
  upt: number;
  asp: number;
  discountShare: number;
  memberShare: number;
}

export async function kpis(f: Filters): Promise<Kpis> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT
       COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
       COUNT(DISTINCT o.id) AS transactions,
       COALESCE(SUM(l.qty), 0) AS units,
       COUNT(DISTINCT o.id) FILTER (
         WHERE l.ri_discount_type IS NOT NULL AND l.ri_discount_type <> ''
       ) AS discount_txn,
       COUNT(DISTINCT o.id) FILTER (
         WHERE o.ri_member_type IS NOT NULL AND o.ri_member_type <> ''
       ) AS member_txn
     ${base(scope)}
     WHERE ${scope.where}`,
    scope.params,
  );

  const r = rows[0] ?? {};
  const gross = num(r.gross);
  const transactions = num(r.transactions);
  const units = num(r.units);

  return {
    gross,
    transactions,
    units,
    atv: transactions ? gross / transactions : 0,
    upt: transactions ? units / transactions : 0,
    asp: units ? gross / units : 0,
    discountShare: transactions ? num(r.discount_txn) / transactions : 0,
    memberShare: transactions ? num(r.member_txn) / transactions : 0,
  };
}

export interface DailyPoint {
  day: string;
  gross: number;
  transactions: number;
}

export async function dailyTrend(f: Filters): Promise<DailyPoint[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT o.date_order::date AS day,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COUNT(DISTINCT o.id) AS transactions
     ${base(scope)}
     WHERE ${scope.where}
     GROUP BY 1
     ORDER BY 1`,
    scope.params,
  );
  return rows.map((r) => ({
    day: String(r.day).slice(0, 10),
    gross: num(r.gross),
    transactions: num(r.transactions),
  }));
}

export interface StoreRow {
  id: number;
  name: string;
  gross: number;
  transactions: number;
  units: number;
  atv: number;
  upt: number;
  memberShare: number;
}

export async function storeRanking(f: Filters): Promise<StoreRow[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT c.id, c.name,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COUNT(DISTINCT o.id) AS transactions,
            COALESCE(SUM(l.qty), 0) AS units,
            COUNT(DISTINCT o.id) FILTER (
              WHERE o.ri_member_type IS NOT NULL AND o.ri_member_type <> ''
            ) AS member_txn
     ${base(scope)}
     WHERE ${scope.where}
     GROUP BY c.id, c.name
     ORDER BY gross DESC`,
    scope.params,
  );
  return rows.map((r) => {
    const gross = num(r.gross);
    const transactions = num(r.transactions);
    const units = num(r.units);
    return {
      id: num(r.id),
      name: String(r.name),
      gross,
      transactions,
      units,
      atv: transactions ? gross / transactions : 0,
      upt: transactions ? units / transactions : 0,
      memberShare: transactions ? num(r.member_txn) / transactions : 0,
    };
  });
}

/**
 * Stores with no rows in the current scope. They vanish from a GROUP BY, and a
 * store that sold nothing is exactly what a director wants flagged — Pacific
 * Place Mall has zero transactions across the whole dataset.
 */
export async function silentStores(f: Filters): Promise<{ id: number; name: string }[]> {
  const scope = buildScope(f);
  // When the user has picked stores, the silent list is about THOSE stores.
  // Without this a filter on one store reported the other twenty-one as silent,
  // which is true of the query and useless to the reader.
  const picked = f.stores.length
    ? `AND cfg.id = ANY($${scope.params.length + 1}::int[])`
    : "";
  const rows = await q<Record<string, string>>(
    `SELECT cfg.id, cfg.name
     FROM pos_config cfg
     WHERE cfg.id NOT IN (
       SELECT c.id ${base(scope)} WHERE ${scope.where}
     )
     ${picked}
     ORDER BY cfg.name`,
    f.stores.length ? [...scope.params, f.stores] : scope.params,
  );
  return rows.map((r) => ({ id: num(r.id), name: String(r.name) }));
}

export interface StoreDaily {
  store: string;
  day: string;
  gross: number;
}

export async function storeDailyTrend(f: Filters, limit = 8): Promise<StoreDaily[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `WITH top AS (
       SELECT c.id ${base(scope)} WHERE ${scope.where}
       GROUP BY c.id
       ORDER BY SUM(l.price_subtotal_incl) DESC
       LIMIT $${scope.params.length + 1}
     )
     SELECT c.name AS store, o.date_order::date AS day,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross
     ${base(scope)}
     WHERE ${scope.where} AND c.id IN (SELECT id FROM top)
     GROUP BY 1, 2
     ORDER BY 1, 2`,
    [...scope.params, limit],
  );
  return rows.map((r) => ({
    store: String(r.store),
    day: String(r.day).slice(0, 10),
    gross: num(r.gross),
  }));
}

export interface CategoryNode {
  level1: string;
  level2: string;
  level3: string;
  gross: number;
  units: number;
}

export async function categoryMix(f: Filters): Promise<CategoryNode[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT COALESCE(NULLIF(split_part(pc.complete_name, ' / ', 1), ''), 'Uncategorised') AS level1,
            ${CATEGORY_LABEL} AS level2,
            COALESCE(NULLIF(split_part(pc.complete_name, ' / ', 3), ''), '—') AS level3,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COALESCE(SUM(l.qty), 0) AS units
     ${base(scope, true)}
     WHERE ${scope.where}
     GROUP BY 1, 2, 3
     ORDER BY gross DESC`,
    scope.params,
  );
  return rows.map((r) => ({
    level1: String(r.level1),
    level2: String(r.level2),
    level3: String(r.level3),
    gross: num(r.gross),
    units: num(r.units),
  }));
}

/**
 * Leaf categories ranked by sales, for the store drill-down. Level 1 is
 * "Textile" for essentially everything here, so the label starts at level 2.
 */
export interface CategoryRow {
  name: string;
  gross: number;
  units: number;
  transactions: number;
}

export async function topCategories(f: Filters, limit = 10): Promise<CategoryRow[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT CASE
              WHEN split_part(pc.complete_name, ' / ', 3) <> ''
                THEN split_part(pc.complete_name, ' / ', 2) || ' / ' ||
                     split_part(pc.complete_name, ' / ', 3)
              ELSE ${CATEGORY_LABEL}
            END AS name,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COALESCE(SUM(l.qty), 0) AS units,
            COUNT(DISTINCT o.id) AS transactions
     ${base(scope, true)}
     WHERE ${scope.where}
     GROUP BY 1
     ORDER BY gross DESC
     LIMIT $${scope.params.length + 1}`,
    [...scope.params, limit],
  );
  return rows.map((r) => ({
    name: String(r.name),
    gross: num(r.gross),
    units: num(r.units),
    transactions: num(r.transactions),
  }));
}

export interface ProductRow {
  code: string;
  name: string;
  category: string;
  gross: number;
  units: number;
  stores: number;
}

export async function topProducts(f: Filters, limit = 50): Promise<ProductRow[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT COALESCE(pp.default_code, '—') AS code,
            COALESCE(pt.name ->> 'en_US', l.full_product_name, '—') AS name,
            COALESCE(pc.complete_name, 'Uncategorised') AS category,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COALESCE(SUM(l.qty), 0) AS units,
            COUNT(DISTINCT c.id) AS stores
     ${base(scope, true)}
     WHERE ${scope.where}
     GROUP BY 1, 2, 3
     ORDER BY gross DESC
     LIMIT $${scope.params.length + 1}`,
    [...scope.params, limit],
  );
  return rows.map((r) => ({
    code: String(r.code),
    name: String(r.name),
    category: String(r.category),
    gross: num(r.gross),
    units: num(r.units),
    stores: num(r.stores),
  }));
}

export interface AssociateRow {
  name: string;
  store: string;
  gross: number;
  transactions: number;
  units: number;
  atv: number;
  upt: number;
  discountShare: number;
}

export async function associateLeaderboard(f: Filters): Promise<AssociateRow[]> {
  const scope = buildScope(f);
  const rows = await q<Record<string, string>>(
    `SELECT COALESCE(NULLIF(l.ri_staff_name, ''), '(tanpa nama)') AS name,
            (array_agg(c.name ORDER BY l.id))[1] AS store,
            COALESCE(SUM(l.price_subtotal_incl), 0) AS gross,
            COUNT(DISTINCT o.id) AS transactions,
            COALESCE(SUM(l.qty), 0) AS units,
            COUNT(DISTINCT o.id) FILTER (
              WHERE l.ri_discount_type IS NOT NULL AND l.ri_discount_type <> ''
            ) AS discount_txn
     ${base(scope)}
     WHERE ${scope.where}
     GROUP BY 1
     ORDER BY gross DESC`,
    scope.params,
  );
  return rows.map((r) => {
    const gross = num(r.gross);
    const transactions = num(r.transactions);
    const units = num(r.units);
    return {
      name: String(r.name),
      store: String(r.store ?? "—"),
      gross,
      transactions,
      units,
      atv: transactions ? gross / transactions : 0,
      upt: transactions ? units / transactions : 0,
      discountShare: transactions ? num(r.discount_txn) / transactions : 0,
    };
  });
}

/** Options for the filter bar. Not scoped — the pickers must show everything. */
export async function filterOptions(): Promise<{
  stores: { id: number; name: string }[];
  categories: string[];
}> {
  const [stores, categories] = await Promise.all([
    q<Record<string, string>>(`SELECT id, name FROM pos_config ORDER BY name`),
    q<Record<string, string>>(
      // Only categories that actually carry products: the tree also holds
       // parents like "Textile" and unused Odoo defaults, and offering a filter
       // that can only ever return nothing is worse than not offering it.
       `SELECT DISTINCT ${CATEGORY_LABEL} AS level2
        FROM product_category pc
        WHERE EXISTS (SELECT 1 FROM product_template pt WHERE pt.categ_id = pc.id)
        ORDER BY 1`,
    ),
  ]);
  return {
    stores: stores.map((r) => ({ id: num(r.id), name: String(r.name) })),
    categories: categories.map((r) => String(r.level2)),
  };
}

// --- Data Trust --------------------------------------------------------------

export interface ReconRow {
  month: string;
  posExTax: number;
  glIncome: number;
  diff: number;
}

/**
 * POS revenue excluding tax against posted GL income, by month.
 *
 * This is the panel that earns the dashboard its credibility: as of 2026-08-14
 * all three months reconcile to Rp 0. Deliberately NOT scoped by the filter bar
 * — it is a statement about the whole dataset, not about the current selection.
 */
export async function reconciliation(): Promise<ReconRow[]> {
  const rows = await q<Record<string, string>>(
    `WITH pos AS (
       SELECT date_trunc('month', o.date_order)::date AS m,
              SUM(l.price_subtotal) AS v
       FROM pos_order o JOIN pos_order_line l ON l.order_id = o.id
       GROUP BY 1
     ), gl AS (
       SELECT date_trunc('month', aml.date)::date AS m,
              SUM(-aml.balance) AS v
       FROM account_move_line aml
       JOIN account_account a ON a.id = aml.account_id
       WHERE a.account_type = 'income' AND aml.parent_state = 'posted'
       GROUP BY 1
     )
     SELECT COALESCE(pos.m, gl.m) AS month,
            COALESCE(pos.v, 0) AS pos_ex_tax,
            COALESCE(gl.v, 0) AS gl_income,
            COALESCE(pos.v, 0) - COALESCE(gl.v, 0) AS diff
     FROM pos FULL JOIN gl ON gl.m = pos.m
     ORDER BY 1`,
  );
  return rows.map((r) => ({
    month: String(r.month).slice(0, 10),
    posExTax: num(r.pos_ex_tax),
    glIncome: num(r.gl_income),
    diff: num(r.diff),
  }));
}

export interface Coverage {
  firstOrder: string;
  lastOrder: string;
  orders: number;
  lines: number;
  returnLines: number;
  linesWithoutStaff: number;
  distinctPaymentMethods: number;
  linesWithCost: number;
}

export async function coverage(): Promise<Coverage> {
  const rows = await q<Record<string, string>>(
    `SELECT MIN(o.date_order)::date AS first_order,
            MAX(o.date_order)::date AS last_order,
            COUNT(DISTINCT o.id) AS orders,
            COUNT(l.id) AS lines,
            COUNT(l.id) FILTER (WHERE l.qty < 0) AS return_lines,
            COUNT(l.id) FILTER (
              WHERE l.ri_staff_name IS NULL OR l.ri_staff_name = ''
            ) AS lines_without_staff,
            COUNT(l.id) FILTER (
              WHERE l.total_cost IS NOT NULL AND l.total_cost <> 0
            ) AS lines_with_cost,
            (SELECT COUNT(*) FROM pos_payment_method) AS payment_methods
     FROM pos_order o JOIN pos_order_line l ON l.order_id = o.id`,
  );
  const r = rows[0] ?? {};
  return {
    firstOrder: String(r.first_order ?? "").slice(0, 10),
    lastOrder: String(r.last_order ?? "").slice(0, 10),
    orders: num(r.orders),
    lines: num(r.lines),
    returnLines: num(r.return_lines),
    linesWithoutStaff: num(r.lines_without_staff),
    distinctPaymentMethods: num(r.payment_methods),
    linesWithCost: num(r.lines_with_cost),
  };
}
