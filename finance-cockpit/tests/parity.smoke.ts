// =============================================================================
// Parity: does this dashboard agree with the Odoo reports themselves?
//
// This is the only test that answers that question. The fourteen checks on the
// tie page prove the dashboard is consistent with the ledger and with itself;
// they cannot prove it computes what `custom.report.aged.payable` computes.
// Here we log in to Odoo, call the real reports through `get_report_table` with
// the same filters, and compare the grand totals.
//
// It needs a real Odoo login with accounting access, which this application
// deliberately does not hold — so it is never run by the container and never in
// CI. Run it by hand before a deploy and paste the output into the README:
//
//   docker run --rm --network odoo19-platform-net \
//     -v "$PWD:/app" -w /app --env-file ../.env \
//     -e FINANCE_DB_HOST=postgres \
//     -e FINANCE_PARITY_LOGIN=... -e FINANCE_PARITY_PASSWORD=... \
//     node:22-alpine npx tsx tests/parity.smoke.ts [YYYY-MM-DD]
//
// Exits non-zero on any mismatch beyond the currency rounding.
// =============================================================================

import { createRequire } from "node:module";
import { randomUUID } from "node:crypto";

const require_ = createRequire(import.meta.url);
const react = require_("react") as { cache?: <T>(fn: T) => T };
if (typeof react.cache !== "function") react.cache = (fn) => fn;

const ODOO = (process.env.FINANCE_ODOO_URL ?? "http://odoo-front:8069").replace(/\/+$/, "");
const DB = process.env.FINANCE_DB_NAME ?? "prd_levis_begbal";
const LOGIN = process.env.FINANCE_PARITY_LOGIN ?? "";
const PASSWORD = process.env.FINANCE_PARITY_PASSWORD ?? "";

const money = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

async function rpc(path: string, params: unknown, cookie?: string): Promise<Response> {
  return fetch(`${ODOO}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: randomUUID(), params }),
    signal: AbortSignal.timeout(180_000),
  });
}

async function login(): Promise<string> {
  const response = await rpc("/web/session/authenticate", { db: DB, login: LOGIN, password: PASSWORD });
  const body = (await response.json()) as { result?: { uid?: number | false } };
  if (!body.result?.uid) throw new Error("Odoo rejected the parity credentials");
  const cookie = response.headers.get("set-cookie");
  if (!cookie) throw new Error("Odoo returned no session cookie");
  return cookie.split(";")[0];
}

interface ReportTable {
  columns: { header: string; field: string; kind: string }[];
  lines: { type?: string; values: Record<string, unknown> }[];
}

async function reportTable(
  cookie: string,
  model: string,
  options: Record<string, unknown>,
): Promise<ReportTable> {
  const response = await rpc(
    "/web/dataset/call_kw",
    {
      model,
      method: "get_report_table",
      args: [options],
      kwargs: {},
    },
    cookie,
  );
  const body = (await response.json()) as { result?: ReportTable; error?: { data?: { message?: string } } };
  if (!body.result) throw new Error(`${model}: ${body.error?.data?.message ?? "no result"}`);
  return body.result;
}

/** Sum a numeric column over the rows Odoo marks as ordinary data. */
function columnTotal(table: ReportTable, field: string, rowType?: string): number {
  let total = 0;
  for (const line of table.lines) {
    if (rowType && line.type !== rowType) continue;
    if (!rowType && line.type && line.type !== "data") continue;
    const raw = line.values?.[field];
    const value = typeof raw === "number" ? raw : Number(String(raw ?? "").replace(/[^\d.-]/g, ""));
    if (Number.isFinite(value)) total += value;
  }
  return total;
}

interface Comparison {
  name: string;
  dashboard: number;
  odoo: number;
}

async function main() {
  if (!LOGIN || !PASSWORD) {
    console.error(
      "FINANCE_PARITY_LOGIN and FINANCE_PARITY_PASSWORD are required.\n" +
        "This test calls the Odoo reports as a real accounting user; the dashboard's own\n" +
        "credentials cannot do it, and that is by design.",
    );
    process.exit(2);
  }

  const { defaultCompanyIds, companyRounding } = await import("../src/lib/queries/common");
  const { trialBalance } = await import("../src/lib/queries/close");
  const { agingByPartner, totalsOf } = await import("../src/lib/queries/ap");
  const { summaryByAccount } = await import("../src/lib/queries/openitems");
  const { today, startOfMonth } = await import("../src/lib/finance-filters");
  const { pool } = await import("../src/lib/db");

  const asOf = process.argv[2] ?? today();
  const from = startOfMonth(asOf);
  const companies = await defaultCompanyIds();
  const rounding = await companyRounding(companies[0]);

  const cookie = await login();
  const options = {
    date_from: from,
    date_to: asOf,
    company_ids: companies,
    journal_ids: [],
    account_ids: [],
    partner_ids: [],
    posted_only: true,
    comparison: false,
  };

  console.log(`as of ${asOf} (movement from ${from}) · db ${DB}\n`);

  const comparisons: Comparison[] = [];

  // --- Trial balance ---------------------------------------------------------
  const tbRows = await trialBalance({ from, to: asOf, companies });
  const tbTable = await reportTable(cookie, "custom.report.trial.balance", options);
  comparisons.push({
    name: "Trial balance — closing debit",
    dashboard: tbRows.reduce((s, r) => s + r.closingDebit, 0),
    odoo: columnTotal(tbTable, "closing_debit"),
  });
  comparisons.push({
    name: "Trial balance — closing credit",
    dashboard: tbRows.reduce((s, r) => s + r.closingCredit, 0),
    odoo: columnTotal(tbTable, "closing_credit"),
  });

  // --- Aged payable ----------------------------------------------------------
  const aging = totalsOf(await agingByPartner("payable", { asOf, companies }));
  const apTable = await reportTable(cookie, "custom.report.aged.payable", options);
  comparisons.push({
    name: "Aged payable — grand total",
    dashboard: aging.total,
    odoo: columnTotal(apTable, "total"),
  });

  // --- GL open items ---------------------------------------------------------
  const openItems = await summaryByAccount({ asOf, companies });
  const oiTable = await reportTable(cookie, "custom.report.gl.open.items", {
    ...options,
    layout: "summary",
  });
  comparisons.push({
    name: "GL open items — outstanding",
    dashboard: openItems.reduce((s, r) => s + r.outstanding, 0),
    odoo: columnTotal(oiTable, "outstanding"),
  });

  let failed = 0;
  for (const c of comparisons) {
    const diff = c.dashboard - c.odoo;
    const ok = Math.abs(diff) < rounding / 2;
    if (!ok) failed += 1;
    console.log(
      `${ok ? "OK  " : "FAIL"}  ${c.name}\n` +
        `      dasbor ${money.format(c.dashboard)} · odoo ${money.format(c.odoo)} · selisih ${money.format(diff)}`,
    );
  }

  console.log(`\n${comparisons.length - failed} of ${comparisons.length} match.`);
  await pool().end();
  if (failed) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
