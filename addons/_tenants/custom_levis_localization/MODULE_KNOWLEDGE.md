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
- **Related parties (19.0.1.35.0)**: the EBR chart splits AP four ways —
  trade/non-trade (the purchase stream, on the bill) x third/related party (a
  property of the *vendor*). `res.partner.l10n_related_party` (Boolean, tracked,
  on the Accounting tab next to Account Payable) marks in-group Erajaya
  companies; `levis.purchase.account.map.related_payable_account_id` holds the
  related-party AP per stream (`2103200001` trade / `2103400001` non-trade).
  `account.move.line._levis_stream_payable(mapping, move)` picks the account,
  reading the flag off the **commercial** partner (an invoicing child bills to
  its parent) and falling back to the ordinary payable when the related column
  is empty. Before this, PT Sinar Eka Selaras carried `2103200001` on its
  contact yet all 439 posted bills in `prd_levis_begbal` (Rp 44,58 M still open)
  landed on third-party `2103100001` — the stream mapping overwrote whatever
  core computed from the partner property. Manual bills never hit the bug: with
  no `l10n_purchase_type` at line-precompute time the override never fired and
  core's partner property stood.
- **Seeding the flag**: `setup.py::_flag_related_parties(env, companies)` (called
  from `seed_trade_ou`) ticks the flag on every vendor whose contact already
  points at a related-party AP account — the only way accounting could express
  the intent before the flag existed. It only ever ticks, never unticks, so a
  manual correction survives the next upgrade.
- **GR/IR is deliberately NOT split third/related**: the goods receipt accrues to
  the category's third-party clearing account, so routing the bill elsewhere
  would leave that accrual un-netted. Existing AP balances are left as-is —
  reclassing them is an accounting decision, not a side effect of this fix.

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

**Readiness before anything else (19.0.1.40.0).** `action_check_readiness` answers
"is this month fit to clear" in draft, without computing: it creates no lines and
leaves the run in `draft`. It exists because of August 2026 in prd_levis_begbal,
where the IBCA statement had been imported **four times** — each import restarting
at the 1st, cumulatively: 386 lines (07-Aug), 717 (12-Aug), 840 (14-Aug), 1.202
(19-Aug), for 3.145 posted rows where 1.202 were real. Nothing noticed. The run
reported Rp 10,3 m of settlements with no receivable left, which was true of the
duplicates and useless as a finding. Deduplicated on a clone the same month comes
out at 1.148 settled / 2 short / **Rp 899.730** unexplained.

* `_diag_duplicates` groups on `(journal, date, payment_ref, amount)` and then
  splits on **when the rows were written**: two sales can agree on all four, but
  rows created an hour or more apart (`_DUP_BATCH_GAP_SECONDS`) cannot have come
  from one file.
* **The copies are skipped, not blocked (19.0.1.47.0).** The client imports the
  month cumulatively — 1–7, then 1–14, then 1–31 — so repeats are the routine, and
  refusing the run over them was the wrong lever: a month with any other finding is
  booked with *Ignore warnings* ticked, and the copies would ride along with
  everything else. `_duplicate_line_ids()` maps each re-import to the line it
  repeats, `_compute_one` hangs it on the prepared row, and `_line_from_parsed`
  returns `state='skipped'`, no block, no allocation, with a note naming the entry
  it copies. It must happen **before** allocation: a copy that consumed the day's
  receivable would make the original read as short, and the run would then be wrong
  about the real line too. The diagnostic drops to `warning` and
  `_assert_generatable` no longer refuses — there is nothing left for it to stop.
* `_diag_import_incomplete` reports a journal whose statement stops before the
  period does — the August run read as a month and covered eighteen days, and
  `_diag_missing_days` by design cannot say so (it looks for *interior* gaps).
  It also reports a journal with no lines at all, which `_diag_missing_days` can
  only say after a Compute.
* `_diag_coverage` compares settlement gross against the open receivable pool
  measured **before allocation spends it**. Past `_COVERAGE_TOLERANCE` it says so
  as a ratio: the cause is never in this module — a repeated bank import, or a POS
  import that never ran — and both leave the same footprint.

**Evidence before the residual ordering (19.0.1.40.0).** `_attach_evidence` runs
between parsing and allocation and asks the trading day's receipts two questions
the narrative cannot answer:

* **Which tender receivable.** Measured on August 2026: 377 settlements had their
  tender named by the receipts and a *different* account credited by
  `_allocate`, which picks by largest residual and cannot see a tender.
  `_allocate_with_evidence` drains the proven account first and only then falls
  back to the ordinary search — a **priority, not a restriction**, so a proven
  tender that is already reconciled still gets settled instead of stranding money.
  `only_accounts` still binds: a cash deposit may not consume a card receivable
  however its receipts read, because the channel restriction answers a different
  question. `line.tender_locked` records where the receipts decided it.
* **Which trading day — the receipts no longer answer this (19.0.1.51.0).** The
  ladder is still walked looking for proof, because a receivable can be booked a
  day either side of the settlement, but what it finds only orders the
  allocation: it never renames `trans_date`. A same-amount match on a
  neighbouring day is arithmetic, not evidence about when the sale happened.
  Production, 1 Sep 2026: a QRIS settlement of 1.550.900 whose narrative said
  31/08 was moved to 30/08 because that day held a CASH sale of exactly that
  amount, and the line then reported a tender conflict against a day the store
  never traded that tender on. 124 of the 1.012 settlements in the August and
  September runs had been moved this way, every one of them by the evidence pass
  and none by the narrative.

**The trading day is anchored on the mutation (19.0.1.51.0).** `_resolve_target`
computes it as `statement_line.date - settlement_lag_days`, for every row, and
the narrative's `TANGGAL` is no longer used as the day even where it is present.
One rule beats two: the date is missing on most BCA rows, it is the acquirer's
batch date rather than the store's trading day, and honouring it where present
only made two kinds of row behave differently. The narrative date is kept as a
cross-check — `trans_date_is_derived` now means *the bank did not name this same
day*, whether it named none or a different one — and the run's warning banner
counts those.

`_allocation_order` then allocates proven settlements first. Order decides who
gets the money when the pool is thin, and a proven claim beats an unproven one;
statement order is kept inside each group so a rerun allocates identically.

**`leg` / `leg_partial`: when the gross names nothing, ask the receivable.**
`_x24_identify` searches inside one tender, so a bank line paying two tenders at
once (Visa's whole day *plus* Mastercard's whole day, one BCA credit) stays
`none` however plainly the money reads. `_x24_identify_legs` asks the smaller
question instead: `line._x24_alloc_legs()` turns the allocation into
`(tender, trading day, amount)` — the tender read off the account name, which is
the only place it survives — and each leg is put through the *same*
`_x24_identify` against that tender's bucket of that day. Nothing weaker than a
proof is accepted; what changed is the target, not the standard. All legs proven
reads `leg`, some of them `leg_partial`, and an unproven leg names nothing at
all: a leg is a residual whenever several bank lines share a day's receivable,
and a residual need not be a whole number of transactions. This is only ever a
*fallback* — a line the gross already explains never reaches it — so it cannot
weaken the `exact`/`batch`/`subset` readings. Measured on run 10 of
`prd_levis_begbal`: 41 more lines fully named, and 407 of the 949 legs in
still-unnamed lines given their receipts. It also reaches a day the line's own
ladder walked past, so `_generate_receipts` widens its `_x24_rows` window to the
allocation's dates and stamps each candidate with the day it really came from.

**`subset`: a unique combination is proof, an ambiguous one is not.** `_x24_subset`
extends `_x24_identify` with a bounded meet-in-the-middle search *per tender*.
The doctrine is unchanged — only arithmetic counts — but a combination that is
the **only** way to make the number is arithmetic. Two tenders that can each make
it, or one tender that can make it twice, name nothing. Bounded twice:
`_SUBSET_MAX_ITEMS` (20 candidates after dropping anything above the target) and
`_SUBSET_MAX_SOLUTIONS` (stop at the second). `_subset_totals` reaches each subset
sum one addition from a known one, which is what keeps the search from becoming
the slowest step of a 3.000-line run; the callers additionally memoise per
`(store, day, gross)`. On a deduplicated August it fires on **470 of 1.130**
allocations. It does not move the totals — greedy reached the same accounts —
which is a narrower claim than it sounds: there was almost nothing left to correct.

**Bulk instead of line by line.** `action_match_proven` re-ticks everything the
amounts prove across a whole run, which matters after mapping a MID: a line only
becomes readable once it has a store, and without this the month would have to be
recomputed — throwing away every tick already made — to collect free ticks.
`action_suggest_receipts` takes a recordset, so a selection in the settlement list
can be built as a batch (the `<header>` button); the cost is per line either way.

**The mapping wizard proposes from takings, not from names.** `_evidence_suggestions`
indexes every store's X70D transactions by amount — single transactions, and each
tender's day total — and votes: a deposit that equals exactly one store's cash for
exactly one trading day says which shop it came from without reading the narrative
at all. A figure that fits two stores votes for neither, and a group whose best
store does not beat the runner-up is left for a person. `evidence_note` on the
wizard line says why; empty means the old name-overlap guess and nothing
corroborating it. Silent when the OU field or the staged rows are absent.

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

## Feature 20 — The store's settlement day (`levis.pos.clearing.store.day`)

Phase 5, and the same projection cut the other way. Feature 19 answers "is the
12th done?" for a bank feed; the store accountant asks something narrower that
had no home: *for this shop, did the money the bank paid on H match the tenders
the shop rang up on H-1, and if not, which transaction is missing?*

One row per **store operating unit per settlement date**, rebuilt wholesale by
`_rebuild_for_run`, booking nothing. `line.store_day_id` is the one column it
adds. Lines with no store are skipped rather than bucketed under a blank: an
unmapped merchant id belongs to no shop, and inventing a row for it would put
money against a store nobody chose.

### Three figures, not one

The bank pays net of the acquirer fee and the store rang up gross, so a single
"statement vs sales" number would report the MDR as a shortfall every day. The
row therefore carries `statement_total` (what hit the bank), `gross_total` (what
that was worth before the fee) and `x70d_total` (what the store sold).
`variance` compares the two comparable ones; `variance_bank` is kept beside it
for whoever reads the bank book rather than the ledger.

**Money in is takings only** — `kind in _SETTLING_KINDS`. A sweep to the pooling
account is the same money leaving again and its `gross` is a sign artefact of the
narrative reader; comparing either against sales would be nonsense. In practice a
sweep also carries no merchant id, so it names no store at all.

**Cash is included, and split out.** By instruction the comparison covers every
tender, cash among them, with `x70d_cash_total` in its own column: a store whose
card money is perfect and whose till is still in the safe shows a variance
exactly equal to the cash, which is information rather than a defect.

### The sales side is the feed, not the ledger

`_x70d_rows` calls the matcher's own `LevisPosClearingAlloc._x24_rows`, so the
reconciliation and the receipt matching can never disagree about what a trading
day holds — same extraction, same `OFFLINE_OTHER_CARD` fold, same store-code
route. `levis.pos.x70d.txn` (Feature 21) exposes the very same query as a
read-only SQL view so the transactions can be listed under the totals.

### Per tender, which is where a misposting becomes visible

`tender_ids` puts what the store rang up on a tender beside what the run credited
to that tender's receivable (read off the account name — `POS Receivable -
OFFLINE_VISA` and nothing else says Visa). The allocation consumes open
receivables largest-residual-first and cannot see a tender, so a settlement can
be booked to the wrong one; on the settlement alone that is invisible, here it is
a pair of equal and opposite differences with the day's total still nil.

### Reached without recomputing

`action_view_store_days` (run) and `action_open_store_days` (settlement list)
rebuild the projection on the way in. A run computed before this screen existed
would otherwise need `action_compute` to get its rows — and that rebuilds the
settlements from scratch, taking every receipt tick with them.

### Measured on real data (prd_levis_begbal, August 2026)

Run POSCLR/2026/0001: 1 209 lines → **393 store-days in 14 seconds**. OLS SES —
AEON BSD CITY tallies to the rupiah on 11–17 August. On 18 August it reads
-1 550 900, and the tender breakdown says why in one line: `CASH 1 550 900`
rang up, nil cleared — the till of the 17th, not a missing settlement. The three
card tenders of that day match exactly.

## Feature 21 — The X70D tender file, browsable (`levis.pos.x70d.txn`)

A read-only SQL view over the JSON `custom_retail_import` stages on
`retail.import.line` for `file_type = 'x70d'`, resolving store code →
`pos.config` external id → warehouse → operating unit exactly as the matcher
does. A **view, not a table**: nothing is copied, a re-imported day is right here
the moment it is right there. Where the retail import is absent `init` creates
the view **empty rather than not at all** — the clearing must keep working on a
database with no feed, and a missing model would break every screen that reads
this one.

## The August 2026 gap was a duplicate import, not a reconciliation problem

Worth reading before anyone builds a matcher to close a gap in this module.

**IBCA August statements were imported four times into prd_levis_begbal**, each
run reloading the file cumulatively from 1-Aug: 386 rows on 07-Aug, 717 on
12-Aug, 840 on 14-Aug, 1 202 on 19-Aug. 3 145 posted rows where 1 202 are real —
a factor of 2.62. July is clean (2 111 of 2 111), so this is specific to August.

    select count(*), count(distinct (mv.date, sl.payment_ref, sl.amount))
      from account_bank_statement_line sl
      join account_move mv on mv.id = sl.move_id
      join account_journal j on j.id = sl.journal_id
     where j.code = 'IBCA' and mv.date >= '2026-08-01' and mv.date < '2026-09-01'

Measured on a clone, deduplicated by keeping one row per
(date, payment_ref, amount):

| | as imported | deduplicated |
|---|---|---|
| clearing lines | 3 149 | 1 206 |
| ok / short | 1 853 / 1 169 | **1 148 / 2** |
| Σ short_amount | 9 044 212 116 | **899 730** |

**The nine-billion "unexplained" was an artefact.** The duplicate lines promised
the open receivable pool away to statements that do not exist, so every line
processed after them found nothing left and reported itself short. On real data
the clearing already resolves 1 148 of 1 206 lines and leaves under a million
rupiah outstanding on two of them.

It also moves the bank GL: IBCA August turnover reads ~20.98 bn against a real
~8 bn, and the net is out by 940 983. The three early batches are all `posted`,
so correcting production means deleting 1 943 statement lines and their journal
entries — not something to do without a decision. It is being handled separately;
do not "fix" it from here.

**Correction to what this file said earlier.** A previous version of this section
concluded, from the *duplicated* run, that subset matching "abstains on ~95%" and
"has not earned its place". Both figures were measured on corrupt data and are
withdrawn. On the deduplicated month subset matching participates in 470 of 1 130
allocations (42%). It still does not change the totals — the greedy pass reaches
the same answer — but that is a much narrower claim than the one made before, and
it rests on there being almost nothing left to improve rather than on the search
being useless.

The lesson generalises: **measure the input before drawing a conclusion from the
output.** A ratio of gross to open receivables far from 1.0 (this run: 20.8 bn
against 11.65 bn, i.e. 1.79) is a signal that the statement side is inflated, not
that the receivable side is missing.

## Evidence-led allocation (`feat/pos-clearing-evidence`) — design notes inherited

Written by the session that built the receipt subsystem, recorded here because
none of it is visible in the code and all of it was paid for once already.

**Receipt evidence is a priority, not a restriction.** `_allocate_with_evidence`
drains the tender account the receipts name first, then falls back to the ordinary
largest-residual search. Making it a restriction would strand money whenever a
proven tender's receivable happens to be already reconciled — a case the old
behaviour handles correctly. This is deliberate; do not "fix" it into a
restriction.

Traps already hit, so nobody hits them twice:

* **`only_accounts` still binds, above the evidence.** A cash deposit landing on a
  trading day that also holds a card transaction of the same amount will
  "prove" itself against the card. Wrong: the channel restriction answers a
  different question from the one receipts answer. Covered by
  `test_evidence_never_lets_a_cash_deposit_clear_a_card_receivable`.
* **Tender is read from the account NAME** via `_x24_tender_of_account`, prefix
  `POS Receivable - `. A test fixture whose account is called "POS Debit Card"
  silently yields zero evidence — it does not fail, it goes quiet. If a tender
  field ever lands on the account, prefer it to name-matching.
* **Receipt exclusivity is deliberately NOT in the evidence pass.** `x24_match` /
  `x24_tender` are stored computes, and a compute that depends on processing
  order is not idempotent. `_x24_identify` stays stateless; exclusivity lives only
  in the worksheet. Two twin settlements in a day will point at the same
  receipts — same tender, so no account is harmed.
* **The day ladder is walked to find evidence**, and a day whose receipts fit
  replaces the guessed day. `trans_date_is_derived` deliberately stays true: the
  narrative still never stated a date, only the guess got better.
* **Performance.** Subset search is the only expensive step. Three guards: a
  20-candidate cap counted *after* dropping items larger than the target,
  `_subset_totals` reaching each subset sum one addition from a known one, and
  memoisation per (store, day, gross) in both `_attach_evidence` and
  `_compute_x24_trans`. Without the memo a 3 000-line run is dominated by it.
* `_x24_subset` refuses to name anything once two tenders can both compose the
  figure — it does not pick the tidier one. Same for one tender with two
  solutions.

**Two subset-sum implementations must not coexist.** `levis.clearing.matcher.
_subset_match` (tolerance + node budget, used by bank reconcile) and `_x24_subset`
(faster, stricter, zero tolerance) do the same thing. Whichever survives, the
other should call it.

### The dedup script

`scripts/tenants/levis/100_dedupe_bank_statement_imports.py`, on branch
`feat/pos-clearing-evidence`. **Never run anywhere, not even dry.** Env:
`LEVIS_DEDUPE_APPLY=1` (without it, reports and rolls back),
`LEVIS_DEDUPE_JOURNAL` (default IBCA), `LEVIS_DEDUPE_FROM` / `_TO`.

Its duplicate rule is deliberately identical to `_duplicate_groups` in the module
— group on (journal, date, payment_ref, amount), split on a `create_date` gap of
≥ 3600s — so the readiness gate and the script cannot disagree about what a
duplicate is. It refuses (lists rather than deletes) any line already reconciled,
already held by a `levis_clearing_line_id`, or carrying legs other than
Dr bank / Cr suspense.

Before APPLY: dump, then dry-run on a clone and compare its count against the
1 943 measured independently here.

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

## Feature 22 — GR/IR auto-reconciliation when a vendor bill is posted

A goods receipt books `Dr Stock Valuation / Cr GR/IR` and the vendor bill debits that same GR/IR
account, so the accrual is *routed* to net. What never happened is the matching: nothing ever
called `reconcile()`, so both legs sat on the clearing account for ever and GL Open Items grew
without bound — 68,345 open lines by Sep-2026. Sheet row #42 reports the symptom.

**It nets per `(account, purchase order line)`, never pair-by-pair, and that is not a style
choice.** Matching each bill line to "its" GR leg with a rounding tolerance cannot work on this
data. Across all 42,922 posted GR/IR bill lines in `prd_levis_begbal` only **41 %** agree within
Rp 0,02; 25,187 do not match at all, 15,198 of them by more than Rp 1.000, totalling
**Rp 2,52 miliar**. Two structural reasons, neither arithmetic:

* **Partial receipts.** `BILL/T/EBR/2026/08/00224` has 200 lines against 200 PO lines and
  **600** done stock moves — three receipts per line. There is no pair to make.
* **Different bases.** The receipt is valued net of recoverable tax (`stock.move.value`); the
  bill line is not. `BILL/T/EBR/2026/08/00064` joins 1:1 and still differs by Rp 22,7 jt.

So `account.move._post()` gathers every GR/IR leg of the bill and every GR/IR leg of every
goods-receipt entry on the same PO lines, and reconciles the whole group. Odoo nets it and leaves
one residual — which *is* the not-yet-billed position, and exactly what #42 asks the clearing
account to show. On the bill above: Rp 382.589.826 credited by receipts against Rp 172.337.759
debited by the bill, leaving Rp 210.252.067 genuinely unbilled.

Receipts are found through `stock.move.purchase_line_id` and their entries through the
`GR-VAL:` / `GR-RET-VAL:` ref stamped per stock move. **A credit note nets against the return
entries, not the receipt ones** — matching an RTV against the original receipt would net two
unrelated positions.

**`account.move.line._levis_grir_account()` is the single definition of "is this a GR/IR leg".**
Two callers need the same answer — `_compute_account_id` routes the line at create, this feature
recognises it again at post — and two copies of five gates would drift silently: a line routed to
GR/IR but not recognised at post simply never nets. The gates are documented on the method.

Switched by `custom_levis_localization.grir_auto_reconcile` (default `1`); `0` stops it instantly,
which is the rollback. Context key `levis_skip_grir_reconcile` for callers that must opt out.
Failure is caught and logged — the bill is already posted and correct, and a clearing entry that
did not net is a follow-up, not a reason to refuse the document (same contract as the COGS
catch-up).

**The importer needed the other half.** `_compute_account_id` is a *precompute* with no
`@api.depends`, so a create that supplies `account_id` skips routing entirely — which is what the
bill importer does, and why imported bills kept landing on COGS while the accrual stayed open.
`account.move.line.create()` now re-applies the routing, narrowly: only a draft bill line with a
PO link where every other gate already agrees, and it derives `l10n_purchase_type` from the order
when the importer left it blank. A hand-picked expense account on a line with no purchase order is
never touched.

## Feature 23 — The COGS charge ledger is the only guard against charging twice

`levis.cogs.charge` is not bookkeeping colour: `levis.cogs.run._detail()` subtracts it
before proposing anything, and the receipt catch-up does the same. A run generated by a
version that predates the ledger is therefore **invisible** to every later run — it booked
the cost, and nothing records that it did.

That is sheet #74. On `prd_levis_begbal`, `COGS/2026/0001` (June) is posted against
`GLJV/2026/06/0032` and left **0** charge rows, while July left 14,715 and August 9,685.
Re-running June proposed the entire month again: 657 lines, 7,441 units,
Rp 4,227,985,550 — which is what the client saw.

- `_generated_runs_without_ledger()` finds overlapping generated runs whose ledger is
  empty; `_check_charge_ledger()` refuses to compute or generate over them. The failure is
  loud on purpose — the silent version of it is the bug.
- `action_backfill_charges()` reconstructs the ledger of such a run. It is sound precisely
  *because* the ledger is empty: `_detail()` subtracts nothing, so it reproduces the detail
  the run booked. Proven in production, not assumed — the June re-run returned the same 657
  lines and 7,441 units, and `zero_cost_qty` was 0 on **all** of them in both runs, so no
  part of the reconstruction is ambiguous. `scripts/tenants/levis/115_backfill_cogs_charge.py`
  drives it, dry-run by default.
- `_record_charges()` now logs a warning when it books cost but writes no row. That is the
  shape of the original defect, and it should never pass silently again.

## Feature 24 — Bulk reset to draft (sheet #76)

`account.move.action_levis_reset_to_draft_selected()`, bound to the Journal Entries list for
`account.group_account_manager`. It changes nothing about what a reset *means* — Odoo 19
still keeps the reconciliation, and re-posting still recomputes the hand-keyed PPN/PPh lines
— it only stops one entry refused by a period lock from discarding the resets before it.
Each move gets its own savepoint and the refusals are reported together. Tenant-scoped
deliberately: the two hazards above make this a poor platform-wide default.

## Feature 25 — Operating Unit is mandatory on P&L lines (sheet #36)

The client re-opened #36 on 16-Sep with a specific case: *"masih ada transaksi ke COA
P&L yang tidak mengisi operating unit tapi tetap bisa diposting (Hasil cek: bank admin)"*.

The bank-admin case is **not** a broken code path. `account.payment.register.
_prepare_admin_fee_write_off_vals` already merges the wizard's OU into the fee line;
what is missing is anything that makes an operator fill the wizard's OU in. So the
answer is a gate on posting, not another stamping hook — which is also why looking for
the "bug" in the admin-fee module is a dead end.

- `_levis_check_ou_required()` runs from `_post`, **not** `@api.constrains`: a constraint
  is validated at flush and an elevated env can walk straight past it.
- `_levis_pl_account_ids(company)` is one SQL per company per post, reading
  `code_store->>'<cid>'`. Never read `.code` per line — it is company-dependent in
  Odoo 19, so a per-line read is a Python round-trip on the hottest path in accounting.
- An OU counts whether it sits in `l10n_ou_analytic_id` or anywhere inside
  `analytic_distribution` — keys are comma-joined analytic ids, one per plan, so the test
  is membership on the split, never a substring on the key.
- `custom_levis_localization.ou_required_pl` defaults to **0**, and
  `levis_skip_ou_required` in the context is the emergency door (it logs a warning).
  Measured on `prd_levis_begbal` for 2026: 21,988 posted P&L lines, **79** with no OU —
  GLJV 50, OBCA 12, EBRTB 6, IBRI/IMand/IBNI/BILL 9, DEPRE 2. Finance backfills those
  from `scripts/tenants/levis/116_report_pl_lines_without_ou.py` first; flipping the
  switch is a separate, reversible step.
- The header onchange now cascades to every line except `line_section`, `line_note` and
  `payment_term` — the last is the receivable/payable leg, which the Operating Unit has
  no business on. Restricting the cascade to product lines is what made the header field
  look like it had not worked on exactly the entries #36 is about.

## Feature 26 — Inventory adjustments get a document number (sheet #70)

Odoo 19 books an inventory adjustment as bare `stock.move` records with
`is_inventory = True` and **no picking**, so there is no document to point at and two
unrelated counts on the same day are indistinguishable in the Reference column.

The hook already exists in core: `stock.move.inventory_name` feeds `_compute_reference`,
and `stock.quant._get_inventory_move_values` picks it up from the context. So
`stock_quant.py` draws **one** number per `_apply_inventory` — one count is one document,
however many lines it touches — from the `levis.stock.adjustment` sequence
(`STADJ/YYYY/MM/NNNNN`, `noupdate="1"` so an upgrade never resets a drawn number) and lets
core carry it. Do not reach for a new model; there is nothing to model.

The sibling numbering — `GR/<wh>/YYYY/MM/NNNNN` and `INTF/<wh>/YYYY/MM/NNNNN` per picking
type, `STSCP/YYYY/MM/NNNNN` for scrap — is configuration, not code:
`scripts/tenants/levis/120_set_document_numbering.py`. **The warehouse code is not
optional in INTF**, even though the client's example omits it: each of the 34 internal
picking types owns its own sequence, so a shared prefix would run 34 counters in parallel
and mint duplicate document numbers.
## Feature 27 — The store-day proof, and the run that books only what it proves

Month-end at Levi's was days of wizard work because the clearing had no way to
say "this part is not in doubt". It now has one, and it is the only thing in
this feature that is new arithmetic: everything else is the existing engine,
narrowed.

### The unit is a store's trading day, never a settlement line

A settlement cannot be checked against a receivable one at a time. The bank's
channels (debit, credit, QRIS) and X70D's tenders (ten accounts) are two
different partitions of the same money. The case that settles it, measured on
`prd_levis_begbal`, PIM 2 on 3 September 2026:

| Bank paid | X70D booked |
|---|---|
| debit 17.605.500 | DOMESTIC_CARD 69.099.900 |
| QRIS 65.499.000 | OTHER_CREDITCARD 14.004.600 |
| **83.104.500** | **83.104.500** |

The totals are one figure to the rupiah and no member of either side is a subset
of the other. One MID covers Visa, Mastercard, JCB and Amex alike and
`levis.mdr.bin` is empty, so nothing states which of the ten accounts a
settlement pays. Below the day, the two sides are not comparable at all.

### Why the line-grain routes were rejected, with the numbers

Measured over the 1.125 open September settlement lines:

* `_get_auto_match_candidate`'s existing rule — one candidate whose residual
  equals the gross — reaches **27 %** (246 of 916 at the time of measuring).
* Feeding `levis.clearing.matcher._subset_match` the same question per line,
  composing **whole** receivable rows, also reaches **27 %** (312 of 1.125,
  Rp 1,08 miliar). It is not a tuning problem: the split genuinely does not
  line up, so most lines have no whole-row subset at all.
* Weighing the **store-day** instead: **289 of 457 store-days** tie to the
  rupiah in the ledger — Rp 5,12 miliar of Rp 7,27 miliar. That is the
  arithmetic ceiling. What the engine actually proves is lower, because the
  blocking rule below takes some of those days away; the measured figure is in
  "What a September clone produces".

The reason the third works where the first two cannot is `_allocate`, which
takes `min(left, remaining)` and so may spend part of a receivable.
`_reconcile_with_amls` in `custom_account_reconcile` cannot: it creates one
counterpart per AML at the **full** residual. That single difference is why this
lives in `levis.pos.clearing` and not in the bank-reconcile wizard.

### `_prove_store_days` — the gate

Runs in `_compute_one` immediately after `_attach_evidence`, **before** the
allocation loop, because allocation spends the very residual the proof reads.
Groups card and QRIS settlements by `(analytic_account_id, trans_date)`, sums
`parsed["gross"]`, and weighs it against that key's open residual on
`pos_receivable_account_ids` **less the CASH account**. Six verdicts, stamped on
every line of the group as `proof_state` with `proof_ledger_total` beside it:

* `exact` — ties to the rupiah. Evidence.
* `subset` — the day holds more, and exactly one combination of its open items
  makes the gross. Evidence, and only when `advanced_matching` is set. One
  nuance of `_subset_match`'s contract is easy to misread: a lone item equal to
  the gross short-circuits the composition search, so a day holding a single
  500.000 alongside a 300.000 + 200.000 pair takes the single one rather than
  reporting ambiguity. Uniqueness is required of the *compositions*; a single
  item matching to the rupiah is the standard `_get_auto_match_candidate` has
  always applied.
* `over` — the bank paid more than the day sold. A backlog, or a day imported
  twice. Books nothing.
* `under` — part of the day has not been settled yet. Books nothing.
* `no_sales` — the day has no receivable at all. Books nothing.
* `blocked` — see below. Books nothing.

**Zero tolerance, and `config._match_tolerance()` is never called here.** Its own
docstring forbids it: a tolerance widens what is *offered to a person* and must
never size, absorb or book anything. A tolerance inside a booking predicate
launders a shortfall into a fee. `_EPS` stays what it has always been, float
noise.

### Cash is on neither side, and that is the defence

Two things happen in the shops that would otherwise poison this arithmetic, both
raised by the client:

1. **A sale rung up manually and banked before it ever reaches XStore.** Money
   in, no receivable behind it.
2. **A till deposited days late** because the bank was shut or the field had a
   problem. The H-1 assumption collapses entirely.

Neither can reach the proof: `levis_channel = "cash"` never joins the bank side
and the CASH receivable never joins the ledger side — the same asymmetry
`_pool_accounts_for_channel` already keeps for allocation, for the same measured
reason. What they do instead is show on the store-day screen as a variance
exactly the size of the cash, which is what that screen was built to say. The
sanctioned route for cash remains `levis.store.cash.deposit` with a validated
*berita acara*, whose `_find_for_statement_line` returns a record only when
exactly one candidate fits.

`deposit_match_window_days` (default 3) is still **not read by anything**, and
it cannot usefully be switched on yet: `levis.store.cash.deposit._find_for_statement_line`,
the only thing the window would parameterise, has no production caller either —
its `window_days=3` default is reached only from its own tests. So the field is
inert twice over, and wiring it before the cash path exists would be wiring a
knob into nothing.

When that path is built, two things are already known about it. Three days does
not survive a long weekend, which is scenario 2 above and the reason the default
is wrong rather than merely conservative. And the search direction is right as
it stands: it looks only backwards from the bank date, because money is paid in
on or before the day it lands.

### An unreadable line poisons its whole bank day

A money-in line that is `unparsed`, or a settlement whose MID is unmapped, could
be any store's takings on that date. It therefore blocks **every** group sharing
its `(journal, bank date)`, not only itself. A settlement whose channel could not
be read blocks its own group for the same reason: it is money the day holds and
the proof cannot weigh, and leaving it out of the sum while calling the remainder
exact would be arithmetic over a set already known to be wrong. A narrative that
disagrees with the money it moved (`levis_amount_matches_narrative`) blocks its
group too.

A **negative** line blocks nothing — a sweep out or a bank charge cannot be a
shop's takings.

**This rule is expensive, and here is what it costs.** Measured on the
September clone: **6** `(journal, bank date)` pairs carried an unreadable or
unmapped money-in line, and those six days blocked **89 store-days — 234
settlement lines, Rp 1,55 miliar** that would otherwise have been weighed. Two
unmapped MIDs and a handful of unparsed narratives are the whole cause.

That is the rule working, not failing: those days genuinely hold money nobody
can attribute, and clearing the rest of the day would be arithmetic over a set
known to be incomplete. But it does put the incentive somewhere specific —
keeping `levis.bank.mid.map` complete and the narrative grammars current is now
what makes the automation earn its keep, and the mapping wizard is one screen
away. Re-measure this figure each period; a rising one means the feeds have
drifted, not that the rule needs relaxing.

### The load-bearing change: a proven day is spent on itself

`_line_from_parsed` used to pass `_candidate_dates(primary)` — a ±`lookback_days`
ladder — into `_allocate_with_evidence` for every settlement. A proven group
`(store, D)` allowed to reach `(store, D-1)` breaks the neighbour's tie *after*
that tie was measured, which makes proving anything pointless. So a proven line **on a narrowed
run** gets `dates = [primary]` and `pin=True`, and `pin` also stops the
receipts' evidence day from lengthening the ladder again.

**The pin binds a narrowed run only, and so does the allocation order.** A wide
run records the verdict and otherwise allocates exactly what it always did —
pinning it would leave a neighbour's receivable open where it used to clear,
which is a behaviour change dressed as a safety measure. That is the inertness
contract, and `test_a_wide_run_still_reaches_the_neighbour_it_always_reached`
is the mirror of the pin's own regression test. The evidence account keeps its
priority: draining the named tender first **inside** the proven day changes
nothing about the day's total. `tests/test_auto_clearing.py` guards this with a
neighbouring receivable of exactly the settlement's gross — the most tempting
thing a greedy largest-first search could find.

A proven line that still comes up short raises rather than booking: the group's
two sides were equal when weighed, so a shortfall means the code disagrees with
itself. Compute creates nothing, so it is the cheapest place to say so.

### MDR is the printed fee, and QRIS's zero is a real zero

Inside a proven group `ratio == 1`, so `mdr_booked == parsed["mdr"]` exactly.
`_counterpart_plan` emits the MDR leg only when the fee is non-zero, so a QRIS
settlement with `DDR: 0.00` produces a two-leg entry and needs no special case.
**Do not "fix" that by looking up a rate.** September: 1.973 of 1.980 debit and
1.243 of 1.243 credit settlements carried an MDR; QRIS genuinely does not.

### `auto_only` — the narrowed run

A run with `auto_only` set books the store-days it proved plus block C (the
bank's own sweeps and charges), and marks every other settlement `skipped` with
`block = False`, so `action_generate_moves` produces no legs for them with **no
change to stage 2 or stage 3**. Narrowing the run's *scope* is what made the
deferred `_generate_moves(lines=None)` refactor — "the riskiest change in the
whole plan" — unnecessary.

Two consequences worth knowing:

* **`_mark_statement_lines` was fixed first, in its own commit.** It claimed
  every line carrying a `statement_line_id`, skipped ones included. A narrowed
  run would then lock the lines it had *not* booked out of the wide run that was
  meant to finish them, because `_assert_generatable` reads a foreign claim as a
  refusal. It now claims only lines that produced legs.
* **A narrowed run is exempt from the unparsed / unmapped / mismatch warning.**
  Not as a convenience: it books none of those lines, and an unreadable money-in
  line already blocks every store-day sharing its bank day, which is a stronger
  guarantee than the tick the warning asks for. Asking for the tick as well
  would only teach an operator to set `ignore_warnings` by reflex. The
  `sweep_double` blocker is **not** waived — block C is booked by every run.

### The driver prepares and never posts

`_cron_auto_clear` → `_auto_clear_company` → `_auto_clear_dates` →
`_auto_clear_one`. It walks as far as a prepared plan and stops; posting is
still a person who has read the summary. A date is eligible when it is
`auto_clear_delay_days` old, sits after the lock date, has unclaimed unreconciled
lines, is not covered by any non-cancelled run, and its newest statement line is
older than `_DUP_BATCH_GAP_SECONDS` — the same constant that defines "the import
has settled" for `_duplicate_groups`, borrowed so the two definitions cannot
drift apart.

* **A cron, not a queue job.** The queue runner keys pending jobs by UUID across
  every tenant database and a duplicated database has been enough to crash-loop
  it for all of them. A job touching receivables is the last place to accept a
  failure mode shared with every other tenant.
* **Not hooked to the import.** Statements arrive cumulatively (1-7, then 1-14,
  then 1-31), so an import is not the event "a new day exists"; clearing on that
  hook would race the dedup that reads it.
* `pg_try_advisory_xact_lock` per company, so two passes — or a pass and a
  person — cannot spend the same open items. Each date gets its own savepoint
  and a `UserError` is logged with the date rather than abandoning the rest: a
  cron that raises retries forever.

### Switches, and what each one now means

* **`auto_clear_enabled`** (new, default off) with `auto_clear_dry_run` (default
  **on**, stop after Compute), `auto_clear_delay_days` (2) and
  `auto_clear_max_dates` (5). The cron record also ships `active="False"`, so
  the feature is off twice over.
* **`advanced_matching`** finally has a reader, and it is the meaning the field
  was declared with: it gates the `subset` tier, and only there are
  `subset_max_items` and `subset_node_budget` read. It was deliberately **not**
  reused as this feature's on/off switch — repurposing a switch for a different
  meaning is how a Finance user turns on something they never read about.
* `_subset_match` now has a production caller. The note that it and `_x24_subset`
  are two implementations of one search still stands as separate work; do not
  carry subset search back into `_x24_identify`.

### What a September clone produces

Measured, not estimated: a narrowed run over 2026-09-01..30 on a clone of
`prd_levis_begbal`, 1.363 open statement lines, `advanced_matching` off.

| Store-day verdict | Days | Settlement lines |
|---|---|---|
| `exact` | **226** | **570** |
| `blocked` | 89 | 234 |
| `no_sales` | 124 | 278 |
| `over` | 10 | 32 |
| `under` | 8 | 11 |
| no card settlement at all | 5 | — |

**Rp 3.887.852.400 proven, carrying Rp 17.108.954 of MDR, and `short_total` on
the proven lines is exactly zero** — every proven line allocated in full, so the
"proven yet short" guard never fired on real data. 570 lines land in block A, 18
in block C (the bank's own sweeps and charges), and 692 are skipped with a
reason. `no_sales` is feed gaps rather than accounting differences: nine
Sulawesi/Kalimantan stores whose sales never reached X24/X70D (PR #243 puts them
in the canonical store map) and 13 + 15 September missing for every store.

The gap between 226 proven days and the 289 the ledger arithmetic allows is the
blocking rule, and it is accounted for above to the day. A materially different
set of numbers, once that is subtracted, means the key, the anchor or the pool
restriction is wrong — not that a tolerance needs loosening.

**Inertness, measured the same way.** A *wide* run over the same period on the
same clone, before and after this feature, produces the same 1.363 lines, the
same Rp 7.721.009.359 gross, the same Rp 6.318.390.681 allocated, the same
block A/B/C totals, the same 1.657 allocation rows, and the same hash over every
`(statement line, source item, amount)` triple: `12b59f19f96ea4f7`. The verdict
is recorded on a wide run and binds nothing. That is the inertness contract the
config file already states, and `test_a_wide_run_is_unchanged_by_all_of_this`
is its test.


## Feature 28 — COGS inside the POS session's own closing entry (sheet #16)

The client reopened #16 twice. The second time they were explicit: *"COGS yang
di-compute oleh Odoo in total sesuai dengan Report Sales Detail Juni-Agustus, namun
line GL COGS belum melekat ke masing-masing jurnal Sales"*. The totals were never the
problem — the attachment was.

A session is one store on one day, so its closing entry is exactly the document the
COGS belongs on. `custom_retail_import_pos` already proves the insertion point:
`_create_account_move` runs while `move_id` is still draft and under
`check_move_validity=False`, so a balanced pair can be appended and `_check_balanced`
still passes. Do not invent a new hook.

Three things make this safe rather than clever:

- **🔴 The cutover date is mandatory and empty by default.**
  `custom_levis_localization.cogs_session_start` starts blank, so the hook does nothing
  until somebody names a date. June–August 2026 are already booked by
  `COGS/2026/0001..0003`; a date earlier than the cutover charges them a second time, and
  that is the one mistake here that cannot be undone.
- **Every charged unit is written to `levis.cogs.charge` with `source = "session"`.**
  That ledger, not the journal, is what stops the monthly run and the receipt catch-up
  from charging the same unit again (Feature 23). A new Selection value needs no `-u`.
- **Failure never blocks the close.** The retail import closes sessions in bulk; a COGS
  problem must not hold up the day's sales. The block logs and gets out of the way, the
  same contract `stock_move.py` keeps for receipts.

Units whose `standard_price` is still zero are skipped **in silence** and left to the
receipt catch-up. Booking zero would put a meaningless line on the entry and, worse,
write a charge row claiming the unit had been costed. Lines are grouped per product
category so one session cannot grow hundreds of journal lines.
## Feature 29 — The recon workbook, out and back again

Odoo maps what it can, a person maps the rest in the workbook Finance already
reconciles in, and the finished workbook comes back. Three pieces:
`levis.clearing.ebr` (the export), `levis.clearing.recon.upload` (the import)
and `levis.clearing.manual.map` (the part that has to outlive a recompute).

### The workbook is the client's, not ours

The export mirrors the EBR workbook Finance has always filled in by hand —
`MUTASI <BANK>` per bank, `COMPILE SALES`, `AR <previous month>`, `SUMMARY` —
with every column Odoo can answer already answered. The columns and their
sources:

| EBR column | Source |
|---|---|
| CASH IN/ATS | `line.kind` — settlement/cash deposit → `CASH IN`, sweep → `ATS`, charge → `BIAYA ADMIN`, interest → `BUNGA` |
| METHOD | `line.channel` → `DEBIT` / `KREDIT` / `QRIS` / `CASH` |
| MID NO, MDR, AMOUNT PAYMENT | `line.mid_key`/`tid_key`, `line.mdr`, `line.gross` — all read off the narrative |
| REMARKS | `stock.warehouse.levis_ebr_label` + the bank, e.g. `SENCY CEK (BCA)` |
| Cabang | never filled — the branch code is not on the imported line, but the column stays so the geometry matches the sheet Finance pastes into |
| Store code / Store Name | the warehouse's `l10n_store_code` behind `line.analytic_account_id` |
| STATUS | `ok` → `REKON DONE`, `short` → `SELISIH`, `skipped` → `SKIP`, unmapped → blank |

Two sheets deviate from the client's on purpose. `SUMMARY` is the store-day
reconciliation (`levis.pos.clearing.store.day`) rather than a sales pivot,
because the question month-end actually asks is the variance. And `COMPILE SALES`
leaves `CASHIER LOGIN ID`, `CASHIER NAME` and `METODE PEMBAYARAN` blank and says
so on the sheet: the first two are in the X24 item feed rather than X70D, and the
third is the client's own acquirer label, not feed data. Filling them with
something plausible would be worse than leaving them empty.

A settlement that is mapped, allocated and merely has receipts nobody has ticked
yet is deliberately **not** there: on August 2026 that is 831 rows against the 89
that need a decision, and burying the 89 is how a worksheet stops being used.
*Also list lines with unnamed receipts* on the export wizard adds them for
whoever wants them; the in-app Receipt Matching worksheet is where ticking them
one at a time belongs.

`AMOUNT PAYMENT` is blank on a sweep or a charge for the same kind of reason.
Those are not takings, and filling the cell with the bank amount had the column
footing to Rp 27,89 miliar against a Rp 15,42 miliar month — the ATS sweeps alone
are Rp 12,47 miliar of August. The client's own sheet zeroes them.

`levis_ebr_label` is the one thing the export cannot derive: the warehouse code
is a number (34885) and the store name is the full mall name, while Finance
writes `BIP`. `scripts/tenants/levis/125_seed_ebr_store_labels.py` seeds it from
the client's own workbook — their store code and their remark sit on the same
statement row, so the pairing is theirs — and never overwrites a label a person
set. Without it REMARKS falls back to the store code.

`levis.pos.x70d.txn` gained `sap_store_code`, `store_name`, `auth` and `voucher`
for this. They were always in `raw_data_json`; the view simply did not expose
them.

### `UNMAPPED` is the sheet that comes back

It carries every line `_compute_one` could not place — `unmapped`, `unparsed`,
`short`, `mismatch`, `skipped` — plus anything whose receipts name a tender the
allocation did not credit (`x24_tender_mismatch`), and five input columns: **STORE CODE**, **SIMPAN RULE
(Y/N)**, **TENDER**, **NO TRANSAKSI X24DN**, **CATATAN**. The first and third are
dropdowns over the hidden `REF` sheet (which is also the generated version of the
client's `Sheet2`), because a store code typed from memory is the most common way
a round trip comes back unusable.

The `_META` sheet names the run and carries a **token** — a digest over every
`(statement line, date, amount)` in the run. It is not a checksum of the file,
which is meant to be edited; it is a checksum of what the file claims about the
ledger, so an upload can tell "someone filled in the blanks" from "the run has
been recomputed since". A token mismatch is a warning, not a refusal: every row
is validated against the ledger as it stands anyway.

### Why the answers cannot live on the run

`action_compute` unlinks `line_ids` and `_generate_receipts` drops every
candidate receipt that is not ticked. A decision written onto a clearing line
therefore does not survive the next Compute — which is exactly how 44 hand-made
ticks were lost on 9 September 2026 and had to be recovered from a dump and
re-keyed on `statement_line_id`.

So the decisions live on **`levis.clearing.manual.map`**, one row per
`account.bank.statement.line`, unique per company, outliving the run entirely.
Compute reads them back through four small hooks and nothing else changes:

* `_compute_one` loads them once (`_for_lines`) and hangs them on each `prep`;
* `_target_analytic(prep)` is the store — the manual answer first, then the rule.
  A manual mapping outranks a MID rule because the rule generalises over a
  merchant id while the manual answer is about this one bank line;
* `_attach_evidence` turns a chosen tender into evidence of the same shape the
  receipts produce, so `_allocate_with_evidence` drains it first with no new
  allocation code at all — and `_pool_accounts_for_channel` still binds over it;
* `_apply_manual_receipts` re-ticks the named receipts after every rebuild,
  releasing an *automatic* claim elsewhere but never a human one.

`levis.pos.clearing.line.manual_map_id` is the only new column on the line, and
it is a back-reference for the operator, not an input.

### A refusal is a sentence

`_pool_accounts_for_channel` would silently ignore a cash deposit pointed at a
card receivable, and the person who typed it would never learn their answer did
nothing. So the same rule is checked at upload time and refused by name, and
again as a `@api.constrains` on the model so the UI path cannot bypass it. The
other refusals: a bank line not in this run, a row whose amount or date has moved
since the export, an unknown store code, a warehouse with no Operating Unit, a
tender outside `pos_receivable_account_ids`, a receipt that is not among that
store's transactions, a receipt a person has already ticked elsewhere, and a
receipt claimed twice inside the same file. Whole-file refusals: another run,
another company, or a run already `generated`/`posted`.

Every upload writes a `levis.clearing.upload.log` — the file itself, its SHA-256,
the counts and the rejections with their reasons — even when nothing is applied,
because a failed import that rolls back leaves nothing to look at otherwise. A
byte-identical re-upload is refused unless *Upload again anyway* is ticked.

### What it deliberately does not do

Apply ends at `action_compute`. It never generates and never posts: the three
hard-separated stages are the feature, not an obstacle. `SIMPAN RULE = Y` creates
a `levis.bank.mid.map` inside its own savepoint, so a colliding rule refuses
itself without taking the rest of the upload down.

The export changes nothing at all — no Compute, no projection rebuild, no receipt
touched — and `test_export_carries_the_sheets_and_writes_nothing` is its test.

### Three things the first users asked for

* **The sales side is the trading days, not the bank days.** Money in on 1
  September pays the day the store traded — 31 August. `_trading_window` shifts
  `COMPILE SALES` back by `settlement_lag_days`, the same anchor
  `_resolve_target` uses, so the two sides cannot drift apart; the sheet prints
  the window it covers. Filtering on the run's own dates was wrong at both ends:
  it dropped the takings the period settles and added a day the next period pays.
* **A tender is offered by name.** The ten receivables differ only in their last
  digits, so the dropdown and the `REF` sheet now read
  `1106000102 — POS Receivable - OFFLINE_VISA`. The upload accepts the label, the
  label with a plain hyphen, or the bare code — `_resolve_tender` takes the code
  off the front of whatever was written.
* **The AR sheet names the transactions.** An open POS receivable is one X70D
  transfer line per store, per day, per tender, so it carries no receipt number
  at all; `_ar_receipts` reads them from the staged X70D rows and keeps only the
  ones matching that row's own tender. A collected row shows the receipts its
  settling bank line names. Measured on the live September run: 5.072 of 5.083 AR
  rows carry transaction numbers, capped at ten per cell with the rest counted.

### What it costs, and where

Measured on the live `prd_levis_begbal`, September run, 567 lines: `_META` 0,1 s,
`SUMMARY` 0,1 s, `MUTASI IBCA` 0,2 s, `UNMAPPED` 0,0 s, `AR` 1,4 s, `REF` 0,0 s —
and **`COMPILE SALES` 62 s**. The whole cost is one scan of `levis.pos.x70d.txn`,
a SQL view over staged JSON that no index reaches; reading it with `search_read`
instead of a recordset removed 12 s of repeated prefetch scans, and the remaining
60 s is the scan itself. It is a wizard switch for that reason.

No timeout is at risk: `limit_time_real` is 1200 s and Caddy's read/write timeout
is 720 s. Worth knowing before somebody "fixes" a 90-second export that is not
broken.

### Measured against the client's own workbook (August 2026)

Built from `POSCLR/2026/0001` on a clone of `prd_levis_begbal`: 2.348 statement
lines, **17 s**, 1,0 MB, sheets `SUMMARY` (678 store-days), `MUTASI BCA` (2.035
rows), `MUTASI BRI` (306), `MUTASI BNI` (5), `MUTASI MANDIRI` (2), `UNMAPPED`
(99), `COMPILE SALES` (9.197), `AR JULY 2026` (2.648).

The `AMOUNT PAYMENT` column against the figure Finance typed into their own
`SALES PER BANK` cell for the same month:

| | Odoo | Client's workbook | Difference |
|---|---|---|---|
| BCA | 13.969.794.486 | 13.969.830.691,67 | 36.205,67 |
| BRI | 1.446.723.819 | 1.446.724.196 | 377 |

The BCA difference is one row: `TRSF E-BANKING DB 0508/SWBCA/WS954` of 36.205,
an ATS sweep the workbook counted inside settlement takings. BRI's 377 is the
`ADJUSTMENT BANK 288` the sheet carries plus narrative rounding. Both columns sum
to `run.total_gross` exactly (15.416.518.305), which the workbook's does not —
so where the two disagree, it is the workbook that is adding something up twice.

`UNMAPPED`'s 99 rows are 68 `unmapped` + 8 `unparsed` + 10 `short` + 3 `skipped`
+ 10 tender disagreements. That is the month's real manual work, against the 920
rows the first cut of this sheet produced before the receipt gaps were moved
behind a switch.

## Feature 30 — Clearing one store-day, and pairing its two lists by hand

Feature 27 answers "which store-days tie?" and books them in one narrowed run.
What it could not do is the other half of month-end: take the store-day that
does *not* tie, work out by hand which receipts that particular credit paid, and
clear that store alone.

### The run can be narrowed to a set of stores

`scope_analytic_ids` on `levis.pos.clearing`. A line whose store is outside the
scope is `skipped` with `block = False` and a reason — the same shape `auto_only`
uses, and for the same purpose: a later wide run must find it exactly as it was.
Block C is skipped too when a scope is set, because the bank's own sweeps belong
to the company and not to the store being cleared.

`action_clear` on `levis.pos.clearing.store.day` (one record or a selection from
the list) creates that narrowed run over the picked dates and stores, computes
it, and opens it. It stops there. Prepare Entries and Post & Reconcile are
unchanged, so partial clearing behaves as it always has: what the allocation
explains is booked, and an unexplained remainder stays on suspense with the bank
line still open.

The guarantee that makes this safe is one #258 already had to establish:
`_mark_statement_lines` claims only lines that produced legs, so a narrowed run
never locks a line it did not book out of the run that will.

### `levis.clearing.match` — the bank on the left, the till on the right

Opened from a store-day. Left column: that day's bank credits with gross, what
is already matched and what is not. Right column: the store's X70D transactions
for the trading day. Tick one credit and the transactions it paid, press
*Pasangkan*, and both totals are shown with their difference as you go.

Three rules, each one the engine's own:

* **Pairing names one credit.** Ticking two would leave the assignment
  ambiguous, so `action_match` refuses it by name.
* **A transaction is paid once.** Every claimed transaction — including one held
  by another credit on the *same* store-day — is shown with the entry holding it
  and cannot be ticked. An earlier cut locked only the ones held elsewhere, which
  let a tick look available and then fail at the partial unique index on the way
  out; measured on a real store-day (Plaza Senayan, 7 September) that was 5
  visible locks where there are in fact 11.
* **The answer outlives the run.** It is written to `levis.clearing.manual.map`
  as well as to the receipts, because `action_compute` rebuilds receipts.

The screen books nothing. It records what pays what.
