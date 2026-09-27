# -*- coding: utf-8 -*-
"""COGS inside the POS session's own closing entry (sheet #16).

The switch is empty by default, so the first thing these lock is that an
untouched database behaves exactly as it did. June–August 2026 are already
charged by ``COGS/2026/0001..0003``, and charging them a second time is the one
mistake here that cannot be undone — so the cutover guard gets more tests than
the happy path.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSessionCogs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.param = cls.env["ir.config_parameter"].sudo()
        cls.Session = cls.env["pos.session"]

    def _set_start(self, value):
        self.param.set_param("custom_levis_localization.cogs_session_start", value)

    def test_empty_switch_means_no_cutover_date(self):
        self._set_start("")
        session = self.Session.new({})
        self.assertIsNone(session._levis_session_cogs_start())

    def test_a_date_is_read_back(self):
        self._set_start("2026-09-01")
        session = self.Session.new({})
        self.assertEqual(session._levis_session_cogs_start(), date(2026, 9, 1))

    def test_whitespace_is_not_a_date(self):
        self._set_start("   ")
        session = self.Session.new({})
        self.assertIsNone(session._levis_session_cogs_start())

    def test_the_hook_is_inert_while_the_switch_is_empty(self):
        """No date, no COGS — whatever the session holds."""
        self._set_start("")
        session = self.Session.search([], limit=1)
        if not session:
            self.skipTest("no POS session in this database")
        lines, charges = session._levis_session_cogs_vals()
        self.assertEqual(lines, [])
        self.assertEqual(charges, [])

    def test_a_session_before_the_cutover_is_left_alone(self):
        """This is the guard that protects June–August from a second charge."""
        session = self.Session.search([("stop_at", "!=", False)], order="stop_at", limit=1)
        if not session:
            self.skipTest("no closed POS session in this database")
        stop = session.stop_at.date()
        # A cutover after this session: it must not be touched.
        self._set_start(date(stop.year + 1, 1, 1).isoformat())
        lines, charges = session._levis_session_cogs_vals()
        self.assertEqual(lines, [], "a session before the cutover must never be charged")
        self.assertEqual(charges, [])

    def test_the_charge_ledger_can_say_a_session_booked_it(self):
        """Without this value the monthly run would charge the units again."""
        field = self.env["levis.cogs.charge"]._fields["source"]
        self.assertIn("session", dict(field.selection))

    def test_lines_are_balanced_and_grouped_per_category(self):
        """Every category contributes exactly one debit and one credit."""
        session = self.Session.search([("stop_at", "!=", False)], order="stop_at desc", limit=1)
        if not session:
            self.skipTest("no closed POS session in this database")
        stop = session.stop_at.date()
        self._set_start(date(stop.year - 1, 1, 1).isoformat())
        lines, _charges = session._levis_session_cogs_vals()
        if not lines:
            self.skipTest("this session has nothing costed to book")
        self.assertEqual(len(lines) % 2, 0)
        debit = sum(line["debit"] for line in lines)
        credit = sum(line["credit"] for line in lines)
        self.assertAlmostEqual(debit, credit, places=2, msg="the inserted pair must balance")
        for line in lines:
            self.assertTrue(bool(line["debit"]) != bool(line["credit"]), "a leg is debit or credit, never both")

    def test_a_failure_never_blocks_the_close(self):
        """The COGS block must swallow whatever it throws.

        🔴 Inspect **this module's** class, not ``type(env['pos.session'])``.
        ``custom_operating_unit_docs`` also overrides ``_create_account_move``,
        and whichever module loads last is the one at the front of the MRO — so
        reading the method off the registry class tests somebody else's code.
        Exactly the trap ``_post.__module__`` sets on ``account.move``.
        """
        import inspect

        from odoo.addons.custom_levis_localization.models import pos_session

        source = inspect.getsource(pos_session.PosSession._create_account_move)
        self.assertIn("except Exception", source)
        self.assertIn("_logger.exception", source)

    def test_the_override_calls_super(self):
        """Two modules extend this method; dropping super() silently loses the
        Operating Unit stamp custom_operating_unit_docs puts on the entry."""
        import inspect

        from odoo.addons.custom_levis_localization.models import pos_session

        source = inspect.getsource(pos_session.PosSession._create_account_move)
        self.assertIn("super()._create_account_move", source)
