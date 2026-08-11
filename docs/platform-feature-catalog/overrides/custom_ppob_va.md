---
status: override
module: custom_ppob_va
source: manifest + models/*.py + controllers/
---

# custom_ppob_va

## Purpose
The **top-up pipeline for mitra wallets via bank Virtual Account** — BCA, BNI,
BRI, Mandiri and Permata. Two independent paths reach the same wallet credit:
a real-time host-to-host callback, and a reconciliation rule over imported bank
statements for the cases where the callback never arrived.

## Business Flow
- **Host-to-Host.** `/api/ppob/va/<bank>/inquiry` and `/api/ppob/va/<bank>/payment`
  are authenticated per bank with HMAC-SHA256 over timestamp plus body, using the
  platform secure-endpoint primitives: Redis-backed nonce replay guard, IP
  allow-list, clock-skew check.
- The hard idempotency guarantee is **not** the nonce guard but a database
  constraint: `UNIQUE(bank_ref)` on `custom.ppob.va.topup`. A duplicate callback
  credits the wallet exactly once and returns the original acknowledgement. This
  matters because banks retry, and a replay window is a time-bounded defence
  while a unique index is not.
- **Manual / reconcile.** A `va_match` extension of `custom.reconcile.rule`
  matches bank-statement references against `custom.ppob.va.account` records and
  credits the correct wallet, reusing `custom_bank_import` and
  `custom_accounting_full` rather than building a second matching engine.
- An optional per-VA output tax splits each top-up into DPP (the wallet credit)
  and PPN (Output VAT), through the wallet's tax-inclusive credit primitive.

## Key Models
- `custom.ppob.va.account` — the virtual account assigned to a mitra.
- `custom.ppob.va.topup` — one top-up; carries the unique `bank_ref`.
- `custom.ppob.va.bank.connection` — per-bank credentials and endpoint config.
- `custom.reconcile.rule` (inherited) — the `va_match` matcher.
- `account.bank.statement.line`, `custom.ppob.wallet.move` (inherited).

## Important Fields
- `custom.ppob.va.topup.bank_ref` — **unique**. The single guarantee that a
  retried callback cannot double-credit a wallet.
- `custom.ppob.va.account.partner_id` — the mitra the VA belongs to; the join the
  reconcile rule resolves.

## Endpoints
- `POST /api/ppob/va/<bank_code>/inquiry` — the bank asks whether the VA is valid
  and what is owed.
- `POST /api/ppob/va/<bank_code>/payment` — the bank reports a settled payment.
