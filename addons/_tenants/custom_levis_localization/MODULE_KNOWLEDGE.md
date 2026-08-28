---
status: draft
generated_at: 2026-07-02T08:56:04Z
generator: bootstrap-v1
module: custom_levis_localization
manifest_version: 19.0.1.29.0
---

# Levi's Localization (`custom_levis_localization`)

## Purpose
This module implements five specific requirements for the Levi's tenant: HS Code management on the product master, ensuring receipt quantities do not exceed demand quantities, skipping the inventory journal entry at goods receipt confirmation, generating branded payment vouchers and receipts, and providing a periodic inventory reconciliation tool that realigns GL inventory-asset accounts with actual on-hand stock value.

## Business Flow
1. **HS Code Management**:
   - Delivered as a `product.template` view that inherits `product.product_template_form_view` to surface the native `stock_delivery` `hs_code` field on the General Information tab (`views/product_template_views.xml:9-18`). There is no Python `product` override; the field itself comes from `stock_delivery`.
2. **Receipt Quantity Validation**:
   - On confirming an incoming stock picking, if any line's done quantity exceeds its demand quantity (compared with `float_compare`), a `UserError` is raised listing the offending products.
3. **Inventory Journal at Goods Receipt & Vendor Return (opt-in switch)**:
   - Governed by `ir.config_parameter` `custom_levis_localization.suppress_gr_journal` (default **OFF**). This build has no standard stock input/output interim accounts, so core real-time valuation posts nothing; the module books inventory GL directly via the category pair `property_stock_valuation_account_id` + `account_stock_variation_id` (same pair the Inventory Reconciliation tool uses).
   - Switch OFF (default): on a vendor **goods receipt** (source = supplier) it posts `Dr Stock Valuation / Cr Stock Variation` for `move.value` (ref `GR-VAL:<move id>`); on a vendor **return / RTV** (destination = supplier) it posts the exact reverse `Dr Stock Variation / Cr Stock Valuation` (ref `GR-RET-VAL:<move id>`). Both are idempotent by `ref` and only fire for `real_time` categories with the accounts + a stock journal set.
   - Switch ON (periodic): both receipt and return journals are suppressed; GL is trued up periodically by `levis.inventory.reconciliation`.
4. **Payment Vouchers & Payment Receipts**:
   - Two branded PDF documents are generated for payments on `account.payment`: a *Payment Voucher* for vendor/outbound payments and a *Payment Receipt* for customer/inbound payments. Each renders only for its matching payment direction.
5. **Periodic Inventory Reconciliation**:
   - Because receipts/deliveries do not post inventory journals in this setup, GL inventory-asset accounts drift from real on-hand value. `levis.inventory.reconciliation` computes, per valuation account, the actual stock value (`stock.quant.value`) vs the current GL balance and generates a DRAFT adjustment journal against an inventory-variation account for the accountant to review and post.

## Key Models
- `levis.inventory.reconciliation` — Manages periodic inventory reconciliations, computing differences between GL balances and actual stock values and producing a DRAFT `account.move`.
- `levis.inventory.reconciliation.line` — One line per stock-valuation account, holding the GL balance, stock value, and computed difference.
- `stock.move` — Overrides to skip GL journal entries on vendor goods-receipt moves.
- `stock.picking` — Overrides to validate receipt quantities against demand quantities.

## Important Fields
- **levis.inventory.reconciliation**:
  - `name`: Sequence-generated identifier. Defaults to `"/"` and is replaced in `create()` via the `levis.inventory.reconciliation` `ir.sequence` (prefix `INVREC/%(year)s/`).
  - `company_id`: Company for the reconciliation (defaults to the active company).
  - `date`: Date up to which posted GL balances are considered (default is today).
  - `journal_id`: General account journal used for generating the reconciliation entry.
  - `counterpart_account_id`: Inventory variation account where differences are booked when a category-level Stock Variation account is not set.
  - `line_ids`, `move_id`, `state` (draft/computed/generated), `total_difference` (computed sum of line differences), `currency_id`.

- **levis.inventory.reconciliation.line**:
  - `reconciliation_id`: Parent reconciliation (cascade delete).
  - `company_id`, `currency_id`: Related from the parent.
  - `account_id`: Valuation Account.
  - `counterpart_account_id`: Variation Account.
  - `book_value`: GL Balance.
  - `stock_value`: Actual on-hand stock value.
  - `difference`: Computed and stored, `stock_value − book_value`.

- **stock.move**:
  - `_is_levis_goods_receipt()`: True when the move enters from a supplier location (`location_id.usage == 'supplier'`).
  - `_is_levis_vendor_return()`: True when the move leaves to a supplier location (`location_dest_id.usage == 'supplier'`) — a vendor return / RTV.
  - `_levis_suppress_gr_journal()`: Reads the `suppress_gr_journal` config switch (default OFF).
  - `_should_create_account_move()`: Returns `False` for vendor receipts only when the suppress switch is ON; otherwise defers to core.
  - `_action_done()`: After super, calls `_levis_post_gr_journal()` (receipts) and `_levis_post_return_journal()` (vendor returns).
  - `_levis_book_valuation_entry(ref, label, incoming)`: Shared idempotent poster — `incoming=True` → Dr Valuation/Cr Variation; `incoming=False` → the reverse. No-op if already posted for `ref`, non-real-time category, missing accounts/journal, or zero `move.value`.

- **stock.picking**:
  - `button_validate()`: Validates the done quantity against demand quantities on incoming stock pickings (via `float_compare`). Raises an error if any line exceeds its demand.

## Public Methods
- **levis.inventory.reconciliation**:
  - `action_compute()`: Rebuilds lines, computing differences between GL balances and actual stock values.
  - `action_generate_move()`: Generates a DRAFT journal entry for the reconciliation and opens it.
  - `action_view_move()`: Returns an act_window action opening the generated `account.move`.
  - `_cron_generate_drafts()`: Creates one computed reconciliation per company and generates a DRAFT entry when a difference exists. Never posts automatically. Bound to an inactive monthly cron.

## Integration Points
- **Depends on**: `product`, `stock`, `stock_account`, `stock_delivery`, `purchase`, `account`.
- **Inherits from**: `stock.move` and `stock.picking`.
- **ir.sequence**: `seq_levis_inventory_reconciliation` (code `levis.inventory.reconciliation`, prefix `INVREC/%(year)s/`, padding 4).
- **ir.cron**: `cron_levis_inventory_reconciliation` runs `model._cron_generate_drafts()` monthly, shipped with `active=False`.
- **Reports**: Two `ir.actions.report` bound to `account.payment` (`action_report_payment_voucher`, `action_report_payment_receipt`) rendering QWeb templates `report_payment_voucher` / `report_payment_receipt`, using paperformat `paperformat_levis_payment` (`reports/paperformat.xml`).
- **Extended by**: None.
- **External calls**: None.
- **Cross-vertical**: The manifest names `prd_levis` / `rnd_levis` / `demo_levis` as the intended target databases, but nothing in the code enforces tenant scoping.

## Feature 9 — Trade/Non-Trade split + Operating Unit
- **Models**: `purchase.order` (`l10n_purchase_type`, numbering, `_prepare_invoice`),
  `purchase.order.line` (`_compute_analytic_distribution` merges the store OU),
  `account.move` (`l10n_purchase_type`), `account.move.line` (`_compute_account_id`
  remaps the payable per stream AND fills a non-trade product line that resolved to
  no account with `mapping.expense_account_id` — only when otherwise empty),
  `stock.picking` (`l10n_purchase_type`),
  `stock.move` (GR/IR routing + OU analytic on the GR journal),
  `stock.warehouse` (`l10n_ou_analytic_id`, `l10n_purchase_journal_id`),
  `levis.purchase.account.map` (config: payable + GR/IR + expense per company/type).
- **Numbering**: `data/po_sequences.xml` defines `purchase.order.levis.trade`
  (`PO/T/EBR/%(year)s/%(month)s/`) and `.nontrade` (`PO/NT/EBR/...`), both
  `use_date_range` + `no_gap`. Native date ranges are yearly, so
  `PurchaseOrder._levis_next_po_number` ensures a MONTHLY `ir.sequence.date_range`
  before drawing the counter → per-month reset. Absent sequences (non-Levi's DB)
  fall back to core `P` numbering.
- **Seeding**: `models/setup.py::seed_trade_ou(env)` — idempotent; creates the
  "Operating Unit" analytic plan + one analytic account & one purchase journal per
  warehouse (guarded by the two `stock.warehouse` link fields), and the mapping
  rows by account CODE (`with_company`, company-dependent). Run via
  `post_init_hook` (install) or `scripts/tenants/levis/40_setup_trade_ou.py`
  (existing DBs, since `-u` does not re-run post-init).
- **EBR account codes**: trade payable `2103100001`, non-trade payable
  `2103300001`, non-trade GR/IR `2103300008`. Trade GR/IR stays per product
  category (`account_stock_variation_id`, e.g. `2103109121` textile).

## Feature 8 — Admin fees (and card MDR) on payment registration
- **Models**: `levis.payment.register.fee` (TransientModel, one fee line on the
  wizard) and `account.payment.register` (`_inherit`), in
  `models/account_payment_register.py`.
- Each fee line carries its own COA, label and amount; the wizard total
  (`amount`) is recomputed as `<batch residual> + Σ fees` by
  `_onchange_admin_fee_line_ids`, so amounts never accumulate and clearing the
  lines restores the plain residual. The fees ride Odoo's native
  `write_off_line_vals` channel (`_prepare_admin_fee_write_off_vals`), so the
  counterpart still equals the bill residual and the bill reconciles in full.
- A **negative** amount nets the fee off an inbound receipt — that is how the
  `is_mdr` lines produced by `_onchange_x_card_bin` book card MDR, resolved
  against `levis.mdr.bin`. MDR lines are read-only in the list.
- **Several bills at once**: core leaves `group_payment` False for a multi-bill
  selection (one payment per bill), and a single fee cannot be split across
  them. Adding a fee line therefore ticks *Group Payments*, so one payment
  settles every selected bill with the fee charged once — the case that matters,
  since batching bills into one transfer is what saves the fee. Unticking
  *Group Payments* while fees exist raises in
  `_create_payment_vals_from_batch` rather than splitting the fee. Bills from
  **different partners** build more than one batch, so `can_edit_wizard` is
  False and the whole section stays hidden; register per partner.
- `_assert_admin_fee_balance` rejects a hand-edited `Amount` that no longer
  equals residual + fees, which would otherwise mis-reconcile the bill silently.
- **Tenant-neutral twin**: `custom_payment_admin_fee` (ee_gap) is the same
  feature without MDR/BIN and Operating Unit. Never install both on one
  database — both inherit the wizard and inject an "Admin Fees" group, so the
  section renders twice and the two onchange handlers fight over `amount`.

## Feature 13 — Indonesian bank master data (Kode BI)
- **Field**: `res.bank.l10n_id_bi_code` ("Kode BI") — the 7-digit Bank Indonesia
  clearing/RTGS participant code, a.k.a. *sandi bank* (`models/res_bank.py`).
  Surfaced on the core bank form/list and made searchable
  (`views/res_bank_views.xml`, inheriting `base.view_res_bank_form`,
  `base.view_res_bank_tree`, `base.res_bank_view_search`).
- **Seeding**: `data/res.bank.csv` ships 181 banks (name + SWIFT/BIC + Kode BI),
  external IDs `res_bank_<kodeBI>`, so re-running `-u` updates rather than
  duplicates. Loaded on install/upgrade; no separate script.
- **Kode BI is the unique key, not BIC.** Roughly 46 Bank Indonesia branch offices
  all share the BIC `INDOIDJA`, so BIC cannot identify a row. A `models.Constraint`
  enforces `unique(l10n_id_bi_code)`; NULL is allowed many times over, which is why
  the stock "Reserve" placeholder bank (no Kode BI) does not collide.
- **Consumer**: `levis.mdr.bin.acquirer_bank_id` — the Card BIN / MDR mapping's
  *Acquiring Bank* dropdown, which was effectively empty before this seed.
- **Data provenance**: 180 rows come from the customer's (EBR) list; its Kode BI
  column had lost leading zeros to Excel, so 29 are re-padded to 7 digits and
  `CITIBANK, NA` (`00310305`, 8 digits) is corrected to `0310305`. Bank Central
  Asia (`CENAIDJA` / `0140397`) was absent from that list and added separately —
  **its two values are not verified against the official BI participant list.**

## Feature 14 — Product-catalogue indexes (large variant counts)

The Levi's catalogues carry ~32k templates / ~348k variants (Size × Inseam is
`create_variant='always'`, so Odoo materialises the full matrix). Two hot paths
were unindexed. `models/product_product.py` fixes both.

- **Product Variants list.** `product.product_product_tree_view` declares
  `default_order="is_favorite desc, default_code, name, id"`. `name` is an
  `_inherits` field on `product_template`, so ordering by it forced a LEFT JOIN
  plus a top-N sort over the whole catalogue (~280 ms for one 80-row page).
  `views/product_product_views.xml` drops `name` from the order, and
  `_levis_list_order_index` covers what remains. Page 1 is now sub-millisecond.
- **Valuation.** Core `product.value` (`stock_account`, Odoo 19's replacement for
  `stock.valuation.layer`) ships with a primary key and no other index, while
  `product.product._compute_value` → `_get_last_product_value` filters on
  `product_id / company_id / move_id / lot_id` and sorts by `date DESC`. Two
  indexes are created from `product_product.init()` — see the gotcha below for
  why they are NOT declared on a `product.value` model.

## Feature 15 — Monthly POS clearing (`levis.pos.clearing`)

Settles the per-tender POS receivables (`1106000101`..`110`) against the bank
settlements already imported, replacing `scripts/tenants/levis/80|81|90_*clearing_juli*`
which were hardcoded to one month and driven by the client's EBR workbook.

**Why no upload is needed.** The acquirer prints gross and fee on every settlement
narrative, so `levis.bank.narrative` reads them straight off `payment_ref`:

| Bank | Shape | Gross | Fee |
|---|---|---|---|
| BCA debit | `KR OTOMATIS MID : <mid> <STORE> TGH: n DDR: n` | `TGH` | `DDR` |
| BCA credit | `KARTU KREDIT MID:<mid> <STORE> TGH:0000n ADM:0000n` | `TGH` | `ADM` |
| BCA QRIS | `KR OTOMATIS TANGGAL :dd/mm MID : <mid> ... QR : n DDR: n` | `QR` | `DDR` |
| BCA NFC | `KR OTOMATIS TANGGAL :dd/mm MID : <mid> <STORE> NFC: n DDR: n` | `NFC` | `DDR` |
| BRI | `OnUs|OffUs|QRIS* 1 YYMMDD <tid> <STORE> AMT:n,00MDR:n,00` | `AMT` | `MDR` |

Measured on prd_levis_begbal July 2026 (2 535 lines): 2 073 settlements,
407 cash deposits, 34 sweeps, 6 charges, 3 interest, **12 unrecognised**, and
`gross - mdr == amount` on **every** settlement (0 disagreements). This is a
strict improvement on the scripts, which had to spread a monthly per-store MDR
pro-rata because the workbook and the ledger were on different grains.

`NFC` was added to that table in 19.0.1.31.0, from two of those 12 unrecognised
lines. Contactless says how the card was presented, not whether it was debit or
credit, and the narrative does not say — so it parses as `debit`, which is the
feed it arrives on. That choice carries no accounting weight, because clearing
pools debit, credit and QRIS over the same card receivables; what matters is
that it resolves to a *card* channel at all, since an unrecognised one keeps the
unrestricted pool and may settle the CASH receivable. Both observed rows carry
`DDR: 0.00`, so contactless is fee-free here or billed elsewhere.

**Why the tender split is discovered, not read.** One card MID covers Visa,
Mastercard, JCB and Amex alike, and `levis.mdr.bin` is empty, so nothing states
which of the ten receivable accounts a settlement pays. `_allocate` consumes that
store's open debits for the trading day, largest residual first, and reports the
remainder as a shortfall rather than forcing it somewhere.

**The clearing is written onto the bank statement line itself** (since
19.0.1.30.0). Odoo books a statement line as `Dr Bank / Cr Suspense` and expects
reconciliation to *replace* the suspense leg — that is why the suspense account
ships with `reconcile = False` and can never be matched. Booking the counterpart
in a separate entry leaves the suspense leg standing forever: the ledger comes
out right, but every statement line stays `is_reconciled = False` and Odoo then
refuses a lock date over the period. July 2026 is the proof — 2 526 lines, GL
flat (suspense nets to zero against 757 `EBR-CLR-JULI-2026-*` legs), lock date
blocked. So `_counterpart_plan` produces the legs that *replace* the suspense
leg:

    Dr Bank                 (untouched, what the bank paid)
    Dr MDR Expense          (prorated to what was actually matched)
        Cr POS Receivable   (per tender, gross)

and a suspense leg survives only when the settlement is short, carrying exactly
the amount nobody could explain. Fully explained lines end up with no suspense
leg and Odoo's own `_compute_is_reconciled` marks them reconciled — no
reconciliation call, no flag flipped on the chart of accounts.

Watch the arithmetic on a short line: the residual is the *balancing* figure, not
`short_amount`. A settlement of gross 1 000 000 / fee 10 000 / bank 990 000 that
only finds 400 000 of open receivable is short 600 000 **gross**, but books
400 000 receivable and 4 000 prorated fee, so 594 000 stays on suspense. The
6 000 difference is fee on a settlement that, as far as the open receivables go,
never happened.

**Three stages, hard-separated.** `action_compute` builds the summary and creates
*nothing* (verified on the clone: `account.move` count 38 822 before and after);
`action_generate_moves` writes the intended journal items to
`levis.pos.clearing.leg` and still touches no accounting; `action_post` applies
exactly those legs to the statement lines and reconciles. Stage 2 persists the
plan rather than letting stage 3 recompute it, so the accountant approves a
specific set of numbers and posting books that set — and if the underlying
receivables moved in between, `_preflight` refuses instead of quietly booking
something else. No cron, no auto-post, and `action_compute` never generates.

**The settlements are searchable away from the run form (19.0.1.39.0).** The
Settlements tab is a `one2many`, and an embedded `one2many` has no search panel —
a month across eleven bank journals is a thousand rows you can only scroll.
`action_view_lines` ("Search Settlements" in the header, plus an *Invoicing ▸
POS Settlements* menu over every run) opens the same records under a normal
action with `view_levis_pos_clearing_line_search`: filter by store, bank, tender,
merchant id, narrative or X24DN transaction number; group by any of them. The
line's `run_state` and `run_period_ref` are stored relateds added for exactly
this — a filter on a non-stored field returns nothing rather than failing. The
settlement form moved out of the tab into a top-level
`view_levis_pos_clearing_line_form` so the row popup and the standalone list are
the same screen; receipt ticking there is gated on `run_state`, which the tab used
to get for free from the parent's state.

**The mapping wizard is a full page, and its totals prove themselves
(19.0.1.39.0).** A proposal is one merchant id summed over a whole period, while
the *Sample Narrative* beside it belongs to exactly one of those statement lines —
so the amount reads as though it disagreed with the account mutation and the
berita transfer. Three things fix that, and none of them is a different sum:
`gross_total` and `mdr_total` carry the narratives' own figures next to the bank's
(gross − MDR is what the bank moved, and `narrative_gap` shows anything left
over — a cash deposit quotes no gross, so its whole amount lands there by
design), and `statement_line_ids` holds the lines behind the total with a
*Bank Lines* button to open them. The wizard opens `target="current"`, not a
dialog: dozens of ids each needing their amounts read against a statement do not
fit in a modal, so the buttons live in a `<header>` rather than a `<footer>`.

**Undo is per statement line.** Once posted, the legs live on the bank entries,
so `action_cancel` refuses; reversing means Odoo's own "Undo Reconciliation" on
the lines concerned.

**Key models.** `levis.pos.clearing` (+ `.line` per statement line, `.leg` per
planned journal item, `.alloc` per
consumed receivable, `.diag` for findings), `levis.clearing.config` (accounts, one
row per company, seeded by code from `models/setup.py:seed_clearing_config`),
`levis.bank.mid.map` (MID/TID/keyword → Operating Unit), `levis.bank.narrative`
(AbstractModel, one `_parse_<format>` per bank), plus stored narrative fields on
`account.bank.statement.line` for per-line inspection.

**The statement line carries its own reading.** `_compute_levis_narrative` stores
`levis_narrative_kind`, `levis_channel`, `levis_mid`, `levis_gross`, `levis_mdr`,
`levis_trans_date`, `levis_ou_analytic_id`, `levis_mid_map_id`,
`levis_narrative_note` and `levis_amount_matches_narrative` on every line, so a
statement can be filtered and grouped per store without running a clearing. The
compute depends on the narrative, the amount and the journal's format — **not** on
`levis.bank.mid.map`, so adding one mapping never silently rewrites months of
history; `action_levis_reread_narrative()` (via `add_to_compute`, so the ORM owns
the write) re-reads the lines Finance chooses. `custom_levis_bank_reconcile`
builds the interactive matching wizard on exactly these fields.

**The receipt numbers behind a settlement are recovered, and only where the
money proves them.** The receivable a settlement consumes is an X70D transfer
line — one per store, per trading day, per tender — so it carries no receipt
number at all. The staged X70D rows do (`retail.import.line.raw_data_json`:
`store_code`, `register`, `transnum`, `tender_type`, `tender_amount`), and X24DN
posts the same keys as `pos.order.pos_reference` (`store-register-transaction`).
`_x24_rows` joins them to the Operating Unit through `ir.model.data`
(`posconfig_<store>`) → `pos.config` → `stock.warehouse.l10n_ou_analytic_id`.

`_x24_identify` then matches on **arithmetic only**: one transaction equal to the
settlement's gross (`exact`), or one tender whose whole trading day sums to it
(`batch`); several of either is `ambiguous` and lists them all without claiming
one; anything else is `none` and names nothing. There is deliberately **no subset
search** — a 250.900 settlement out of a day holding 16.865.300 across ten card
transactions can be composed many ways. Reading the receipts off the *allocated*
receivable (the first cut of this feature, 19.0.1.36.0) was worse still: the
allocation picks by residual and cannot see a tender, so that 250.900 line listed
the day's ten card receipts and read as though it had paid millions.

Where the match lands, it yields the one thing the narrative can never say: the
**tender**. `x24_tender` records it and `x24_tender_mismatch` flags the lines
where the allocation credited a different tender receivable — 377 of 1.420
identified settlements on prd_levis_begbal's August run. That is a real
divergence between evidence and `_allocate`'s largest-residual guess, not a
display bug. `custom_retail_import` stays a non-dependency: without it the
columns are simply empty and clearing is unaffected.
`levis.pos.clearing.line.move_name` is the statement line's own entry number.

Gotcha: some staged rows carry an empty `trans_date`/`tender_amount`, so both
casts live inside a `CASE` — a bare `WHERE` is free to run after the cast and
dies with `invalid input syntax for type date`.

**The matching worksheet: `levis.pos.clearing.receipt`.** Roughly half a month's
settlements pay *part* of a trading day, which no arithmetic can decompose (see
`_x24_identify`), so the last word is a human's and has to be storable. One row =
one X24DN transaction offered to one bank line, with a `matched` tick.

* **Generated per line, on demand.** `action_suggest_receipts` builds one bank
  line's candidates (~0,6 s, ~20 rows). Generating a whole month up front was
  36.000 rows and **143 seconds** — a button no web worker survives — for a
  question that is always asked one line at a time. `action_compute` therefore
  writes only the ticks the amount proves (947 rows, ~4 s on prd_levis_begbal).
* **A tick is exclusive company-wide.** A partial unique index
  (`levis_pos_clearing_receipt_matched_uniq ... WHERE matched`) is the guarantee —
  `_sql_constraints` cannot express "only ticked rows are unique", and every
  candidate row is a duplicate of some other line's candidate by design.
  `_assert_unclaimed` checks first so the user gets a sentence naming the bank
  line that already holds the transaction, not an integrity error mid-flush;
  `_release_elsewhere` (per record) and `_sweep_claimed` (one DELETE, used by the
  generator) then take the receipt off every other line.
* **Unticking does not sweep the run.** The receipt is free the moment it is
  unticked; it reappears wherever it belongs the next time that line is opened.
* Refreshing a line rebuilds only its *unticked* suggestions — an answer already
  given is never undone by asking the question again.
* `matched_total` / `match_gap` on the line are what has been confirmed and what
  is still unexplained; `x24_trans_refs` follows the ticks, not the evidence.

**Two rules may never claim one terminal.** `_check_no_colliding_rule` refuses a
mapping that would compete with an existing one, comparing through the resolver's own
`_keys_match` — so it catches an identical key, a leading-zero variant
(`1999632289` vs `001999632289`) *and* a suffix (`4608375` vs `885004608375`), which no
unique index can express. It deliberately allows what the model was built for:
non-overlapping `date_start`/`date_end` (a MID handed to another store), rules restricted
to different bank feeds, and keyword substrings. Override with context
`levis_skip_mid_map_guard=True`, which logs a warning. The SQL `_key_uniq` constraint
exists but has never fired: `journal_id` is NULL on every real rule and Postgres treats
NULLs as distinct.

**The most specific keyword wins, not the first row.** `_resolve` picks by
`(sequence, -len(key), key)`. Sequence stays the explicit override; length settles the tie
— which is *always*, since every keyword rule on prd_levis_begbal carries sequence 20, so
the tie used to be broken alphabetically. `SMB SOPIAN PERMANA` beat `SOPIAN PERMANA` only
because M sorts before O, and the two name different stores.

**Provisioning an existing database.** `post_init_hook` only runs on install;
`scripts/tenants/levis/96_setup_pos_clearing.py` does the same for a database
that already has the module. The MID mapping is deliberately not seeded — see the
gotcha below.

## Feature 16 — Store code + advanced-matching foundations

Phase 1 of the daily-clearing work. Nothing here changes what the clearing
allocates; it puts the pieces in place that later phases stand on.

**`stock.warehouse.l10n_store_code`** — the store's identity *outside* Odoo. The
analytic OU is the identity inside the ledger, but it is a record id: a cashier
cannot type it on a transfer memo and a bank cannot print it on a statement. A
textual code already existed, but only inside the X24DN feed, reachable only via
`ir.model.data` xids named `posconfig_<CODE>`. This promotes it to a real column
so one code serves the retail feed, the cash-deposit *berita acara*, and bank
matching alike.

* Unique per company (`models.Constraint`; Odoo 19 ignores `_sql_constraints`).
  NULLs stay distinct in Postgres, which is what lets a fleet where most stores
  have no code yet pass the constraint during backfill.
* `pos.config.l10n_store_code` is a **non-stored** related. Storing it would force
  a full recompute of every `pos.config` row on `-u` in each of the ~10 databases
  sharing this addon, and nothing needs it in SQL — the clearing's raw queries
  already join `ir_model_data` -> `pos_config` -> `stock_warehouse`.
* `_levis_store_code_index(company_id)` is an `ormcache`d `{CODE: (warehouse_id,
  analytic_id)}`; `_levis_store_by_code(company, code)` is what callers use.
  `create`/`write`/`unlink` clear the cache when a code, an analytic or a company
  changes — a renamed code must stop resolving, and there is a test for that.
* `seed_store_codes(env)` backfills from the feed's xids. It **never** overwrites
  a code already on a warehouse (a hand correction outranks the feed) and
  **never** moves a code off the warehouse holding it (a silent steal is worse
  than a visible gap). Both cases are counted and logged. Run it on an existing
  database with `scripts/tenants/levis/41_seed_store_codes.py`; check the
  `skipped` / `orphan` counters it prints — a large number means the feed's store
  mapping disagrees with the warehouses, which is a finding, not a hiccup.

**`levis.clearing.matcher`** (AbstractModel) — one answer to a question two
screens were each answering their own way.

* `_score_candidate(...)` is the bank-reconcile wizard's `score()`, lifted
  unchanged; `custom_levis_bank_reconcile._get_match_candidates` now calls it, so
  the clearing and the wizard can no longer drift apart in what they rank first.
* `_subset_match(items, target, tolerance, max_items, node_budget)` composes a
  settlement out of several open items — but only when exactly one composition
  fits. It is deliberately *not* the same decision `_x24_identify` refuses:
  that method declines to name a subset of **receipt numbers**, which would be an
  unverifiable claim about which customers the acquirer paid. This is ledger
  allocation, where a subset is already being chosen greedily today and every
  item taken is recorded on `levis.pos.clearing.alloc` and reconciled as an exact
  pair. **Do not carry subset search back into `_x24_identify`.**
* Its honesty rests on two properties, both tested: items are put in a total
  order (`-amount, date, key`) before anything is searched, so a shuffled pool
  yields the identical subset; and the search stops at the **second** solution,
  not the first, reporting `ambiguous` and allocating nothing.
* An exhausted node budget returns `none`, never a partial answer.

**Seven new `levis.clearing.config` fields, all inert on arrival** —
`suggest_tolerance_amount` / `_ratio` (0.0), `advanced_matching` (False),
`subset_max_items`, `subset_node_budget`, `deposit_match_window_days`,
`writeoff_limit_amount` (0.0). `_match_tolerance(amount)` returns the wider of
the two tolerances. The tolerance is a **suggestion band only**: it widens which
candidates are offered and lifts their rank, and it never sizes, absorbs or books
anything. A difference inside the band still lands on suspense until a human
writes it off. Keep it distinct from `_EPS` (0.005), which is float noise — a
tolerance-sized difference is money someone decided to absorb and has to stay
visible as such.

## Feature 17 — Store cash deposits and the daily closing

Phase 2 of the daily clearing. Two models, neither of which books anything.

**`levis.store.cash.deposit`** — the document that replaces a guess with evidence.
Card money names its own store (the acquirer prints a MID); cash does not, and
until now the only way to attribute a cash credit was a hand-written keyword rule
guessing at the transfer memo. Finance keys what the store says it paid in,
attaches the slip, and validates it; the clearing then matches a bank credit to
*that*.

* **Finance owns it, not the store.** There are no store users in this database
  and this creates none. `draft -> submitted -> validated` still earns its keep:
  it separates whoever typed a number from whoever checked it against the slip.
* `berita_acara_ref` (`SETOR/<CODE>/<YYYYMMDD>/<nnnn>`) is the string the store
  must put on the transfer memo. That is the whole mechanism by which a bank
  credit stops needing to be guessed at.
* `action_validate` refuses without an attachment and without a store OU. A
  deposit nobody vouched for is not evidence.
* `_bank_credit_uniq` is a **plain** `unique(statement_line_id)` — Postgres treats
  NULLs as distinct, so any number of deposits may await a credit while a claimed
  credit cannot be claimed twice. No partial index needed.
* `write()` freezes `amount` / `warehouse_id` / `deposit_date` / `bank_journal_id`
  once `state = matched`: those figures are what made the match, and editing them
  would leave the clearing pointing at a document that no longer says what it
  said. `action_unmatch` releases the credit and unfreezes them.
* `_find_for_statement_line()` returns a record **only when exactly one candidate
  fits**. Two deposits of the same amount in the same window is a real situation
  (two stores, one bank, one flat float) and is evidence for neither.
* `expected_amount` with no linked session is 0 **and so is `variance`** —
  "nobody measured" must not render as "the store was short".

**`levis.store.daily.closing`** — one row per store per trading day, `_auto =
False`. Deliberately a view: `pos.session` already *is* the daily closing, with a
state and a cash count, and a second stateful record covering the same day would
drift from it. If Finance later needs to write on it, these column names become
field names unchanged.

Three numbers that are easy to conflate and must not be:
`cash_counted` (what the cashier counted), `cash_expected` (opening float plus
the cash the orders say was taken), and the POS receivable the clearing consumes.
`cash_variance` is a till problem; `cash_undeposited` is a banking one.

**Column facts the upgrade taught us** (both cost a failed `-u`):
`pos_session` has **no `company_id` column** — company lives on `pos_config`; and
`cash_register_balance_end` is **computed and unstored**, so the view rebuilds it
as `cash_register_balance_start + cash payments`, the same way core does. Only
`cash_register_balance_start` and `cash_register_balance_end_real` are stored.

A deposit covering several trading days is spread evenly across them in the view.
That is presentation only — nothing allocates or books from the split figure.

**Odoo 19 view gotcha:** `<group expand="0" string="Group By">` inside a `<search>`
no longer validates (`RELAXNG_ERR_INVALIDATTR`). Group-by filters go flat after a
`<separator/>`, which is what every other search view in this module already does.

## Feature 18 — Writing off a clearing residual

Phase 5. A settlement that does not fully explain itself leaves a residual on the
bank suspense account, and the statement line stays open. That is the right
default and it stays the default: `levis.clearing.writeoff.wizard` opens on
`mode = suspense`, and applying it changes nothing.

Some residuals are genuinely explained — a rounding crumb, an unprinted admin
fee, a store that banked less than it counted. Leaving those on suspense stops
being honest bookkeeping and becomes a queue nobody can clear. The wizard records
that decision with an account, a reason, a label and the user who made it
(`writeoff_account_id` / `_label` / `_reason` / `_uid` on
`levis.pos.clearing.line`).

**The whole feature is one expression.** `_counterpart_plan` already computes the
residual leg as the *balancing figure*; the write-off changes only which account
that leg names (`writeoff_account_id or config.suspense_account_id`), and its
role becomes `writeoff`. The entry therefore still balances by construction and
`_preflight`'s `planned == -st_line.amount` identity is untouched.

**Two paths:**

* *Before posting* (the ordinary one) the wizard books nothing. It writes the
  account onto the line and calls `run._retarget_residual_legs()`, which flips
  the **existing** residual leg in place. The receivable and MDR legs keep their
  ids and their reviewed values — rebuilding the whole plan would discard a
  review nobody asked to redo.
* *After posting* the residual is a real journal item. A separate journal entry
  cannot clear it: suspense ships `reconcile = False`, so `Dr write-off / Cr
  suspense` would leave two open items instead of one. So
  `_apply_writeoff_to_posted_move` does what `_apply_to_statement_lines` does —
  replaces the suspense item on the statement line's own move — and the line then
  goes reconciled on its own. **This is the only place the module writes to a
  posted move outside the clearing's posting stage.** It identifies the item to
  move through `leg.move_line_id`, never by "whatever is on suspense": two
  settlements can leave suspense items on one statement line.

**The trap that cost a test run.** `short_amount` is the **gross** left unmatched;
the residual leg is smaller by the fee that was pro-rated away (600 000 vs
594 000 in the fixture). A guard comparing the posted suspense item against
`short_amount` rejects every legitimate write-off. Compare against the leg's own
`balance`.

`writeoff_limit_amount` on the config caps what one line may absorb, checked in
`_preflight` via `_assert_writeoffs_within_limit`; zero (the default) means no
cap. The wizard also refuses the suspense account and any POS receivable — a
residual must not be hidden back in the accounts it came from.

## Feature 19 — The settlement day (`levis.pos.clearing.day`)

Phase 4. The clearing runs over a month because that is the unit its accounting
belongs to — one sequence, one lock-date check, one balance simulation. But
nobody works a month, and the question an operator has is "is the 12th done?".
Until now there was nowhere to ask it: status belonged to the run.

`levis.pos.clearing.day` is **a projection, not a fourth posting stage**. It books
nothing, `_rebuild_for_run` recreates every row on each `action_compute`, and
deleting them all costs nothing but the screen. `line.day_id` is the one column
this phase adds to an existing table.

Stored rather than a `read_group`, for three reasons that each rule the
alternative out: the day compares **two populations in different places** (bank
lines dated D against POS receivables dated D-1, so no grouping over either can
show the other); it needs a status that persists and buttons to press; and it
carries a reviewer's note.

### The green rule, and what it deliberately is not

`is_balanced` is `unexplained_total` at nil — every bank line allocated, or
written off on purpose — plus nothing unmapped or unreadable. **It is not gated
on `tally_variance`.**

That is the most important decision in this model. A settlement legitimately
draws on more than one trading day: that is exactly why `_candidate_dates` walks
a ±`lookback_days` ladder and why `settlement_lag_days` calls itself an
assumption. Gating the colour on `gross_total == sales_h1_total` would paint days
red for a reason no operator can fix, and a red that cannot be cleared is quickly
a red nobody reads.

So the H-1 comparison the business asked for is kept — it *is* `tally_variance`,
with its own column and its own colour — but as supervisory information, not a
workflow gate. `test_a_tally_gap_alone_does_not_stop_a_day_going_green` is the
load-bearing test: a store sells 1.5 M on the 8th, 1.0 M settles on the 9th, the
day is green and the variance still reads -500 000.

`sales_h1_total` is read straight from the ledger by SQL, **not** from this run's
allocations — answering "did roughly the right amount of money show up" from what
the run managed to match would make it agree with itself by construction.

`kanban_color`: 10 green (settled or posted), 1 red (a line names no store or
could not be read), 3 amber (partly done), 0 grey (untouched). The kanban binds
straight to it.

### Measured on real data (August 2026, prd_levis_begbal clone)

3 149 lines over 22 days. The day roll-up reproduces the run's own totals to the
rupiah — Rp 10 305 228 221 unexplained — which is the correctness check that
matters.

Two things only real data showed:

* **`sales_h1_total` must be scoped to the day's own stores.** A date carries
  more than one bank feed, and an IBNI feed holding a single Rp 1 line was being
  compared against the entire company's sales, reporting a variance of minus 412
  million. Fixtures cannot catch this — they never have two feeds on one date.
* **The H-1 assumption does not hold in a backlog month.** Early-August
  settlements ran 3-4x the H-1 sales (3-Aug: Rp 2,88 bn gross against Rp 0,67 bn
  sold), because they were paying for July. Had `is_balanced` been gated on the
  tally, all 22 days would have been red for a reason no operator could fix. This
  is the concrete justification for the green rule above.

### BNI and Mandiri carry no settlements

Checked across June-August 2026 in production, this is the whole of both feeds:
IBNI 4 lines in July and 3 in August, IMand 4 and 1 — all of them Rp 1 or Rp 31
QR onboarding transfers, plus Meterai and Buku Cek charges that `_parse_minor`
already handles. Against IBCA's 2 111 + 3 145 and IBRI's 416.

So **do not write `_parse_bni` / `_parse_mandiri` settlement grammars** on the
strength of "those journals are configured". They are configured and empty; a
day of work per bank would recover about Rp 40 over two months. The store names
in those narratives (`LEVIS GRAND INDONESIA`, …) are already reachable through
keyword rules on `levis.bank.mid.map` with no new code. Revisit only if Levi's
moves card settlement to those banks.

### Not done in this phase

The partial generate/post refactor (`_generate_moves(lines=None)` /
`_post(lines=None)`, so a single day can be booked on its own) is **deliberately
left out**. It is the riskiest change in the whole plan — it turns the run's
state into something derived from its lines — and it rewrites the same methods
that the uncommitted receipt-matching work touches. Do it after that lands, on
its own, so it can be reverted alone.

## Gotchas
- **Never `_inherit "product.value"` from this module.** Doing so pulls
  `product.value` into the module's `init_models()` pass, and
  `registry.check_foreign_keys()` then re-creates any *missing* core foreign key
  (`if spec is None: add_foreign_key(...)`). `prd_levis_begbal` and `rnd_levis`
  have lost `product_value_product_id_fkey` and still hold ~187k rows whose
  `product_id` no longer resolves, so the `ALTER TABLE` raises
  `ForeignKeyViolation` and rolls the whole upgrade back. The `product.value`
  indexes are therefore created with raw `CREATE INDEX IF NOT EXISTS` DDL inside
  `ProductProduct.init()`, which keeps that model out of the pass entirely.
  The same crash still awaits `-u stock_account` on those two databases until the
  dangling rows are removed.
- **Odoo renders `is_favorite desc` as `COALESCE("is_favorite", FALSE) DESC`.**
  A plain btree on `is_favorite` is therefore unusable for that sort; the index
  must be on the same expression. Odoo only emits `NULLS FIRST/LAST` when the
  order string spells it out (`odoo/orm/models.py:~2178`), so Postgres' defaults
  (DESC → NULLS FIRST, ASC → NULLS LAST) already match.
- **Odoo 19 silently ignores `_sql_constraints`.** The classic list-of-tuples form
  produces only a `WARNING ... no longer supported` line at upgrade and creates NO
  constraint. Use the `models.Constraint` class attribute instead (as
  `res_bank.py` does) and verify with
  `SELECT conname FROM pg_constraint WHERE conrelid='<table>'::regclass;` — a clean
  upgrade log proves nothing. `levis_mdr_bin.py` still uses the deprecated form, so
  its `bin_range_order` CHECK is **not enforced in the database**.
- **AP account type coercion**: an AP control account used on a bill's
  payment-term line MUST be `account_type = liability_payable` (core
  `account.move.line._check_payable_receivable` on purchase documents:
  `payment_term XOR liability_payable` must be False). The EBR CoA designates the
  non-trade payable as payable, but demo_updated_levis imported `2103300001` as
  `liability_current`, which broke non-trade bill posting. `seed_trade_ou`
  therefore coerces every mapped payable account to `liability_payable` +
  `reconcile=True` (logged). The GR/IR accounts are only used on `move_type=entry`
  journals, which that constraint does NOT check, so they need no coercion.
- Overriding a computed field's method re-declares `@api.depends` and REPLACES the
  inherited deps: `purchase.order.line._compute_analytic_distribution` restates
  the base deps (`product_id`, `order_id.partner_id`) plus `order_id.picking_type_id`.
  `account.move.line._compute_account_id` has NO base `@api.depends` (precompute-at-
  create), so the override adds none either and relies on `l10n_purchase_type` being
  set on the move at create time (via `_prepare_invoice`).
- **PO uploads go through the native `base_import`, which never runs onchanges.**
  The Quantity/Unit Price swap guard on `purchase.order.line`
  (`_check_levis_qty_price_swap`) is therefore an `@api.constrains`, not an
  onchange warning — an onchange would have been skipped by the very path the bad
  data came in on (06-Aug-2026, 18 orders at 413.011 pcs @ Rp 1). Thresholds live
  in `ir.config_parameter`: `custom_levis_localization.po_swap_guard_qty`
  (default 10000) and `.po_swap_guard_price` (default 100); either set to `0`
  disables the guard for that database. A genuine bulk order is unaffected as long
  as its unit price is above the price threshold.
- Tenant scoping is a deployment convention only — the manifest documents the Levi's databases as intended targets, but there is no runtime check preventing installation elsewhere.
- The `_cron_generate_drafts` cron is shipped with `active=False` (`data/inventory_reconciliation_data.xml:20`) and is monthly, so it does NOT run automatically unless a tenant enables it. When enabled it only creates DRAFT reconciliations/entries; it never posts.
- The payment reports are direction-guarded: the Payment Voucher renders only for outbound payments and the Payment Receipt only for inbound payments.
- `_edo_line_source_doc` must read the FAR side of the reconciliation partials —
  `matched_debit_ids.debit_move_id` and `matched_credit_ids.credit_move_id`, the way core
  does in `_compute_reconciled_lines_ids`. `matched_debit_ids` holds the partials where the
  line is the *credit* side, so reading `credit_move_id` returns the line you started from;
  that line belongs to the payment, never to an invoice, so the `move_type` filter dropped
  it and every voucher row silently fell back to the payment's own number. The NOMOR DOC AP
  and REF Invoice Vendor columns showed no bill at all until 19.0.1.25.1. The failure is
  invisible in the PDF — it looks like a filled-in column.

- **Search views here take no `<group string="Group By">`.** Odoo 19's
  `base/rng/common.rng` defines `group` with no `string` attribute and `field`
  children only, so wrapping group-by filters in one fails view validation with
  `RELAXNG_ERR_INVALIDATTR` *and* a misleading `Element search has extra content:
  field` on the line above. Group-by filters go flat after a `<separator/>`,
  which is what the receipt search view already did.
- **`account.bank.statement.line` has no SQL `date` column.** It is delegated from
  `account.move` via `_inherits`, so an ORM domain on `date` works but raw SQL must
  join `move_id` — `select sl.date ...` fails with `column sl.date does not exist`.
- **Bank narratives name stores by abbreviation, not truncation.** `LEVIS BIP` is
  Bandung Indah Plaza and `LEVIS GANCIT` is Gandaria City: there is no word overlap
  with the analytic name, so no fuzzy matcher can resolve them and guessing from
  initials would misdirect money between shops. The MID/TID is the key, and the
  wizard offers a suggestion only where the text genuinely overlaps an Operating
  Unit name. Mapping the rest is a one-off human step (~24 terminals).
- **Many cash deposits identify only the depositor, not the store.** Of 407 July
  deposits, a large share read `TRSF E-BANKING CR ... ADAM SURYONO` with no store
  word at all (Rp 61 M for that one name). The cashier's name is a legitimate and
  stable key — one cashier deposits for one shop — so those get `match_type=keyword`
  rules on the name. The wizard's `key` is editable for exactly this reason: shorten
  it to the distinctive part so next month's deposits match the same rule.
- **One merchant is printed two ways.** BCA shows `885004608375` on the debit feed
  and `004608375` on the credit-card feed. `_keys_match` accepts a suffix match from
  6 digits up, and the wizard folds suffix-equivalent ids into a single proposal —
  without that they collide on the `levis.bank.mid.map` uniqueness constraint.
  Channel is deliberately *not* part of that key: the same MID carries debit and
  QRIS, and the rule answers "which store", not "which tender".
- **The bank suspense account `1103000002` is `reconcile = False`,** and all six
  bank journals use it as their `suspense_account_id`. That is not a Levi's
  misconfiguration — it is what `chart_template.py` ships, on every tenant here,
  because Odoo never matches a suspense leg, it *replaces* it. Booking the
  counterpart in its own entry therefore nets the balance to zero while leaving
  every statement line `is_reconciled = False` forever, and **Odoo core then
  refuses to set `fiscalyear_lock_date` over the period** ("There are still
  unreconciled bank statement lines in the period you want to lock"). That is the
  July 2026 situation and the reason the design changed in 19.0.1.30.0. Do not
  "fix" it by flipping the flag: that makes the six bank journals behave unlike
  every other Odoo database and still needs a bulk match to mean anything.
  Consumption is *additionally* tracked by an explicit marker
  (`levis_clearing_line_id`), which is what a second run reads.
- **The marker is written at generation, never at compute.** Previewing a period
  must leave the database untouched, so a second run only becomes blind to July's
  settlements once the first run has actually produced drafts.
- **Allocations are paired to journal legs by position, not by lookup.** Two stores
  can produce a credit on the same account with the same analytic inside one entry;
  looking the leg up afterwards would hand both allocations the same line and then
  over-reconcile it. `_apply_to_statement_lines` zips the newly created items
  (ascending id) against the planned legs and refuses to pair at all if the counts
  differ.
- **Writing to a posted statement-line entry is normal, not a hack.** Odoo posts
  the entry the moment the line is imported, and core's own
  `action_undo_reconciliation` rewrites `line_ids` on it with
  `force_delete=True, skip_readonly_check=True`. `_apply_to_statement_lines` uses
  the same context but only *deletes the suspense leg* instead of clearing
  everything, so nothing recomputes the bank amount or its currency behind our
  back. It refuses outright when the line no longer sits on suspense — somebody
  reconciled it by hand after the plan was approved.
- **Legs are booked in company currency only.** `_preflight` refuses a statement
  line with a `foreign_currency_id`, rather than inventing a per-leg rate. All six
  Levi's bank journals are IDR.
- **`short_amount` excludes unmapped lines.** "This store had nothing open" and "we
  do not know the store" are different problems with different fixes; conflating
  them inflated the shortfall figure by ~4.3 bn on the first real run.
- **`levis_narrative_*` does not depend on `levis.bank.mid.map`.** Adding one
  store's mapping must not silently rewrite the whole statement history, so the
  fields are re-read explicitly via `action_levis_reread_narrative` (exposed as the
  *Re-read Bank Narrative* action on the Bank Settlements list).
- **`CAIR CEK UNTUK RTGS` (Rp 1.533.030.000) is classified `unknown` on purpose.**
  Its destination is not in the narrative and Treasury never confirmed it; booking
  it anywhere plausible would hide the question. Bank interest is likewise excluded
  from clearing rather than absorbed.
- **The sweep destination must not also be a statement source.** Block C debits
  `1103019320` directly, which is journal `OBCA`'s `default_account_id`. OBCA has no
  July statement lines today, so there is no double count — but the `sweep_double`
  diagnostic blocks generation if that ever changes.

- **A cash deposit may only clear the CASH tender receivable.** `_allocate` spans every
  configured tender account, which is right for a card settlement — one MID covers Visa,
  Mastercard, JCB and Amex, so the split has to be discovered. For a cash deposit the tender is
  certain, and letting it consume a card receivable clears the wrong account. Measured on the
  July 2026 data before the guard: **93.1% of cash-deposit allocations (Rp 703,965,244) landed
  on card receivables**, leaving the real cash receivable open and the card one over-cleared.
  `_pool_accounts_for_channel` restricts the pool, resolved by code from
  `ir.config_parameter custom_levis_localization.pos_cash_receivable_code` (default
  `1106000101`) and required to be one of the configured tender accounts. QRIS is deliberately
  NOT restricted: it spreads across seven accounts with no concentration, so a restriction
  would break allocations that are currently right. Expect the reported shortfall to RISE after
  this guard (July: Rp 35.3m/14 lines -> Rp 104.1m/49 lines) — that is the real gap becoming
  visible, not a regression.
- **And the mirror: a card or QRIS settlement may not clear the CASH receivable.** Different
  question, definite answer — that account holds takings paid in cash, so card money settling it
  clears an account the customer never used, and hides a real cash shortfall behind a card
  over-clear. Only 3 of 358 unambiguously matched card/QRIS settlements landed there in July
  (0.8%, Rp 2.6m): small, and wrong by construction rather than by measurement. The asymmetry is
  deliberate — cash is restricted to ONE account because its channel is certain, card/QRIS is
  merely denied ONE account because which card account it belongs to stays undecidable. Both
  branches test the channel POSITIVELY (`_CARD_CHANNELS`), never "not cash": an unread narrative
  carries channel `other` and must keep the unrestricted pool.

## Out of Scope
- This module does not cover inventory adjustments, backorders, or handling of internal transfers and manufacturing receipts. These functionalities are left to the core Odoo stock management processes.
- The GL-skip behavior focuses solely on vendor goods receipts; customer returns and outbound shipments keep posting normally.
- The payment vouchers and receipts are limited to vendor and customer payments; other types of financial transactions (e.g., intercompany) are not covered.
