# -*- coding: utf-8 -*-
"""Naming the store behind a cash deposit, from what the cashier actually typed.

A card settlement carries a merchant id, so the store is a lookup. A cash
deposit carries nothing but free text a cashier typed into a transfer form, and
that text is written differently every time. Two signals in it turned out to be
worth reading, measured against the deposits Finance had already mapped by hand:

* the **terminal code** of the machine the money was paid in at (``WSID:ZT481``,
  or the bare ``Z8VR1`` an e-banking transfer carries). Staff use the machines
  nearest the shop, so 31 of the 33 codes observed resolve to exactly one store;
* the **store shorthand**, which is the same handful of letters every time and
  is broken up with spaces at random: ``k gm``, ``bi p``, ``T smc``.

The shorthand is why matching now also runs on a separator-free copy of the
narrative. Before that, Kelapa Gading needed one rule per spelling, and Central
Park really did have three (``ols cp``, ``levis c p``, ``setor cp``).

The tests below pin the three decisions that carry risk: that a terminal is
compared whole rather than by its digits, that an unmapped terminal does not
block the text rules, and that compacting never lets a two-letter rule match
inside somebody's name.
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "levis")
class TestCashDepositMapping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.parser = cls.env["levis.bank.narrative"]
        cls.Map = cls.env["levis.bank.mid.map"]
        plan = cls.env["account.analytic.plan"].create({"name": "OU Cash Map Test"})

        def ou(name):
            return cls.env["account.analytic.account"].create(
                {"name": name, "plan_id": plan.id, "company_id": cls.company.id}
            )

        cls.kgm = ou("KELAPA GADING MALL")
        cls.gi = ou("GRAND INDONESIA")
        # The parser dispatches on the journal's declared grammar; without it
        # every narrative falls to _parse_none and nothing below is exercised.
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Bank Cash Map",
                "type": "bank",
                "code": "BCMT",
                "company_id": cls.company.id,
                "levis_clearing_format": "bca",
            }
        )

    def _rule(self, match_type, key, ou, **kw):
        return self.Map.create(
            {
                "name": f"{match_type} {key}",
                "match_type": match_type,
                "key": key,
                "analytic_account_id": ou.id,
                "company_id": self.company.id,
                **kw,
            }
        )

    def _resolve(self, ref):
        parsed = self.parser.parse(self.journal, ref, 1_000_000.0, None)
        return parsed, self.Map._resolve(self.company, self.journal, parsed, None)

    # -- the terminal ---------------------------------------------------
    def test_01_terminal_is_read_in_both_spellings(self):
        for ref, expect in (
            ("SETORAN VIA CDM 05/07 WSID:ZT481 IRWAN ASTRIA JAYA", "ZT481"),
            ("TRSF E-BANKING CR 07/03 Z8VR1 RISA INDRIYANI", "Z8VR1"),
        ):
            parsed, _rule = self._resolve(ref)
            self.assertEqual(parsed["terminal"], expect, ref)
            self.assertEqual(parsed["channel"], "cash")

    def test_02_terminal_is_compared_whole_not_by_its_digits(self):
        """``_normalise_key`` keeps digits only: Z6FK1 would become 61."""
        self._rule("terminal", "Z6FK1", self.kgm)
        self._rule("tid", "1999632261", self.gi)
        _parsed, rule = self._resolve("TRSF E-BANKING CR 07/03 Z6FK1 ASSHA RUFNA ZANUBA")
        self.assertEqual(rule.analytic_account_id, self.kgm, "a terminal matched on digits collides with merchant ids")

    def test_03_one_store_may_own_several_terminals(self):
        for code in ("ZL6F1", "ZL6D1", "ZL6C1"):
            self._rule("terminal", code, self.gi)
        for code in ("ZL6F1", "ZL6D1", "ZL6C1"):
            _parsed, rule = self._resolve(f"TRSF E-BANKING CR 07/03 {code} ADAM SURYONO")
            self.assertEqual(rule.analytic_account_id, self.gi, code)

    def test_04_unmapped_terminal_falls_through_to_the_text(self):
        """Unlike a MID: the machine is a hint, whoever walks up to it."""
        self._rule("keyword", "KGM", self.kgm)
        parsed, rule = self._resolve("TRSF E-BANKING CR 07/03 Z9ZZ9 setoran cash ols k gm 010826 ASSHA")
        self.assertEqual(parsed["terminal"], "Z9ZZ9")
        self.assertEqual(rule.analytic_account_id, self.kgm)

    # -- the shorthand --------------------------------------------------
    def test_05_shorthand_matches_however_it_is_spaced(self):
        self._rule("keyword", "KGM", self.kgm)
        for ref in (
            "TRSF E-BANKING CR 0207/FTSCY/WS95031 100.00 setoran cash ols k gm 010826 ASSHA",
            "TRSF E-BANKING CR 0207/FTSCY/WS95031 100.00 setoran cash ols kgm 010826 ASSHA",
            "TRSF E-BANKING CR 0207/FTSCY/WS95031 100.00 setoran cash ols KG M 010826 ASSHA",
        ):
            _parsed, rule = self._resolve(ref)
            self.assertEqual(rule.analytic_account_id, self.kgm, ref)

    def test_06_a_two_letter_rule_is_never_compacted(self):
        """Compacted, 'CP' lands inside a name and quietly claims the deposit."""
        self._rule("keyword", "CP", self.gi)
        _parsed, rule = self._resolve("TRSF E-BANKING CR 07/03 Z1111 setoran cash MUHAMMAD RESKY")
        self.assertFalse(rule, "a two-letter key matched inside free text")

    def test_07_the_longest_rule_wins(self):
        self._rule("keyword", "SMB", self.gi, sequence=20)
        self._rule("keyword", "SMB SOPIAN", self.kgm, sequence=20)
        _parsed, rule = self._resolve("TRSF E-BANKING CR 07/03 Z1111 setoran smb sopian permana")
        self.assertEqual(rule.analytic_account_id, self.kgm)

    # -- the guards -----------------------------------------------------
    def test_08_two_rules_may_not_claim_one_terminal(self):
        self._rule("terminal", "ZT481", self.kgm)
        with self.assertRaises(ValidationError):
            self._rule("terminal", "zt-481", self.gi)

    def test_09_one_shorthand_spelled_two_ways_is_one_rule(self):
        self._rule("keyword", "ols cp", self.kgm)
        with self.assertRaises(ValidationError):
            self._rule("keyword", "olscp", self.gi)

    def test_10_a_card_settlement_is_untouched(self):
        """The whole point of the model: cards are matched on their MID alone."""
        self._rule("keyword", "LEVIS", self.gi)
        parsed, rule = self._resolve("KR OTOMATIS MID : 885004608383 LEVIS MALL KELAPA TGH: 1349900.00 DDR: 2024.85")
        self.assertEqual(parsed["kind"], "settlement")
        self.assertFalse(parsed["terminal"])
        self.assertFalse(rule, "an unmapped MID must not fall through to the text")
