# custom_payment_methods_id — module knowledge

## What it is
Four `account.payment.method` records — Giro and Bank Transfer, inbound and
outbound — plus the `_get_payment_method_information()` entry that makes them
legal. Nothing else. Manual-style: no file generation, no provider.

## Gotchas

**The records are created by a hook, not a data file.** `account.payment.method`
carries a unique constraint on `(code, payment_type)`, and Levi's databases
already own these four rows through `custom_levis_localization`. A `<record>`
here would blow up on install there. `hooks.post_init_hook` skips whatever
already exists, so both modules can coexist on one database. The flip side:
the rows have no XMLID of their own, so an uninstall of this module leaves them
behind — deliberate, since removing a payment method that posted payments
reference would break those payments.

**`_get_payment_method_information()` must know the code before the record can
be created.** Core reads that dict inside `account.payment.method.create` to
resolve `mode` and the allowed journal types. Creating a method whose code is
absent from the dict fails. That is why the model override and the hook ship
together — installing only the data would not work.

**`type: ('bank',)` means bank journals only.** Do not try to add giro or bank
transfer to a cash journal; core filters them out of
`available_payment_method_line_ids` and the line silently disappears.

**Installing gives you the methods, not the journal lines.** Attach them per
journal, or run `scripts/tenants/arkaaim/setup_payment_journals.py`, which adds
the lines and points each at the journal's own bank account (direct-to-bank).

## Related
- `addons/_tenants/custom_levis_localization/models/account_payment_method.py` —
  the Levi's original this was extracted from.
- `scripts/tenants/arkaaim/setup_payment_journals.py` — wires the methods onto
  the ARKA journals.
