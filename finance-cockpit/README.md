# Levi's Finance Cockpit

A read-only Finance & Accounting dashboard over `prd_levis_begbal`, served at
`/finance`. Next.js 15 App Router, React server components, plain SQL against a
Postgres role that cannot write.

Separate from `sales-cockpit` on purpose: this app reads the ledger, the bank
statements and the POS clearing runs, and that reach should not ride on a sales
dashboard's credential. Different container, different Postgres role, different
pg_hba line.

## What it answers

| Halaman | Pertanyaan |
|---|---|
| `/finance/ap` | Berapa hutang terbuka, siapa yang lewat jatuh tempo, apa yang jatuh tempo empat pekan ke depan, tagihan mana yang belum lunas, pembayaran mana yang menggantung |
| `/finance/openitems` | Apa yang belum tuntas di setiap akun rekonsiliasi per tanggal potong, dan — setelah netting FIFO — siapa yang sebenarnya masih berhutang. Fokus GR/IR |
| `/finance/pos` | Seberapa jauh piutang POS per tender sudah dipertemukan dengan settlement bank; run clearing, diagnostik, baris rekening koran yang memblokir lock date |
| `/finance/close` | Apa yang masih menghalangi tutup buku: draft, jurnal tak seimbang, lock exception, lompatan nomor, baris tanpa analitik |
| `/finance/tie` | **Bukti** bahwa keempat halaman di atas boleh dipercaya |

## The promise, and how it is kept

The requirement was that the figures tie to the Odoo reports to the rupiah. Two
things enforce that.

**`/finance/tie` runs fourteen checks live** on every page load — no number in it
is written into the code. Three of them are expected NOT to be zero, and they say
so up front, because a difference that is explained is evidence and a difference
that is hidden is not.

**`npm run test:parity`** is the only real proof. It logs in to Odoo as an
accounting user, calls `custom.report.trial.balance`,
`custom.report.aged.payable` and `custom.report.gl.open.items` through
`get_report_table` with the same filters, and compares the totals. The dashboard
cannot run it — it holds no such credentials, deliberately.

### Verified against prd_levis_begbal on 2026-08-28, as of that date

```
OK     1. Neraca saldo tutup seimbang         debit = kredit = 166.325.664.540
OK     2. Seluruh buku besar berimbang        debit = kredit = 521.967.194.708
OK     3. Aging hutang = saldo GL             -55.058.266.937
OK     4. Aging piutang = saldo GL             13.702.159.829
note   5. Jembatan paritas vs as-of           selisih 719.838.546 (dijelaskan)
OK     6. Open items vs custom_reconcile_account   sisa tak dijelaskan 0
OK     7. Identitas penyelesaian               0
OK     8. Invarian netting                     4.124.116.810 → 4.124.116.810
OK     9. GR/IR = saldo GL                     4.124.116.810
note  10/11/12. Clearing POS — belum ada run terposting
OK    13. Jurnal dikecualikan                  0 (tidak ada yang ditandai)
note  14. Paritas Odoo — jalankan test:parity

14 of 14 reconcile or are explained; 0 failed.
```

## Known reconciling items

These are real, understood, and priced. They are the reason several checks
report a difference and still pass.

**Pembayaran bertanggal periode berikutnya — Rp 719.838.546.** 29 partial
reconciles carry `max_date = 2026-09-01`: payments dated September applied to
August bills. `max_date` is the later of the two lines' *accounting* dates, not
the moment someone clicked reconcile, so those bills were genuinely still open on
28 August. The as-of reading counts them; `amount_residual` does not. This is
check 5's bridge and part of check 6's.

**Baris bertanggal setelah tanggal potong — Rp 38.775.000.** 25 unreconciled
lines on account 1115200001 dated after the cut-off. `custom_reconcile_account`
counts them because it applies no date filter at all; an as-of reading cannot.

**Aged reports do not exclude journals.** `custom.report.aged.receivable` reads
`account.move.line` directly and never filters `x_custom_report_excluded`, while
the trial balance does. The difference is deliberate in Odoo, so it is preserved
here. No journal carries the flag in this database today, so the gap is currently
zero — the filter stays so the two move together the day one does.

**Six permanent lock exceptions (ids 49–54)** are intentional: June 2026 postings
were opened on purpose and left open. `/finance/close` states the expected count
rather than hard-coding the ids, so a seventh shows up as a change.

**Piutang POS tidak punya lawan transaksi.** All 10.990 receivable lines without a
partner sit on accounts 1106…, because POS records no customer. `/finance/close`
excludes those from the "no partner" defect count and says how many it excluded.

## Database access

The app logs in as `finance_ro`, created by `sql/001_finance_ro_role.sql`:

- `LOGIN`, no superuser, no createdb, no createrole
- `default_transaction_read_only = on` — `UPDATE` and `CREATE TABLE` are refused
  by the server, not by application code
- `SELECT` on ~36 named tables and three views; `res_users` is **not** among them
- `statement_timeout = 30s`

The cost of excluding `res_users`: `create_uid` on a journal entry can only ever
be shown as a number. That is the trade, taken deliberately.

Applying it (idempotent, run both halves):

```bash
docker cp sql/001_finance_ro_role.sql odoo19-platform-postgres:/tmp/
docker exec -e PGPASSWORD="$PGPASS" odoo19-platform-postgres \
  psql -U odoo -d postgres -v finance_password="$FINPASS" -f /tmp/001_finance_ro_role.sql
docker exec -e PGPASSWORD="$PGPASS" odoo19-platform-postgres \
  psql -U odoo -d prd_levis_begbal -v finance_password="$FINPASS" -f /tmp/001_finance_ro_role.sql
```

### One manual step: pg_hba

`pg_hba.conf` is a per-user allowlist ending in an explicit `reject`, so a new
role cannot connect until it is named there. The lines are already in
`postgres/pg_hba.conf`, **above** the two `reject` lines:

```
host    prd_levis_begbal  finance_ro    172.16.0.0/12           scram-sha-256
host    prd_levis_begbal  finance_ro    192.168.0.0/16          scram-sha-256
host    prd_levis_begbal  finance_ro    10.0.0.0/8              scram-sha-256
```

The file is a **single-file bind mount**, so it must be edited in place — writing
a new file gives it a new inode and the container keeps serving the old one.
`cat new > /opt/odoo-platform/postgres/pg_hba.conf` is right; `mv` and `sed -i`
are not. Then:

```bash
docker exec odoo19-platform-postgres psql -U odoo -d postgres -c "SELECT pg_reload_conf()"
docker exec odoo19-platform-postgres psql -U odoo -d postgres \
  -c "SELECT database, user_name, address, error FROM pg_hba_file_rules WHERE user_name::text LIKE '%finance_ro%'"
```

`error` must be NULL on all three rows.

### Proving the boundary

```
read works              finance_ro|173610
write refused           ERROR: cannot execute CREATE TABLE in a read-only transaction
other database refused  FATAL: pg_hba.conf rejects connection for ... database "postgres"
ungranted table refused ERROR: permission denied for table res_users
```

## Running it

```bash
docker compose build finance-cockpit
docker compose up -d --no-deps finance-cockpit     # --no-deps matters; see below
curl -s http://127.0.0.1:18132/finance/api/health
```

**Always `--no-deps`.** A bare `docker compose up -d finance-cockpit` from this
directory will try to bring up its dependencies, and this repo's compose files
are split across overlays — that is how a previous session took production
Postgres down.

The port is loopback-only. Caddy is the front door.

## Performance

Measured on the live database, 2026-08-28:

| Query | Time |
|---|---|
| As-of residual, all reconcile accounts (70.735 open lines) | ~1,0 s |
| Per-account outstanding summary | ~0,5 s |
| `/finance/openitems/778` — 58.840 rows fetched, netted, rendered | ~1,8 s |
| `/finance/tie` — all fourteen checks | ~2,5 s |
| `/finance/close` | ~2,9 s |

The shape that matters: the settlement is gathered with `UNION ALL` and then
aggregated, never as `LEFT JOIN account_partial_reconcile ON (debit_move_id = id
OR credit_move_id = id)`. Postgres cannot use an index for an `OR` across two
columns and that form degrades to a nested loop over 173k lines.

Netting is always scoped to one account. That is safe because netting never
crosses accounts, and it is what keeps the largest page under two seconds.

## Tests

```bash
npm run typecheck
npm test              # pure units: bucket boundaries, netting invariants
npm run test:tie      # all fourteen checks against the live database
npm run test:parity   # against the Odoo reports; needs an accounting login
```

`npm test` needs no database. The two smoke tests do:

```bash
docker run --rm --network odoo19-platform-net \
  -v "$PWD:/app" -w /app --env-file ../.env \
  -e FINANCE_DB_HOST=postgres node:22-alpine npx tsx tests/tie.smoke.ts
```

`tests/netting.test.ts` property-tests the invariant that makes the whole design
work: FIFO only moves rupiah between rows, so `sum(outstanding)` always equals
`sum(residualAsOf)`. That is why the headline figure on `/finance/openitems` is
computed **without** netting — it cannot be broken by a bug in the port, and
check 8 asserts the two agree.

## Traps this code already stepped in

- **`account_account.code` is not a column.** It is `code_store`, JSONB, keyed by
  the ROOT company id as a string. `code_store ->> 1` is a different operator
  that returns null for every account.
- **`account_account.name`, `account_journal.name`, `account_analytic_account.name`
  and `account_analytic_plan.name` are JSONB.** `COALESCE(aa.name, 'fallback')`
  fails with *invalid input syntax for type json* rather than falling back.
  `res_partner.name` is a plain varchar.
- **IDR `rounding` is 0.01, not 1.0.** The zero threshold is 0.005. A different
  epsilon either invents thousands of phantom rows on GR/IR or erases real ones.
- **`levis.pos.clearing` run totals are compute fields without `store=True`.**
  There is no `total_gross` column. Everything run-level is re-aggregated from
  `levis_pos_clearing_line`. The before/after balance snapshots *are* real
  columns.
- **`account_bank_statement_line` `_inherits` `account.move`,** so `date`,
  `company_id` and `currency_id` are not on its table. Always join.
- **A partial only counts when both sides are posted.** None violate this today,
  which is exactly why the guard is written now.

## Schema facts

`docs/SCHEMA-FACTS.md` records what was measured on the database rather than read
from the addons in `/home`, which lag production. Re-run that inventory before
trusting any column name in a new query.
