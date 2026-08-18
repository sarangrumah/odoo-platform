# -*- coding: utf-8 -*-
"""Tests for POS session acquisition during an import.

The bug these pin: ``get_session`` used to call ``pos.session.create()`` blind.
Odoo permits at most one non-closed session per register, so the moment anybody
opened that POS in the UI the create raised ValidationError, the executor re-raised,
and the ENTIRE file died — one stray session on one store cost prd_levis_begbal
eight consecutive nights of sales in Aug-2026.

Two properties matter, and they pull in opposite directions:

* an EMPTY stray session must be adopted rather than fought with, otherwise the
  import stays hostage to whoever clicked "Open Register";
* a session WITH orders must never be adopted, because posting imported orders into
  a live shift would mix a cashier's takings into the import's closing entry.

``point_of_sale`` is not a dependency of this addon (the executor reaches for
``pos.session`` lazily, only on tenants that have it), so these tests inject a fake
POS model rather than installing the app — same technique as
``test_x24_pending_replay``, which patches the heavy POS calls out for the same
reason.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.custom_retail_import.models.retail_import_executor import RetailSessionBusy


def _fake_session(state="opened", orders=(), stock_at_closing=False):
    """A stand-in for a pos.session record: only what _ri_open_session touches."""
    s = MagicMock()
    s.id = 4041
    s.state = state
    s.order_ids = list(orders)
    s.update_stock_at_closing = stock_at_closing

    def _write(vals):
        for k, v in vals.items():
            setattr(s, k, v)

    s.write.side_effect = _write
    return s


@tagged("post_install", "-at_install")
class TestPosSessionAdoption(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Executor = cls.env["retail.import.executor"]

    def _run(self, existing, created=None):
        """Call _ri_open_session with pos.session faked out. Returns (result, Session)."""
        Session = MagicMock()
        Session.search.return_value = existing or []
        Session.create.return_value = created if created is not None else _fake_session(state="opening_control")
        cfg = MagicMock()
        cfg.id = 5
        cfg.display_name = "OLS SES - KELAPA GADING MALL"
        real_getitem = type(self.env).__getitem__

        def _getitem(env_self, name):
            if name == "pos.session":
                return Session
            return real_getitem(env_self, name)

        with patch.object(type(self.env), "__getitem__", _getitem):
            return self.Executor._ri_open_session(cfg), Session, cfg

    def test_opens_a_session_when_none_is_live(self):
        """Nothing open on the register: behave exactly as before, i.e. create one."""
        created = _fake_session(state="opening_control")
        result, Session, cfg = self._run(existing=[], created=created)
        Session.create.assert_called_once()
        self.assertIs(result, created)
        self.assertEqual(result.state, "opened", "session must end up opened, or the close books no GL")

    def test_adopts_an_empty_stray_session(self):
        """An empty session left over from the UI is reused, not fought with."""
        stray = _fake_session(state="opening_control", orders=())
        result, Session, cfg = self._run(existing=stray)
        Session.create.assert_not_called()
        self.assertIs(result, stray)
        self.assertEqual(result.state, "opened")

    def test_adopted_session_never_moves_stock(self):
        """Decision B holds for an adopted session too: imported POS books no stock."""
        stray = _fake_session(state="opened", stock_at_closing=True)
        result, _Session, _cfg = self._run(existing=stray)
        self.assertFalse(
            result.update_stock_at_closing,
            "adopting a session must not let the close create pickings — that double-counts on-hand",
        )

    def test_refuses_a_session_that_holds_orders(self):
        """A live shift is off limits; the caller parks that store and imports the rest."""
        busy_session = _fake_session(state="opened", orders=(MagicMock(),))
        with self.assertRaises(RetailSessionBusy) as caught:
            self._run(existing=busy_session)
        msg = str(caught.exception)
        self.assertIn("KELAPA GADING", msg, "the message must name the store a human has to go close")
        self.assertIn("4041", msg)
        self.assertIs(caught.exception.session, busy_session)
