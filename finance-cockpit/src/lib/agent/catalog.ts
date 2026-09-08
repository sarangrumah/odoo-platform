// =============================================================================
// The entity catalogue the matcher resolves names against.
//
// Account and vendor names come from the database, never from a hard-coded
// list: a vendor added next week has to become answerable without a redeploy,
// and the account code is read through the same company-dependent JSONB path
// the rest of the app uses, so the assistant can never disagree with a page
// about what an account is called.
//
// Only names and ids are held. No balances, no amounts — this is a phonebook,
// and every figure comes from a skill calling the same queries the pages do.
// =============================================================================

import { q, num } from "@/lib/db";
import { accountCodeSql, accountNameSql, rootCompanyId } from "@/lib/queries/common";

export interface CatalogAccount {
  id: number;
  code: string;
  name: string;
  accountType: string;
}

export interface CatalogPartner {
  id: number;
  name: string;
}

export interface Catalog {
  accounts: CatalogAccount[];
  partners: CatalogPartner[];
  byAccountId: Map<number, CatalogAccount>;
  byPartnerId: Map<number, string>;
}

const TTL_MS = 5 * 60 * 1000;

let cached: { at: number; value: Promise<Catalog> } | null = null;

async function load(): Promise<Catalog> {
  const root = await rootCompanyId();

  const [accountRows, partnerRows] = await Promise.all([
    q<Record<string, string | null>>(
      `SELECT aa.id, ${accountCodeSql("$1")} AS code, ${accountNameSql()} AS name, aa.account_type
         FROM account_account aa
        WHERE aa.active
        ORDER BY code`,
      [String(root)],
    ),
    // Only counterparties that actually appear on a reconcilable line: the
    // partner table runs to tens of thousands of rows, almost all of them
    // customers who never touch the ledger, and matching a question against
    // those is both slow and a source of false hits.
    q<Record<string, string | null>>(
      `SELECT DISTINCT rp.id, rp.name
         FROM res_partner rp
         JOIN account_move_line aml ON aml.partner_id = rp.id
         JOIN account_account aa ON aa.id = aml.account_id
        WHERE aa.reconcile
          AND aml.parent_state = 'posted'
          AND rp.name IS NOT NULL
        ORDER BY rp.name`,
    ),
  ]);

  const accounts: CatalogAccount[] = accountRows.map((r) => ({
    id: num(r.id),
    code: String(r.code ?? ""),
    name: String(r.name ?? ""),
    accountType: String(r.account_type ?? ""),
  }));

  const partners: CatalogPartner[] = partnerRows.map((r) => ({
    id: num(r.id),
    name: String(r.name ?? ""),
  }));

  return {
    accounts,
    partners,
    byAccountId: new Map(accounts.map((a) => [a.id, a])),
    byPartnerId: new Map(partners.map((p) => [p.id, p.name])),
  };
}

/**
 * Cached for five minutes. Every answer needs it, the chart of accounts changes
 * about quarterly, and a failed load must NOT be cached — otherwise one blip
 * during a deploy would leave the assistant unable to name an account until the
 * process restarts.
 */
export function catalog(): Promise<Catalog> {
  const now = Date.now();
  if (cached && now - cached.at < TTL_MS) return cached.value;

  const value = load().catch((err) => {
    cached = null;
    throw err;
  });

  cached = { at: now, value };
  return value;
}
