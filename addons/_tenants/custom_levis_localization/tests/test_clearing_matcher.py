# -*- coding: utf-8 -*-
"""The composition search, on its own.

``levis.clearing.matcher._subset_match`` is pure arithmetic, so it is tested
without a run, a statement or a chart of accounts. Every test here is about one
of the two properties the method's honesty rests on — determinism and
uniqueness — because a subset matcher that is merely *usually* right is worse
than none: it launders a guess into an allocation.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestClearingMatcher(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.matcher = cls.env["levis.clearing.matcher"]
        cls.day = date(2026, 7, 15)

    def _items(self, *amounts):
        return [("A%d" % index, amount, self.day) for index, amount in enumerate(amounts)]

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------
    def test_one_composition_is_named(self):
        # 500 + 250 is the only way to reach 750 out of this pool.
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0, 250.0, 120.0, 70.0), 750.0)
        self.assertEqual(verdict, "unique")
        self.assertEqual(sorted(chosen), ["A0", "A2"])

    def test_a_target_two_sets_can_reach_names_neither(self):
        # 500+250+120 and 500+300+70 both make 870 — a real aggregation trap.
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0, 250.0, 120.0, 70.0), 870.0)
        self.assertEqual(verdict, "ambiguous")
        self.assertEqual(chosen, [])

    def test_two_compositions_name_nothing(self):
        # 300 + 200 and 400 + 100 both make 500. Naming either is a guess.
        verdict, chosen = self.matcher._subset_match(self._items(400.0, 300.0, 200.0, 100.0), 500.0)
        self.assertEqual(verdict, "ambiguous")
        self.assertEqual(chosen, [])

    def test_nothing_adds_up(self):
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0), 999.0)
        self.assertEqual(verdict, "none")
        self.assertEqual(chosen, [])

    def test_a_single_item_answers_it(self):
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0, 120.0), 300.0)
        self.assertEqual(verdict, "unique")
        self.assertEqual(chosen, ["A1"])

    def test_two_items_of_the_same_amount_are_ambiguous(self):
        verdict, chosen = self.matcher._subset_match(self._items(300.0, 300.0, 120.0), 300.0)
        self.assertEqual(verdict, "ambiguous")
        self.assertEqual(chosen, [])

    def test_the_whole_pool_may_be_the_answer(self):
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0, 120.0), 920.0)
        self.assertEqual(verdict, "unique")
        self.assertEqual(sorted(chosen), ["A0", "A1", "A2"])

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------
    def test_a_shuffled_pool_gives_the_same_answer(self):
        amounts = [500.0, 300.0, 250.0, 120.0, 70.0, 33.0, 17.0]
        target = 870.0
        first = self.matcher._subset_match(self._items(*amounts), target)
        for rotation in range(1, len(amounts)):
            shuffled = amounts[rotation:] + amounts[:rotation]
            items = [("A%d" % amounts.index(a), a, self.day) for a in shuffled]
            verdict, chosen = self.matcher._subset_match(items, target)
            self.assertEqual(verdict, first[0])
            self.assertEqual(sorted(chosen), sorted(first[1]))

    # ------------------------------------------------------------------
    # Bounds
    # ------------------------------------------------------------------
    def test_a_pool_larger_than_the_cap_is_not_searched_blindly(self):
        # 30 items, cap of 4: the search may not wander over the whole pool.
        items = self._items(*[100.0 + index for index in range(30)])
        verdict, chosen = self.matcher._subset_match(items, 617.0, max_items=4)
        self.assertIn(verdict, ("unique", "ambiguous", "none"))
        if verdict == "unique":
            self.assertLessEqual(len(chosen), 4)

    def test_an_exhausted_budget_reports_no_answer_not_a_partial_one(self):
        items = self._items(*[float(1 + index) for index in range(24)])
        verdict, chosen = self.matcher._subset_match(items, 150.0, node_budget=1)
        self.assertEqual(verdict, "none")
        self.assertEqual(chosen, [])

    def test_a_zero_budget_searches_nothing(self):
        verdict, _chosen = self.matcher._subset_match(self._items(500.0), 500.0, node_budget=0)
        self.assertEqual(verdict, "none")

    # ------------------------------------------------------------------
    # Tolerance
    # ------------------------------------------------------------------
    def test_tolerance_lets_a_near_miss_compose(self):
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0), 799.0, tolerance=5.0)
        self.assertEqual(verdict, "unique")
        self.assertEqual(sorted(chosen), ["A0", "A1"])

    def test_without_tolerance_the_same_near_miss_is_refused(self):
        verdict, chosen = self.matcher._subset_match(self._items(500.0, 300.0), 799.0)
        self.assertEqual(verdict, "none")
        self.assertEqual(chosen, [])

    def test_an_item_larger_than_the_target_is_never_taken(self):
        verdict, chosen = self.matcher._subset_match(self._items(5000.0, 300.0), 300.0)
        self.assertEqual(verdict, "unique")
        self.assertEqual(chosen, ["A1"])

    # ------------------------------------------------------------------
    # Rounding
    # ------------------------------------------------------------------
    def test_cents_do_not_drift(self):
        # Three amounts that float addition does not sum cleanly.
        verdict, chosen = self.matcher._subset_match(self._items(0.10, 0.20, 0.70), 0.30)
        self.assertEqual(verdict, "unique")
        self.assertEqual(sorted(chosen), ["A0", "A1"])
