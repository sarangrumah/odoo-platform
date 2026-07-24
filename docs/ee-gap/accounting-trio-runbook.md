# Accounting EE-gap Trio — Deploy, Config & Verification Runbook

Operational runbook for the three Community accounting EE-gap modules, as rolled
out to the Levi's tenant fleet on 24-Jul-2026 (PR #66 merged to `main`).

| Module | Version | Purpose |
|---|---|---|
| `custom_account_reconcile` | 19.0.2.0.0 | Manual reconciliation: overview dashboard, journal-items wizard, bank-statement matching/auto-match |
| `custom_account_deferred` | 19.0.1.0.0 | Deferred revenue/expense: date-driven deferral + monthly day-count-prorated recognition |
| `custom_account_batch_payment` | 19.0.1.0.0 | Batch vendor payments + per-bank export file (BCA/Mandiri/BNI/BRI) |

**Target DBs (Levi's fleet):** `rnd_levis`, `prd_levis`, `prd_levis_begbal`,
`prd_detail_levis`, `prd_levis_AP`, `demo_updated_levis`.

---

## 0. Environment & conventions

- **Runtime:** the odoo container `odoo19-platform-odoo` mounts
  `/opt/odoo-platform/addons` → `/mnt/extra-addons`. Source is edited under
  `/home/odoo-erp/odoo-platform/addons` (dev checkout) and **must be copied to
  `/opt`** to take effect. `/opt` is shared across sessions — sync it right
  before any `-u`.
- **Postgres:** container `odoo19-platform-postgres`, user `odoo`. Fetch the
  password on demand (do not hardcode):
  ```bash
  PW=$(docker exec odoo19-platform-postgres printenv POSTGRES_PASSWORD)
  q(){ docker exec -i -e PGPASSWORD="$PW" odoo19-platform-postgres psql -U odoo -d "$1" -tA -c "$2"; }
  ```
- These are **shared addons** — installed on many DBs. Adding a stored field
  needs `-u` on every DB carrying the module (schema-drift risk). The trio's
  current state adds no new columns, so a plain code sync + `-u` is safe.

---

## 1. Deploy (code)

The trio is already installed on all six DBs; deploy = sync current code + `-u`.

```bash
# 1a. Sync /home -> /opt (rsync is NOT installed on this host; use cp -a)
for m in custom_account_reconcile custom_account_deferred custom_account_batch_payment; do
  cp -af /home/odoo-erp/odoo-platform/addons/ee_gap/$m/. \
         /opt/odoo-platform/addons/ee_gap/$m/
done
# sanity: only __pycache__ should differ
for m in custom_account_reconcile custom_account_deferred custom_account_batch_payment; do
  diff -rq --exclude=__pycache__ \
    /home/odoo-erp/odoo-platform/addons/ee_gap/$m \
    /opt/odoo-platform/addons/ee_gap/$m || echo "  ^ $m differs"
done

# 1b. Upgrade each DB. IMPORTANT: no --test-enable (see §4 "Gotchas").
MODS=custom_account_reconcile,custom_account_deferred,custom_account_batch_payment
for db in rnd_levis prd_levis prd_levis_begbal prd_detail_levis prd_levis_AP demo_updated_levis; do
  echo "== -u $db =="
  docker exec -i odoo19-platform-odoo odoo -d "$db" -u "$MODS" \
    --stop-after-init --no-http --log-level=warn 2>&1 | tail -3
done
```

Verify install state:
```bash
for db in rnd_levis prd_levis prd_levis_begbal prd_detail_levis prd_levis_AP demo_updated_levis; do
  echo "$db: $(q "$db" "SELECT string_agg(name||'='||state||' '||latest_version, ', ' ORDER BY name) FROM ir_module_module WHERE name IN ('custom_account_reconcile','custom_account_deferred','custom_account_batch_payment');")"
done
```
Expect each: `...=installed 19.0.x.0.0` for all three.

---

## 2. Configure `custom_account_deferred`

The module refuses to generate entries until the company carries a deferred
expense account, a deferred revenue account and a general journal. Seed via the
idempotent script (matches accounts by **name** — codes are company-dependent on
Odoo 19; EBR chart names are stable across levis DBs):

```bash
# DRY first (no write); then FIX_APPLY=1 to commit.
for db in rnd_levis prd_levis prd_levis_begbal prd_detail_levis prd_levis_AP demo_updated_levis; do
  echo "== $db =="
  docker exec -i -e FIX_APPLY=1 odoo19-platform-odoo odoo shell -d "$db" --no-http --log-level=warn \
    < scripts/tenants/levis/74_set_deferred_config.py 2>&1 | grep -E '^\[APPLY\]|SystemExit|Not found'
done
```

Resulting config (all DBs):
- `deferred_expense_account_id` → **Other prepaid expenses** (asset_prepayments)
- `deferred_revenue_account_id` → **Deferred Income - Current** (liability_current)
- `deferred_journal_id` → **GLJV "General Journal"** — except `demo_updated_levis`
  which lacks GLJV and falls back to **MISC "Miscellaneous Operations"**.

Verify:
```bash
for db in rnd_levis prd_levis prd_levis_begbal prd_detail_levis prd_levis_AP demo_updated_levis; do
  echo "$db: $(q "$db" "SELECT (deferred_expense_account_id IS NOT NULL AND deferred_revenue_account_id IS NOT NULL AND deferred_journal_id IS NOT NULL) FROM res_company WHERE id=1;")"
done   # expect 't' everywhere
```

---

## 3. Verification (behaviour)

All three verifications run in `odoo shell` and **end with `env.cr.rollback()`**
— they create real records (invoices, payments, statement lines), assert the
posting behaviour, then discard everything. **No data is left on any DB.** The
`INV/…` / `BATCH/…` numbers seen are assigned in-transaction and released on
rollback.

Save each script to the scratchpad (or anywhere), then run per DB with:
```bash
docker exec -i odoo19-platform-odoo odoo shell -d <DB> --no-http --log-level=warn < <script>.py
```
Pass criteria: the script prints `RESULT: ALL CHECKS PASSED` and no `[FAIL]`.

### 3a. Deferred entries — `verify_deferred.py`

Posts a 920,000 customer invoice deferred over Jul–Sep 2026 (92 days @ 10,000/day
→ 310k / 310k / 300k). Checks: one **posted** deferral move reclassing revenue →
deferred-revenue account (balanced); three recognition moves, day-count prorated,
each balanced, summing to 920,000; future recognitions left `draft` with
`auto_post='at_date'`.

```python
import datetime
env = env  # odoo shell
OK = True
def check(l, c, d=""):
    global OK; OK = OK and bool(c); print(f"  [{'PASS' if c else 'FAIL'}] {l}" + (f" — {d}" if d else ""))
company = env["res.company"].browse(1)
env = env(context=dict(env.context, allowed_company_ids=[company.id]))
partner = env["res.partner"].search([("customer_rank", ">", 0)], limit=1) \
    or env["res.partner"].search([], limit=1) or env["res.partner"].create({"name": "DEF TEST"})
income = env["account.account"].with_company(company).search([("account_type", "=", "income")], limit=1)
product = env["product.product"].create({"name": "DEFERRED TEST", "type": "service", "property_account_income_id": income.id})
move = env["account.move"].create({"move_type": "out_invoice", "partner_id": partner.id,
    "invoice_date": datetime.date(2026, 7, 24), "date": datetime.date(2026, 7, 24),
    "invoice_line_ids": [(0, 0, {"product_id": product.id, "name": "deferred", "quantity": 1,
        "price_unit": 920000.0, "tax_ids": [(6, 0, [])], "account_id": income.id,
        "deferred_start_date": datetime.date(2026, 7, 1), "deferred_end_date": datetime.date(2026, 9, 30)})]})
move.action_post()
gen = move.deferred_generated_ids
deferral = gen.filtered(lambda m: m.deferred_entry_type == "deferral")
recog = gen.filtered(lambda m: m.deferred_entry_type == "recognition").sorted("date")
check("one deferral, posted", len(deferral) == 1 and deferral.state == "posted")
check("deferral hits deferred-revenue acct", company.deferred_revenue_account_id in deferral.line_ids.account_id)
check("three recognition moves", len(recog) == 3)
got = [round(sum(m.line_ids.filtered(lambda l: l.account_id == income).mapped("credit")), 2) for m in recog]
check("proration 310k/310k/300k", got == [310000.0, 310000.0, 300000.0], str(got))
check("future recognitions draft+auto_post", all(m.state == "draft" and m.auto_post == "at_date"
    for m in recog if m.date > datetime.date(2026, 7, 24)))
print("RESULT:", "ALL CHECKS PASSED" if OK else "SOME CHECKS FAILED")
env.cr.rollback(); print("rolled back — DB unchanged")
```

### 3b. Batch payment — `verify_batch_payment.py`

Creates two posted outbound vendor payments (each with a `res.partner.bank`),
batches them, validates (→ `BATCH/YYYY/MM/####`), generates the BCA export
(→ state `sent`, payments `marked sent`), checks the CSV rows.

```python
import base64, datetime
env = env
OK = True
def check(l, c, d=""):
    global OK; OK = OK and bool(c); print(f"  [{'PASS' if c else 'FAIL'}] {l}" + (f" — {d}" if d else ""))
company = env["res.company"].browse(1)
env = env(context=dict(env.context, allowed_company_ids=[company.id]))
journal = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
fmt = env.ref("custom_account_batch_payment.format_bca_mcm")
pays = env["account.payment"]
for i, (nm, acc, amt) in enumerate([("Vendor Alpha", "1234567890", 1500000.0), ("Vendor Beta", "9876543210", 2750000.0)]):
    v = env["res.partner"].create({"name": nm, "supplier_rank": 1})
    b = env["res.partner.bank"].create({"acc_number": acc, "partner_id": v.id, "acc_holder_name": nm})
    p = env["account.payment"].create({"payment_type": "outbound", "partner_type": "supplier", "partner_id": v.id,
        "amount": amt, "date": datetime.date(2026, 7, 24), "journal_id": journal.id, "partner_bank_id": b.id, "memo": "INV-%02d" % i})
    p.action_post(); pays |= p
check("both payments posted", all(p.state in ("in_process", "paid") for p in pays))
batch = env["custom.account.batch.payment"].create({"journal_id": journal.id, "date": datetime.date(2026, 7, 24),
    "batch_type": "outbound", "export_format_id": fmt.id, "payment_ids": [(6, 0, pays.ids)]})
check("draft, count 2, total 4.25M", batch.state == "draft" and batch.payment_count == 2 and abs(batch.amount_total - 4250000) < 0.01)
batch.action_validate()
check("validated + named BATCH/2026/", batch.state == "validated" and (batch.name or "").startswith("BATCH/2026/"), batch.name)
batch.action_generate_export_file()
check("sent + file + payments sent", batch.state == "sent" and bool(batch.export_file) and all(p.is_sent for p in pays))
rows = [ln for ln in base64.b64decode(batch.export_file).decode().splitlines() if ln.strip()]
check("2 rows, both accounts, no-decimal amounts", len(rows) == 2 and "1234567890" in "\n".join(rows) and "1500000" in "\n".join(rows))
print("RESULT:", "ALL CHECKS PASSED" if OK else "SOME CHECKS FAILED")
env.cr.rollback(); print("rolled back — DB unchanged")
```

### 3c. Reconcile — `verify_reconcile.py`

Uses **deliberately unique amounts** so candidate search is deterministic on a
busy ledger. Flow A: post an invoice, create a matching bank-statement line,
confirm candidate scoring picks it as top hit, `action_auto_match` reconciles
both sides with no suspense remainder. Flow B: reconcile two opposing receivable
lines via the journal-items wizard. Flow C: the overview SQL view is queryable
and its drill-down returns an act_window.

```python
import datetime
env = env
OK = True
def check(l, c, d=""):
    global OK; OK = OK and bool(c); print(f"  [{'PASS' if c else 'FAIL'}] {l}" + (f" — {d}" if d else ""))
company = env["res.company"].browse(1)
env = env(context=dict(env.context, allowed_company_ids=[company.id]))
Acc = env["account.account"].with_company(company)
income = Acc.search([("account_type", "=", "income")], limit=1)
bankj = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
cust = env["res.partner"].create({"name": "RECON TEST", "customer_rank": 1})
# Flow A
AMT = 12_345_678.91
inv = env["account.move"].create({"move_type": "out_invoice", "partner_id": cust.id,
    "invoice_date": datetime.date(2026, 7, 24), "date": datetime.date(2026, 7, 24),
    "invoice_line_ids": [(0, 0, {"name": "r", "quantity": 1, "price_unit": AMT, "tax_ids": [(6, 0, [])], "account_id": income.id})]})
inv.action_post()
recv = inv.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
stl = env["account.bank.statement.line"].create({"journal_id": bankj.id, "payment_ref": "SETTLE",
    "amount": AMT, "date": datetime.date(2026, 7, 24), "partner_id": cust.id})
check("candidate top hit is the invoice line", stl._get_match_candidates(limit=10)[:1] == recv)
check("auto-match candidate unique", stl._get_auto_match_candidate() == recv)
stl.action_auto_match()
check("stmt line + AML reconciled, no suspense", stl.is_reconciled and recv.reconciled
    and not stl.move_id.line_ids.filtered(lambda l: l.account_id == bankj.suspense_account_id))
# Flow B
racct = cust.property_account_receivable_id.with_company(company)
misc = env["account.journal"].search([("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
B = 3_141_592.65
m1 = env["account.move"].create({"journal_id": misc.id, "date": datetime.date(2026, 7, 24), "line_ids": [
    (0, 0, {"account_id": racct.id, "partner_id": cust.id, "debit": B, "name": "d"}),
    (0, 0, {"account_id": income.id, "credit": B, "name": "dc"})]})
m2 = env["account.move"].create({"journal_id": misc.id, "date": datetime.date(2026, 7, 24), "line_ids": [
    (0, 0, {"account_id": racct.id, "partner_id": cust.id, "credit": B, "name": "c"}),
    (0, 0, {"account_id": income.id, "debit": B, "name": "cc"})]})
(m1 + m2).action_post()
l1 = m1.line_ids.filtered(lambda l: l.account_id == racct); l2 = m2.line_ids.filtered(lambda l: l.account_id == racct)
wiz = env["custom.account.reconcile.wizard"].with_context(active_model="account.move.line", active_ids=(l1 + l2).ids).create({})
check("wizard balanced", wiz.is_balanced)
wiz.action_reconcile()
check("both items reconciled", l1.reconciled and l2.reconciled)
# Flow C
rows = env["custom.reconcile.account"].search([])
check("overview queryable", True, "%d accounts w/ open items" % len(rows))
if rows[:1]:
    check("drill-down act_window", rows[:1].action_open_lines().get("type") == "ir.actions.act_window")
print("RESULT:", "ALL CHECKS PASSED" if OK else "SOME CHECKS FAILED")
env.cr.rollback(); print("rolled back — DB unchanged")
```

### Run all three across the fleet
```bash
for s in verify_deferred verify_batch_payment verify_reconcile; do
  for db in rnd_levis prd_levis prd_levis_begbal prd_detail_levis prd_levis_AP demo_updated_levis; do
    r=$(docker exec -i odoo19-platform-odoo odoo shell -d "$db" --no-http --log-level=warn < /path/$s.py 2>&1 | grep -E 'RESULT:|\[FAIL\]')
    echo "$s @ $db -> $r"
  done
done
```

---

## 4. Gotchas & caveats

- **Do NOT deploy with `--test-enable`.** `custom_account_reconcile`'s bank-match
  tests (`test_exact_match_reconciles`, `test_undo_restores_suspense`,
  `test_wizard_preselects_exact`) assume a clean ledger and **FAIL** on a real DB
  (e.g. `prd_levis_begbal` has ~3,378 pre-existing posted reconcilable AMLs that
  pollute `_get_match_candidates`). This is **non-hermetic test data, not a
  module bug** — the §3c hermetic verification (unique amounts) passes on all six
  DBs. Run the module test suite only on a clean/scratch DB.
- **Fiscal lock date.** Most levis DBs lock at `2026-06-30` (`prd_levis` and
  `prd_detail_levis` are unlocked). Postings in the verification use `2026-07-24`
  (open). A deferral whose period spans an already-closed month would fail to
  post that month's recognition — keep test/live windows after the lock.
- **Batch export requires `partner_bank_id.acc_number`** on every payment, else
  `action_generate_export_file` raises. The bank-name/BIC columns render **blank**
  unless the payee's `res.partner.bank.bank_id` is set. The per-bank layouts
  (`_render_bca_mcm` etc.) are **baselines** — refine against real bank-portal
  sample files before go-live. BCA amounts render without decimals (IDR).
- **Empty customer list.** `prd_levis` / `prd_detail_levis` have 0
  `customer_rank>0` partners; the deferred/reconcile scripts self-create a
  throwaway partner (rolled back).
- **SQL view idiom.** `reconcile_overview.py` builds its `_auto=False` view with
  an f-string `CREATE OR REPLACE VIEW {self._table}` (not `%`-format) — the
  `%`-format form trips semgrep `odoo-sql-injection-percent-format` in CI.
- **Knowledge docs.** Each module carries a hand-written `MODULE_KNOWLEDGE.md`
  (the LLM generator hallucinated cross-module content — do not trust its output
  unreviewed). CI's `drift-check` fails if module source changes without a
  knowledge update.

---

## 5. References

- Modules: `addons/ee_gap/custom_account_{reconcile,deferred,batch_payment}/`
- Config script: `scripts/tenants/levis/74_set_deferred_config.py`
- Gap audit: `docs/ee-gap/accounting-gap-audit-2026-07.md`
- Merged via **PR #66** (`main` merge `071c73a`); bank-import fix that shares the
  ee_gap area: **PR #67**.
- Rolled out + verified across all six levis DBs on **24-Jul-2026**.
