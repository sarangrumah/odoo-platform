# -*- coding: utf-8 -*-
"""Two rules must never compete for one terminal.

The SQL constraint on this model has never fired: ``journal_id`` is NULL on every
rule anyone creates, Postgres treats NULLs as distinct, and it compares raw
strings anyway. So the guard is Python, and it borrows the resolver's own
``_keys_match`` rather than re-stating the rule — a unique index cannot express
"a suffix from six digits up is the same terminal".

Half these tests assert that something is *allowed*. That is the harder half: a
guard that also forbids handing a MID to another store, or restricting a rule to
one bank feed, would have broken two features this model was built for.
"""

from datetime import date

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged

LONG = "885004608375"
SHORT = "4608375"
PADDED = "001999632289"
BARE = "1999632289"


@tagged("post_install", "-at_install")
class TestMidMapGuard(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        plan = cls.env["account.analytic.plan"].create({"name": "Guard OU"})
        cls.store_one = cls.env["account.analytic.account"].create({"name": "GUARD STORE ONE", "plan_id": plan.id})
        cls.store_two = cls.env["account.analytic.account"].create({"name": "GUARD STORE TWO", "plan_id": plan.id})
        cls.bca = cls.env["account.journal"].create(
            {"name": "Guard BCA", "code": "GBCA", "type": "bank", "levis_clearing_format": "bca"}
        )
        cls.bri = cls.env["account.journal"].create(
            {"name": "Guard BRI", "code": "GBRI", "type": "bank", "levis_clearing_format": "bri"}
        )

    def _rule(self, key, store=None, **overrides):
        vals = {
            "name": "rule %s" % key,
            "company_id": self.company.id,
            "match_type": "mid",
            "key": key,
            "analytic_account_id": (store or self.store_one).id,
        }
        vals.update(overrides)
        return self.env["levis.bank.mid.map"].create(vals)

    # ------------------------------------------------------------------
    # Refused: the three shapes of collision
    # ------------------------------------------------------------------
    def test_identical_key_is_refused(self):
        self._rule(LONG)
        with self.assertRaises(ValidationError):
            self._rule(LONG, store=self.store_two)

    def test_leading_zero_variant_is_refused(self):
        """The collision that actually happened: 1999632289 vs 001999632289."""
        self._rule(BARE, match_type="tid")
        with self.assertRaises(ValidationError):
            self._rule(PADDED, store=self.store_two, match_type="tid")

    def test_suffix_variant_is_refused(self):
        """4608375 and 885004608375 are one merchant to the resolver."""
        self._rule(LONG)
        with self.assertRaises(ValidationError):
            self._rule(SHORT, store=self.store_two)

    def test_collision_is_refused_even_when_both_name_the_same_store(self):
        """Harmless today, a trap tomorrow: an edit would change one, not both."""
        self._rule(LONG)
        with self.assertRaises(ValidationError):
            self._rule(SHORT)

    def test_message_names_both_stores_and_the_shape(self):
        self._rule(LONG)
        with self.assertRaises(ValidationError) as caught:
            self._rule(SHORT, store=self.store_two)
        message = str(caught.exception)
        self.assertIn("GUARD STORE ONE", message)
        self.assertIn("GUARD STORE TWO", message)
        self.assertIn("end the same", message, "the reader must know which kind of collision this is")

    # ------------------------------------------------------------------
    # Allowed: the features a careless guard would have broken
    # ------------------------------------------------------------------
    def test_a_terminal_may_be_handed_to_another_store_over_time(self):
        """``date_end`` exists for exactly this. Refusing it breaks the feature."""
        self._rule(LONG, date_end=date(2026, 6, 30))
        later = self._rule(LONG, store=self.store_two, date_start=date(2026, 7, 1))
        self.assertTrue(later.id)

    def test_overlapping_dates_on_the_same_terminal_are_still_refused(self):
        self._rule(LONG, date_end=date(2026, 7, 15))
        with self.assertRaises(ValidationError):
            self._rule(LONG, store=self.store_two, date_start=date(2026, 7, 1))

    def test_rules_restricted_to_different_feeds_do_not_compete(self):
        self._rule(LONG, journal_id=self.bca.id)
        other_feed = self._rule(LONG, store=self.store_two, journal_id=self.bri.id)
        self.assertTrue(other_feed.id)

    def test_a_global_rule_competes_with_a_feed_scoped_one(self):
        """``_resolve`` considers journal_id in (False, this feed), so they meet."""
        self._rule(LONG, journal_id=self.bca.id)
        with self.assertRaises(ValidationError):
            self._rule(LONG, store=self.store_two)

    def test_short_keys_below_the_suffix_floor_do_not_collide(self):
        self._rule("12345")
        self.assertTrue(self._rule("9912345", store=self.store_two).id)

    def test_keyword_substrings_are_the_design_not_a_collision(self):
        self._rule("ols", match_type="keyword")
        longer = self._rule("setoran ols pvj", store=self.store_two, match_type="keyword")
        self.assertTrue(longer.id)

    def test_identical_keyword_is_refused_case_insensitively(self):
        self._rule("cash sales pvj", match_type="keyword")
        with self.assertRaises(ValidationError):
            self._rule("Cash Sales PVJ", store=self.store_two, match_type="keyword")

    def test_archived_rule_does_not_block(self):
        self._rule(LONG, active=False)
        self.assertTrue(self._rule(LONG, store=self.store_two).id)

    def test_a_different_match_type_is_a_different_namespace(self):
        """A MID and a TID that read alike are not the same thing."""
        self._rule(BARE, match_type="mid")
        self.assertTrue(self._rule(BARE, store=self.store_two, match_type="tid").id)

    # ------------------------------------------------------------------
    # Which keyword wins when several match
    # ------------------------------------------------------------------
    def _resolve_cash(self, narrative):
        return self.env["levis.bank.mid.map"]._resolve(
            self.company, self.bca, {"keyword": narrative, "raw": narrative}, date(2026, 7, 8)
        )

    def test_the_most_specific_keyword_wins_even_when_it_sorts_last(self):
        """Deliberately 'Z': with 'SMB' the alphabet gives the right answer for
        the wrong reason, and a test that passes by luck proves nothing."""
        self._rule("SOPIAN PERMANA", match_type="keyword")
        specific = self._rule("ZMB SOPIAN PERMANA", store=self.store_two, match_type="keyword")
        self.assertEqual(self._resolve_cash("setoran zmb sopian permana"), specific)

    def test_the_generic_keyword_still_wins_when_it_is_the_only_match(self):
        generic = self._rule("SOPIAN PERMANA", match_type="keyword")
        self._rule("ZMB SOPIAN PERMANA", store=self.store_two, match_type="keyword")
        self.assertEqual(self._resolve_cash("setoran tunai sopian permana"), generic)

    def test_sequence_remains_an_explicit_override(self):
        """Length only settles a tie; a lower sequence still wins outright."""
        self._rule("ZMB SOPIAN PERMANA", match_type="keyword", sequence=20)
        forced = self._rule("SOPIAN PERMANA", store=self.store_two, match_type="keyword", sequence=5)
        self.assertEqual(self._resolve_cash("setoran zmb sopian permana"), forced)

    # ------------------------------------------------------------------
    # Escape hatch
    # ------------------------------------------------------------------
    def test_the_guard_can_be_skipped_deliberately(self):
        self._rule(LONG)
        forced = (
            self.env["levis.bank.mid.map"]
            .with_context(levis_skip_mid_map_guard=True)
            .create(
                {
                    "name": "migration",
                    "company_id": self.company.id,
                    "match_type": "mid",
                    "key": LONG,
                    "analytic_account_id": self.store_two.id,
                }
            )
        )
        self.assertTrue(forced.id)
