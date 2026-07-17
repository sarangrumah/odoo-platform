# Custom PPOB Suite — Knowledge

Ported from the ERA PPOB R&D project (`E:\Projects\Odoo\rnd-ppob`, Odoo 18) into
the Odoo 19 platform as the `ppob` industry vertical. This file documents the
whole suite; each module's `__manifest__.py` description covers its own scope.

## Purpose

PPOB (Payment Point Online Bank) = bill-payment / top-up reseller. Mitra (B2B
resellers) hold prepaid **wallets**; we hold prepaid **deposit inventory** with
each **provider**. A **transaction** debits the mitra wallet and the provider
bucket atomically, then calls the provider adapter. Tax (PMK-63 margin VAT),
commissions (with PPh 23), a daily e-Faktur rollup, and bank virtual-account
top-ups sit on top.

## Modules (dependency order)

1. `custom_ppob_core` — product classes (vat_mode), products, price tiers,
   res.partner mitra/provider fields, sequences, security groups, **COA
   scaffolding** + role→account mapping.
2. `custom_ppob_wallet` — `custom.ppob.wallet` + atomic `_atomic_debit` /
   `_atomic_credit` / `_atomic_credit_with_tax` primitives (row-locked, paired
   GL + sub-ledger).
3. `custom_ppob_provider` — provider master, atomic bucket inventory, SKU map,
   adapter registry (`ppob_mock`, `ppob_http_json`), DP-100% topup wizard.
4. `custom_ppob_sale` — transaction state machine + dispatch + reaper; **merged
   tax** (vat_mode/dpp/ppn).
5. `custom_ppob_commission` — commission rules/accruals + settlement (PPh 23 via
   `custom_pph_witholding`).
6. `custom_ppob_rollup` — daily aggregation → summary faktur for e-Faktur.
7. `custom_ppob_va` — mitra virtual accounts, H2H callbacks, `va_match` reconcile.
8. `custom_ppob_oracle_bridge` — legacy Oracle EVShop bridge (opt-in, not in the
   default pack).

## Key design decisions (vs ERA source)

- **Account scaffolding (D5):** accounts are created idempotently in
  `custom_ppob_core` `post_init_hook` (search-by-code-then-create with
  `company_ids`), NOT XML data — avoids Odoo-19 `company_ids` M2M + non-idempotent
  `-u` hazards. Downstream code resolves accounts by role via
  `custom.ppob.account.mapping._get_account(role, company)`, never by xmlid.
- **Posting model (D7):** a sale's GL is posted by the wallet + bucket atomic
  helpers (each posts its own paired entry). There is **no** separate compound
  sale move — the ERA `_post_sale_move`/`_prepare_account_move_vals` were dead
  code and are gone. Per-transaction revenue is booked **gross**; PPN is
  recognised at the daily rollup faktur, not per transaction.
- **Adapters (D1):** the PPOB adapter registry is separate from
  `custom_adapter_framework` (provider-instantiated, domain verbs
  inquiry/pay/status/topup). `ppob_http_json` does a single signed POST per call
  (no retry loop) so a non-idempotent `pay()` cannot double-sell; it reuses
  `custom.adapter.config` for per-tenant base_url/credential and writes
  `custom.adapter.call.log`.
- **DP topup (D2):** the wizard is self-contained (DP + Pelunasan `in_invoice`
  pair + `account.move._post` hook advancing the bucket). No third-party
  advance-payment module.
- **Rollup × reports (D6):** the summary faktur posts to a journal flagged
  `account.journal.x_custom_report_excluded` (a generic flag added to
  `custom_accounting_reports`), so its GL is omitted from TB/P&L/BS — revenue is
  already booked per transaction.
- **VA replay (D3):** the H2H controller reuses `custom_core`'s Redis-backed
  `_NonceStore` + IP allowlist. The **hard** idempotency guarantee is the DB
  `UNIQUE(bank_ref)` on `custom.ppob.va.topup`; the nonce is a throttle only.

## Gotchas

- Raw-SQL balance updates in wallet/bucket reference physical table names
  (`custom_ppob_wallet`, `custom_ppob_provider_bucket`) — keep in sync with model
  renames. The bucket's partial unique indexes are created in `init()`.
- Wallet/bucket sub-ledgers guard optional back-ref columns
  (`ppob_transaction_id`, `va_topup_id`) against `_fields` so they install before
  the modules that add those columns.
- Financial reports now exclude any journal with `x_custom_report_excluded=True`
  (backward-compatible; defaults False).
- `custom_ppob_oracle_bridge` runs two 1-minute crons — keep it out of tenants
  that don't use the legacy EVShop pipeline (it is excluded from the seed pack).

## Verification

Dev stack ports 18069/18072. From Git Bash:
`MSYS_NO_PATHCONV=1 ... odoo --test-tags /custom_ppob_provider,/custom_ppob_sale,/custom_ppob_va,/custom_ppob_oracle_bridge -d <db> --stop-after-init`.
Restart the Odoo container after Python changes. See the ERA source at
`E:\Projects\Odoo\rnd-ppob\addons\era_ppob_*` for the pre-port reference.
