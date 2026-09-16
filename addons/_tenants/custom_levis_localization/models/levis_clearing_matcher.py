# -*- coding: utf-8 -*-
"""Shared ranking and composition logic for bank-to-receivable matching.

Two screens ask the same question — "which open receivables did this bank credit
pay?" — and until now each answered it its own way: ``levis.pos.clearing``
allocated greedily by (store, trading day), while the bank-reconcile wizard
ranked candidates with a scoring function of its own. Two rankings of one
question drift apart, and the operator sees the clearing propose one item and
the wizard rank another first. This abstract model is the single answer both
call.

It is deliberately pure: it takes amounts and dates, returns amounts and dates,
touches no state and books nothing. That is what makes it testable without a
run, and what makes it safe to call from a compute.
"""

from odoo import api, models

# Composition search works in integer minor units, so IDR 2-decimal arithmetic
# is exact and the result cannot drift with float addition order.
_MINOR = 100


class LevisClearingMatcher(models.AbstractModel):
    _name = "levis.clearing.matcher"
    _description = "POS Clearing Matching Helpers"

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------
    @api.model
    def _score_candidate(self, aml, target, primary_day, tender_accounts, currency, tolerance=0.0):
        """How well one open item answers ``target``. Higher is better.

        The weights are the ones the bank-reconcile wizard has been using; they
        are moved here unchanged so that lifting them changes no behaviour. The
        only addition is ``tolerance``, and it can only ever *raise* a score —
        it never books, sizes or absorbs anything.
        """
        residual = aml.amount_residual
        score = 0.0
        exact = not currency.compare_amounts(residual, target)
        if exact:
            score += 100.0
        elif tolerance and abs(residual - target) <= tolerance:
            # Near enough to be worth a human's attention, but ranked below
            # anything that actually matches to the cent.
            score += 80.0
        if primary_day and aml.date == primary_day:
            score += 40.0
        elif primary_day:
            score += max(0.0, 20.0 - abs((aml.date - primary_day).days) * 2.0)
        if aml.account_id in tender_accounts:
            score += 15.0  # a tender receivable before a trade one
        if target:
            score += max(0.0, 10.0 - abs(residual - target) / target * 10.0)
        return score

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------
    @api.model
    def _subset_match(self, items, target, tolerance=0.0, max_items=24, node_budget=20000):
        """Which open items compose ``target`` — but only if exactly one set does.

        ``items`` is ``[(key, amount, date)]``; the return is
        ``("unique", [key, ...])``, ``("ambiguous", [])`` or ``("none", [])``.

        **Why this is allowed here when ``_x24_identify`` refuses it.** That
        method refuses to name a subset of *receipt numbers*, and it is right to:
        naming one there is an unverifiable claim about which customers'
        transactions the acquirer paid. This is ledger allocation against
        per-store-per-day receivable totals — a subset is already being chosen
        today, greedily, and every item chosen is recorded on
        ``levis.pos.clearing.alloc`` and reconciled as an exact pair, so it stays
        auditable and reversible. Do not carry this back into ``_x24_identify``.

        The honesty of the answer rests on two properties:

        * **Determinism.** Items are put in a total order — ``(-amount, date,
          key)`` — before anything is searched, so the same pool shuffled
          produces the same subset. Nothing here depends on dict iteration or on
          the order the caller happened to pass.
        * **Uniqueness.** The search does not stop at the first hit. It stops at
          the *second*, and then reports ambiguity and allocates nothing. A
          settlement that can be composed two ways is not evidence for either.
        """
        if not items or not target or max_items <= 0 or node_budget <= 0:
            return "none", []

        goal = int(round(target * _MINOR))
        band = int(round(abs(tolerance) * _MINOR))
        if goal <= 0:
            return "none", []

        # Total order first — everything below depends on it.
        ordered = sorted(items, key=lambda it: (-round(it[1] * _MINOR), it[2], str(it[0])))
        pool = [
            (key, int(round(amount * _MINOR)))
            for key, amount, _date in ordered
            if amount > 0 and int(round(amount * _MINOR)) <= goal + band
        ]
        if not pool:
            return "none", []

        # Cheap cases first: they cover most real aggregation and cost nothing.
        for key, value in pool:
            if abs(value - goal) <= band:
                # A single item answers it. Still has to be unique.
                singles = [k for k, v in pool if abs(v - goal) <= band]
                return ("unique", [singles[0]]) if len(singles) == 1 else ("ambiguous", [])
        whole = sum(value for _k, value in pool)
        if abs(whole - goal) <= band and len(pool) <= max_items:
            return "unique", [key for key, _v in pool]

        pool = pool[:max_items]
        # Suffix sums let a branch be abandoned the moment it cannot reach the
        # goal even by taking everything that is left.
        suffix = [0] * (len(pool) + 1)
        for index in range(len(pool) - 1, -1, -1):
            suffix[index] = suffix[index + 1] + pool[index][1]

        found = []
        budget = [node_budget]

        def walk(index, remaining, chosen):
            if len(found) > 1 or budget[0] <= 0:
                return
            if abs(remaining) <= band:
                found.append(list(chosen))
                return
            if index >= len(pool) or remaining < -band:
                return
            if suffix[index] + band < remaining:
                return
            budget[0] -= 1
            key, value = pool[index]
            chosen.append(key)
            walk(index + 1, remaining - value, chosen)
            chosen.pop()
            walk(index + 1, remaining, chosen)

        walk(0, goal, [])

        if budget[0] <= 0 and len(found) != 1:
            # Ran out of search before the question was settled. "No answer" is
            # the only honest report; a partial search is not evidence.
            return "none", []
        if len(found) == 1:
            return "unique", found[0]
        if len(found) > 1:
            return "ambiguous", []
        return "none", []
