# -*- coding: utf-8 -*-
"""Allocating a five-character journal code for a store.

``account.journal.code`` is five characters and the Levi's seeding derives it
from the store code, so a batch of consecutive stores competes for the same few
characters. The allocator used to keep a four-character stem and append the
counter, which truncates back to the same five characters from ``n=10`` on — so
once ``8074x`` was full it stopped returning at all. These tests pin the two
things that matter: it still hands out the codes it always did, and it always
comes back.
"""

import signal
from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.custom_levis_localization.models.setup import _unique_journal_code
from odoo.exceptions import UserError
from odoo.tests import tagged


class _Deadline:
    """Turn a hang into a failure — the bug this guards against never returns."""

    def __init__(self, seconds=20):
        self.seconds = seconds

    def __enter__(self):
        signal.signal(signal.SIGALRM, self._fire)
        signal.alarm(self.seconds)

    def __exit__(self, *exc):
        signal.alarm(0)
        return False

    @staticmethod
    def _fire(signum, frame):
        raise AssertionError("_unique_journal_code did not return — it is looping")


@tagged("post_install", "-at_install")
class TestJournalCodeAllocation(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]

    def _occupy(self, *codes):
        self.env["account.journal"].create(
            [
                {"name": "Occupied %s" % code, "type": "general", "code": code, "company_id": self.company.id}
                for code in codes
            ]
        )

    def _alloc(self, base):
        with _Deadline():
            return _unique_journal_code(self.env, self.company, base)

    # ------------------------------------------------------------------
    # What it always did
    # ------------------------------------------------------------------
    def test_free_base_is_taken_as_is(self):
        self.assertEqual(self._alloc("80741"), "80741")

    def test_base_is_truncated_to_five(self):
        self.assertEqual(self._alloc("8074123"), "80741")

    def test_first_collision_keeps_the_historic_shape(self):
        # Every purchase journal in the live tenants is named this way
        # (cash 14696 / purchase 14691); the fix must not renumber them.
        self._occupy("14696")
        self.assertEqual(self._alloc("14696"), "14691")

    def test_counter_walks_one_at_a_time(self):
        self._occupy("14696", "14691", "14692")
        self.assertEqual(self._alloc("14696"), "14693")

    # ------------------------------------------------------------------
    # The regression: nine consecutive stores in one provisioning run
    # ------------------------------------------------------------------
    def test_a_full_stem_still_returns(self):
        # 80741..80748 as cash journals plus 80749 — exactly the state
        # 108_add_stores.py reaches after creating the batch's cash journals.
        self._occupy("80740", "80741", "80742", "80743", "80744", "80745", "80746", "80747", "80748", "80749")
        code = self._alloc("80742")
        self.assertEqual(len(code), 5)
        self.assertFalse(
            self.env["account.journal"].search_count([("code", "=", code), ("company_id", "=", self.company.id)]),
            "allocator returned a code that is already taken: %r" % code,
        )

    def test_every_store_in_a_batch_gets_a_distinct_code(self):
        stores = ["80680"] + ["8074%d" % d for d in range(1, 9)]
        self._occupy(*stores)  # the cash journals
        issued = []
        for base in stores:
            code = self._alloc(base)
            issued.append(code)
            self._occupy(code)  # the purchase journal we just "created"
        self.assertEqual(len(set(issued)), len(stores), "codes collided: %r" % issued)
        self.assertTrue(all(len(c) <= 5 for c in issued), issued)

    def test_exhaustion_raises_instead_of_looping(self):
        # Every candidate taken. The old code would spin here too, silently;
        # the point of the fix is that running out is reported, not endured.
        Journal = self.env.registry["account.journal"]
        with patch.object(Journal, "search_count", return_value=1):
            with self.assertRaises(UserError):
                with _Deadline():
                    _unique_journal_code(self.env, self.company, "80741")
