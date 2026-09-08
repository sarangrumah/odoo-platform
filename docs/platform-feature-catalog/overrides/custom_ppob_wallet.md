---
status: override
module: custom_ppob_wallet
source: manifest + models/*.py
---

# custom_ppob_wallet

## Purpose
The **money primitives** the rest of the PPOB suite is built on. One wallet per
(mitra, product class), with debit and credit operations that are atomic against
concurrent transactions — the correctness foundation of a prepaid business where
two simultaneous sales must not both succeed against the same last balance.

## Business Flow
- `_atomic_debit` and `_atomic_credit` take a row-level `SELECT ... FOR UPDATE`
  lock on the wallet, post a paired `account.move`, write a
  `custom.ppob.wallet.move` sub-ledger line, and update the balance — **all
  inside one PostgreSQL transaction**. There is no window in which the balance
  and the ledger disagree.
- `_atomic_credit_with_tax` handles tax-inclusive top-ups: it splits the gross
  into DPP, which grows the wallet, and PPN, which is routed to the output-tax
  repartition account. Used by the Virtual Account top-up path.
- A manual adjust and top-up wizard covers the operations desk's corrections;
  every adjustment goes through the same primitives, so a manual fix leaves the
  same audit trail as an automatic one.
- Dedicated wallet and sale general journals keep the sub-ledger separable from
  the tenant's ordinary accounting.

## Key Models
- `custom.ppob.wallet` — one per (mitra, product class); holds the balance and
  exposes the atomic primitives.
- `custom.ppob.wallet.move` — the sub-ledger line paired with every GL move.
- `custom.ppob.wallet.adjust.wizard` — manual adjustment and top-up.

## Important Fields
- `custom.ppob.wallet.balance` — never written directly; only the atomic helpers
  update it, and always in the same transaction as the ledger line.
- `custom.ppob.wallet.move.ppob_transaction_id` — the back-reference added by
  `custom_ppob_sale`, which is how a wallet movement is traced to the sale that
  caused it.
