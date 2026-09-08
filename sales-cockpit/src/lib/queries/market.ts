// =============================================================================
// Market context: which city a store sits in, and what that market is worth.
//
// Fed by sql/002_cockpit_area.sql. Two things live here and they have very
// different readiness:
//
//   * The store -> city -> agglomeration MAPPING is complete today. It already
//     buys a better benchmark: a Bandung store judged against Bandung stores
//     instead of against Plaza Senayan.
//   * The market FIGURES (population 15-44, apparel spend per capita) are empty
//     until someone enters them from BPS. Everything that depends on them stays
//     silent rather than degrading — a fair-share index computed over half the
//     network ranks stores against a benchmark that excludes them.
//
// The tables are not Odoo models and may be absent entirely (a fresh clone, a
// different tenant), so a missing table is a normal state, not an error.
// =============================================================================

import { cache } from "react";

import { q, num } from "@/lib/db";

export interface Area {
  code: string;
  name: string;
  agglomeration: string;
  dataYear: number | null;
  population1544: number | null;
  apparelCapita: number | null;
  source: string | null;
}

export interface StoreArea {
  configId: number;
  areaCode: string;
  areaName: string;
  agglomeration: string;
  weight: number;
  confidence: string;
  /**
   * Size of the store's market, weighted by catchment.
   *
   * Rupiah of annual apparel spend where Susenas figures are loaded, otherwise
   * a headcount of the 15-44 population. Only ever compared against other
   * stores' values, so the unit cancels — but which basis was used changes what
   * the finding may claim, and travels out as `MarketContext.basis`.
   */
  marketValue: number | null;
}

export interface StoreAddress {
  configId: number;
  store: string;
  street: string | null;
  street2: string | null;
  city: string | null;
  zip: string | null;
  state: string | null;
}

export interface MarketContext {
  /** The mapping exists and covers at least some stores. */
  mapped: boolean;
  /** Every mapped area carries a population — the gate for fair-share. */
  figuresComplete: boolean;
  /** What the market size is measured in, given what is loaded. */
  basis: "belanja" | "populasi";
  /** Areas still missing the Susenas apparel spend that would weight them. */
  missingSpend: string[];
  byStore: Map<number, StoreArea>;
  areas: Area[];
  /** Areas still missing figures, named for the UI. */
  missingFigures: string[];
  /** Mappings sitting on an administrative boundary. */
  needsVerification: string[];
  /** The address Odoo holds for each store, empty until it is filled in there. */
  addresses: StoreAddress[];
}

const EMPTY: MarketContext = {
  mapped: false,
  figuresComplete: false,
  basis: "populasi",
  missingSpend: [],
  byStore: new Map(),
  areas: [],
  missingFigures: [],
  needsVerification: [],
  addresses: [],
};

/**
 * Read once per request. Absent tables resolve to EMPTY, which every caller
 * treats as "no market context", never as a failure.
 */
/**
 * Store addresses as Odoo holds them: pos_config -> operating_unit -> res_partner.
 *
 * Every operating_unit.partner_id in prd_levis_begbal is NULL as of 20-Aug-2026,
 * so this returns rows with empty address fields until the addresses are written
 * into Odoo. It is read from Odoo rather than copied into cockpit_area on
 * purpose — the ERP stays the single place a store's address is maintained.
 */
async function storeAddresses(): Promise<StoreAddress[]> {
  try {
    const rows = await q<Record<string, string>>(
      `SELECT c.id, c.name AS store,
              p.street, p.street2, p.city, p.zip, s.name AS state
       FROM pos_config c
       LEFT JOIN operating_unit ou ON ou.id = c.operating_unit_id
       LEFT JOIN res_partner p ON p.id = ou.partner_id
       LEFT JOIN res_country_state s ON s.id = p.state_id
       ORDER BY c.name`,
    );
    return rows.map((r) => ({
      configId: num(r.id),
      store: String(r.store),
      street: r.street ? String(r.street) : null,
      street2: r.street2 ? String(r.street2) : null,
      city: r.city ? String(r.city) : null,
      zip: r.zip ? String(r.zip) : null,
      state: r.state ? String(r.state) : null,
    }));
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code !== "42P01" && code !== "42501") throw error;
    console.warn(`[market] store addresses unavailable (${code})`);
    return [];
  }
}

export const marketContext = cache(async (): Promise<MarketContext> => {
  let rows: Record<string, string>[];
  try {
    rows = await q<Record<string, string>>(
      `SELECT sa.pos_config_id, sa.area_code, sa.catchment_weight, sa.confidence, sa.note,
              a.name, a.agglomeration, a.data_year, a.population_15_44,
              a.expenditure_apparel_capita, a.source
       FROM cockpit_store_area sa
       JOIN cockpit_area a ON a.code = sa.area_code`,
    );
  } catch (error) {
    // 42P01 = undefined_table. Anything else is a real problem worth surfacing
    // in the log, but the page still renders without market context.
    const code = (error as { code?: string }).code;
    if (code !== "42P01" && code !== "42501") throw error;
    console.warn(`[market] context unavailable (${code}); rules that need it stay silent`);
    return EMPTY;
  }

  const addresses = await storeAddresses();
  if (!rows.length) return { ...EMPTY, addresses };

  const byStore = new Map<number, StoreArea>();
  const areas = new Map<string, Area>();
  const missing = new Set<string>();
  const missingSpend = new Set<string>();
  const unverified: string[] = [];

  for (const r of rows) {
    const pop = r.population_15_44 === null ? null : num(r.population_15_44);
    const spend =
      r.expenditure_apparel_capita === null ? null : num(r.expenditure_apparel_capita);
    const weight = num(r.catchment_weight) || 1;
    const name = String(r.name);

    // Population is the gate; spend only sharpens it. Treating a missing spend
    // as a missing figure kept the rule switched off for data BPS does not
    // publish anywhere we can reach.
    if (!pop) missing.add(name);
    if (!spend) missingSpend.add(name);
    if (String(r.confidence) === "perlu verifikasi") {
      unverified.push(`${name} — ${String(r.note ?? "")}`.trim());
    }

    byStore.set(num(r.pos_config_id), {
      configId: num(r.pos_config_id),
      areaCode: String(r.area_code),
      areaName: name,
      agglomeration: String(r.agglomeration),
      weight,
      confidence: String(r.confidence),
      marketValue: pop ? pop * (spend ?? 1) * weight : null,
    });

    areas.set(String(r.area_code), {
      code: String(r.area_code),
      name,
      agglomeration: String(r.agglomeration),
      dataYear: r.data_year === null ? null : num(r.data_year),
      population1544: pop,
      apparelCapita: spend,
      source: r.source === null ? null : String(r.source),
    });
  }

  return {
    mapped: byStore.size > 0,
    figuresComplete: missing.size === 0,
    basis: missingSpend.size === 0 ? "belanja" : "populasi",
    missingSpend: [...missingSpend].sort(),
    byStore,
    areas: [...areas.values()],
    missingFigures: [...missing].sort(),
    needsVerification: unverified,
    addresses,
  };
});
