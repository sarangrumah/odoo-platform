---
status: draft
generated_at: 2026-09-08T00:00:00Z
generator: hand-authored
module: custom_arka_aim_purchase_type
manifest_version: 19.0.1.2.0
---

# custom_arka_aim_purchase_type

## Purpose
Splits ARKA-AIM purchasing into a **Trade** stream (goods bought to be sold on)
and a **Non-Trade** stream (operational and capex spend), and hangs fixed-asset
capitalisation off the Non-Trade goods receipt. Ports the Levi's
`custom_levis_localization` feature #9 to the ARKA-AIM tenant, minus the parts
that are Levi's-only (per-store Operating Unit, store purchase journals, vendor
bill numbering, the duplicate-SKU gate).

## Why it exists
Two separate asks from the tenant, which turn out to be one feature:

1. The buyer must declare, on the order, whether a purchase is Trade or
   Non-Trade. The two streams have different AP control accounts in the chart
   (`2103100001` vs `2103300001`) and the client wants the distinction visible
   in the **PO number itself**, not only in a field — a Non-Trade order should
   be recognisable as such on a printed document.
2. Capex arrives through Non-Trade purchases. Registering it in the fixed-asset
   subledger meant re-keying every item by hand into
   `custom.fixed.asset`. `custom_asset_from_receipt` already converts a receipt
   into assets, but only for products flagged one by one on their master — which
   is exactly the step a buyer receiving a one-off waste bin will not have done.
   The **purchase stream** is the signal that was missing.

## Business Flow
1. Buyer creates a purchase order and picks **Purchase Type** (radio, default
   Trade). The field is read-only once the order leaves draft/sent, because the
   number was already drawn from that stream's counter.
2. `create()` draws the number from the stream's per-company sequence:
   `PO/T/ARKA/2026/09/001`, `PO/NT/AIM/2026/09/001`. Two independent counters per
   company, both resetting monthly.
3. `_prepare_invoice()` copies the stream onto the vendor bill
   (`account.move.l10n_purchase_type`, editable on a bill keyed in without a PO).
4. `account.move.line._compute_account_id` routes the bill's payment-term line to
   that stream's AP control account, and — where a goods-receipt accrual really
   was booked — its product lines to the stream's GR/IR clearing account.
5. The goods receipt stores the stream (`stock.picking.l10n_purchase_type`) and,
   for a real-time valued category, posts the accrual straight away:
   `Dr Stock Valuation / Cr GR/IR clearing`. The bill in step 4 then debits the
   same GR/IR account, so the pair nets to zero and the value received sits on
   the balance sheet from the receipt date instead of from the invoice date.
6. On a validated **Non-Trade** receipt, *Convert to Assets* is offered. Every
   received line is listed, pre-selected, as a pooled asset; confirming creates
   one draft `custom.fixed.asset` per line carrying the received quantity and the
   line value.

## Key Models & Fields
| Model | Field / method | Note |
|---|---|---|
| `purchase.order` | `l10n_purchase_type` | Trade / Non-Trade, required, default Trade, tracked |
| `purchase.order` | `_arka_next_po_number()` | Draws from the stream sequence; `False` falls back to core |
| `account.move` | `l10n_purchase_type` | Copied from the PO; hand-settable on a manual bill |
| `account.move.line` | `_compute_account_id()`, `_arka_grir_account()` | AP / GR-IR / expense-fallback routing |
| `stock.move` | `_action_done()`, `_arka_post_gr_journal()`, `_arka_post_return_journal()` | Books / releases the GR-IR accrual, idempotent on `ref` |
| `stock.move` | `_arka_grir_amount()` | Receipt = `move.value`; a return = its share of the receipt it reverses |
| `arka.purchase.account.map` | `_grir_account()` | The one resolver both the receipt and the bill go through |
| `stock.picking` | `l10n_purchase_type` (stored), `_arka_is_nontrade_receipt()` | Stream on the receipt |
| `stock.picking` | `_compute_has_rental_asset_lines()` | Also True on a validated Non-Trade receipt |
| `arka.purchase.account.map` | `company_id`, `purchase_type`, `payable_account_id`, `grir_account_id`, `expense_account_id` | The wiring, one row per company and stream |
| `res.company` | `x_nontrade_asset_group_id` | Fallback asset group for Non-Trade conversions |
| `custom.asset.conversion.wizard` | `_asset_conversion_mode_for()`, `_default_asset_group()` | Overrides of the hooks added to `custom_asset_from_receipt` 19.0.0.4.0 |

## Configuration
Seeded idempotently by `post_init_hook` (`hooks.py`), re-run on every upgrade:

* per-company sequences, gated on `res.company.x_doc_code` — a company without a
  code keeps core PO numbering, so the module is inert off-tenant;
* `arka.purchase.account.map` rows resolved **by account code**, because
  `account.account.code` is company-dependent in Odoo 19 and the ids differ per
  database:

  Each entry is an ordered list of candidate codes; the first one present in the
  company's chart wins, because the two ARKA-AIM databases run different charts:

  | Stream | Payable | GR/IR clearing | Expense fallback |
  |---|---|---|---|
  | Trade | `2103100001` / `21100010` | `2103109199` / `29000000` | *(none)* |
  | Non-Trade | `2103300001` / `21100010` | `2103300008` / `29000000` | `7799000000` |

  `prd_arkaaim` runs the Erajaya chart (first code of each pair) and splits the
  streams properly. `trn_arkaaim` runs the plain Indonesian chart, which has ONE
  payable and ONE `29000000 Interim Stock`; there the two streams necessarily
  share them. That is correct for that chart, not a degraded fallback — the
  clearing still nets to zero, it simply is not split by stream.

  `post_init_hook` runs on **install only**, so already-installed tenants are
  seeded by `migrations/19.0.1.1.0/` (the Trade GR/IR account) and
  `migrations/19.0.1.2.0/` (the second chart's codes).

Booking the GR journal additionally needs, per company: the product category
real-time valued with a stock valuation account and a stock journal, plus the
`custom_arka_aim_purchase_type.suppress_gr_journal` parameter left at `"0"`.
`scripts/tenants/arkaaim/enable_gr_journal.py` is that configuration (preview by
default) and documents which categories are switched on and why.

Only empty fields are filled, so a hand-corrected mapping survives an upgrade.
Account **types** are normalised on every run: an AP control account is coerced
to `liability_payable` + reconcilable, a GR/IR account to `liability_current` +
reconcilable.

`res.company.x_nontrade_asset_group_id` is **not** seeded — pick the group on the
company form (Non-Trade Assets tab) once the tenant decides which one it is.

## Gotchas
* **The GR journal is posted by this module, not by core valuation.** Odoo 19
  takes the receipt's counterpart account from
  `stock.location.valuation_account_id`, but the Vendors location is SHARED
  across companies (`company_id` empty) and holds a single account, while
  ARKA-AIM runs two companies with separate charts and needs a different GR/IR
  per purchase stream on top of that. One shared field cannot express that, so
  `stock.move._arka_book_grir_entry` builds the entry. `_should_create_account_move`
  returns False for vendor moves we book ourselves, so configuring a location
  account later cannot produce a second entry.
* **A vendor return is NOT worth `move.value`.** An outgoing move is valued by
  the cost method — under standard costing that is the product's standard price,
  which on this tenant is unset. Releasing the accrual at that value would strand
  the difference in the clearing account forever, so `_arka_grir_amount()` values
  a return as its share of the receipt it reverses (`origin_returned_move_id`).
  A return picking also carries no purchase order, so its stream is read from the
  receipt it reverses.
* **Both sides of the accrual resolve the account through the same helper**
  (`arka.purchase.account.map._grir_account`). They cannot be allowed to drift:
  if the receipt credits one account and the bill debits another, neither ever
  clears. For the same reason, an unmapped stream books NOTHING rather than
  falling back to a guessed account.
* **The bill side gates on "was it actually received", not on product type.**
  ARKA-AIM receives service-typed products through `custom_service_receipt` and
  those receipts do raise an accrual, so `_arka_grir_account()` looks for a done
  move in from a supplier location on the purchase line. A bill raised before the
  goods arrive has no accrual to relieve and keeps its own account.
* **A periodic category is untouched.** `real_time` is the switch: it gates the
  receipt posting and the bill routing alike, so a category can be brought in one
  at a time. **Fixed Assets (Non-Valuated)** is deliberately left periodic —
  its drones are capitalised through the asset register, and accruing them as
  inventory as well would book their value twice.
* **The tenant chart holds one account record per company under the same code.**
  `2103300001` exists twice — one row owned by AIM, one by ARKA — and the hook runs
  as superuser, where the multi-company record rule does not apply. `_find_account`
  therefore filters on `company_ids` as well as on the company-dependent `code`;
  without it the seeding would wire AIM's payable onto ARKA's bills.
* **The expense fallback only fills an empty account.** A product or category
  account always wins; the fallback exists so an opex product with no account
  configured cannot block bill posting outright.
* **Non-Trade conversion is pooled, never per-serial.** A serial-mode wizard line
  is silently dropped when the move line carries no lot — which would quietly
  skip exactly the unflagged lines this module exists to offer. Products that ARE
  flagged on their master keep their own mode, so a configured per-serial
  conversion still wins.
* **Assets are created in draft with no acquisition journal**, exactly like the
  existing `custom_arka_aim_asset_register`. The register is a subledger; the GL
  was already moved by the receipt and the vendor bill, and posting an
  acquisition entry here would double-count. Confirm the asset to build its
  depreciation schedule.
* **`_compute_has_rental_asset_lines` re-declares `@api.depends`.** Re-declaring
  replaces the inherited set, so every base trigger is relisted alongside
  `l10n_purchase_type`.
* **`_compute_account_id` carries no `@api.depends` in core** — it is a
  precompute-at-create field. The override keeps those semantics and just remaps
  after `super()`; the bill already has its stream at create time because
  `_prepare_invoice` set it.
* **`purchase.order` has two search views in play.** The Purchase Orders action
  uses `purchase.purchase_order_view_search`, the RFQ action uses
  `purchase.view_purchase_order_filter`. The stream filters are added to BOTH —
  inheriting only one leaves the split invisible on exactly the list the buyer
  works from. Same trap on the list side: the action pins
  `purchase.purchase_order_view_tree`, which is not the model's default list view.
* Changing the Purchase Type after confirmation is blocked in the view, not by a
  constraint: the number is already drawn and a `PO/T/...` order sitting in the
  Non-Trade stream is worse than an unchangeable field.

## Dependencies
`purchase`, `stock`, `account`, `custom_arka_aim_numbering` (supplies
`res.company.x_doc_code` and the `x_monthly_reset` `ir.sequence` override),
`custom_asset_from_receipt` **19.0.0.4.0 or later** (supplies the two extension
hooks this module overrides).

## Tests
`tests/test_gr_journal.py` — the receipt posts Dr valuation / Cr GR-IR for the
purchase value, posting is idempotent, a periodic category / the switch off / an
unmapped stream / an internal transfer all book nothing, the bill relieves the
same account and flattens the clearing balance, a bill without a receipt keeps
its own account, and a vendor return releases the accrued amount rather than the
standard cost.

`tests/test_purchase_type.py` — separate numbering streams with independent
monthly counters, bill stream inheritance and payable routing, GR/IR staying
inert for a periodic category, a Non-Trade receipt offering an unflagged product,
conversion falling back to the company asset group, and a Trade receipt staying
untouched.
