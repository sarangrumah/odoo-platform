# -*- coding: utf-8 -*-
"""FIFO matching as a plain function, deliberately not a model method.

``custom_accounting_reports`` has the same logic as
``custom.report.gl.open.items._fifo``, but it is a method on an AbstractModel
and cannot be imported. Making either module depend on the other is worse than
the duplication: ``custom_account_reconcile`` depends on ``account`` alone,
while ``custom_accounting_reports`` drags in custom_core, custom_web_layout_memory,
custom_pdp_audit and custom_accounting_full — and a dependency either way would
force one of them onto a database that does not want it.

So: one small pure function, no ORM, no ``self``. Kept honest by
``tests/test_batch_reconcile.py``.
"""


def match_fifo(debits, credits, tolerance=0.005):
    """Pair debits against credits oldest-first.

    ``debits`` and ``credits`` are lists of ``(key, amount)`` with **positive**
    amounts, already in the order they should be consumed. Returns
    ``[(debit_key, credit_key, amount), ...]``.

    Neither side is mutated. A pairing smaller than ``tolerance`` is dropped
    rather than emitted: matching a fraction of a rupiah costs a partial
    reconcile row and buys nothing.
    """
    remaining_debits = [[key, float(amount)] for key, amount in debits if amount > 0]
    remaining_credits = [[key, float(amount)] for key, amount in credits if amount > 0]
    pairs = []
    di = ci = 0
    while di < len(remaining_debits) and ci < len(remaining_credits):
        debit, credit = remaining_debits[di], remaining_credits[ci]
        amount = min(debit[1], credit[1])
        if amount > tolerance:
            pairs.append((debit[0], credit[0], amount))
        debit[1] -= amount
        credit[1] -= amount
        if debit[1] <= tolerance:
            di += 1
        if credit[1] <= tolerance:
            ci += 1
    return pairs


def group_residual(amounts):
    """Net residual of a group, for deciding whether it closes."""
    return sum(amounts)
