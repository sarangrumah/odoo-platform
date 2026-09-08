# -*- coding: utf-8 -*-
"""The POS chain: config → session → order, and the closing entry."""

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosOperatingUnit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        OU = cls.env["operating.unit"]
        cls.ho = OU.with_context(active_test=False).search(
            [("ou_type", "=", "company"), ("company_id", "=", cls.company.id)], limit=1
        ) or OU.create({"code": "ZZP-HO", "name": "Head Office", "ou_type": "company", "company_id": cls.company.id})
        cls.wh_a = cls.env["stock.warehouse"].create(
            {"name": "POS Test WH A", "code": "ZPA", "company_id": cls.company.id}
        )
        cls.wh_b = cls.env["stock.warehouse"].create(
            {"name": "POS Test WH B", "code": "ZPB", "company_id": cls.company.id}
        )
        cls.unit_a = OU.create(
            {
                "code": "ZZP-A",
                "name": "POS Store A",
                "parent_id": cls.ho.id,
                "company_id": cls.company.id,
                "warehouse_id": cls.wh_a.id,
            }
        )
        cls.unit_b = OU.create(
            {
                "code": "ZZP-B",
                "name": "POS Store B",
                "parent_id": cls.ho.id,
                "company_id": cls.company.id,
                "warehouse_id": cls.wh_b.id,
            }
        )
        cls.config_a = cls._make_config("POS Test A", cls.wh_a)
        cls.config_b = cls._make_config("POS Test B", cls.wh_b)

        groups = (
            cls.env.ref("base.group_user")
            | cls.env.ref("point_of_sale.group_pos_user")
            | cls.env.ref("custom_operating_unit.group_operating_unit_user")
        )
        cls.cashier = cls.env["res.users"].create(
            {
                "login": "ou.pos.cashier@test",
                "name": "Cashier A",
                "group_ids": [Command.set(groups.ids)],
                "operating_unit_ids": [Command.set([cls.unit_a.id])],
            }
        )

    @classmethod
    def _make_config(cls, name, warehouse):
        picking_type = cls.env["stock.picking.type"].search(
            [("warehouse_id", "=", warehouse.id), ("code", "=", "outgoing")], limit=1
        )
        return cls.env["pos.config"].create(
            {"name": name, "company_id": cls.company.id, "picking_type_id": picking_type.id}
        )

    def test_01_config_takes_the_unit_of_its_warehouse(self):
        self.assertEqual(self.config_a.operating_unit_id, self.unit_a)
        self.assertEqual(self.config_b.operating_unit_id, self.unit_b)

    def test_02_session_follows_its_config(self):
        session = self.env["pos.session"].create({"config_id": self.config_b.id})
        self.assertEqual(session.operating_unit_id, self.unit_b)

    def test_03_order_follows_its_session(self):
        session = self.env["pos.session"].create({"config_id": self.config_a.id})
        order = self.env["pos.order"].create(
            {
                "session_id": session.id,
                "company_id": self.company.id,
                "amount_tax": 0.0,
                "amount_total": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )
        self.assertEqual(order.operating_unit_id, self.unit_a)

    def test_04_cashier_sees_only_their_own_store(self):
        session_a = self.env["pos.session"].create({"config_id": self.config_a.id})
        session_b = self.env["pos.session"].create({"config_id": self.config_b.id})

        visible = self.env["pos.session"].with_user(self.cashier).search([("id", "in", (session_a | session_b).ids)])

        self.assertEqual(visible, session_a)

    def test_05_cashier_sees_only_their_own_point_of_sale(self):
        visible = (
            self.env["pos.config"].with_user(self.cashier).search([("id", "in", (self.config_a | self.config_b).ids)])
        )
        self.assertEqual(visible, self.config_a)

    def test_06_closing_entry_lines_are_stamped(self):
        """Every vals hook core uses must come back carrying the unit.

        The POS journal is company-wide, so the closing entry's lines have
        nothing to inherit from — if these hooks stop firing, the whole POS
        revenue stream silently leaves per-unit reporting.
        """
        session = self.env["pos.session"].create({"config_id": self.config_a.id})
        stamped = session._ou_stamp({"account_id": 1, "balance": 10.0})
        self.assertEqual(stamped["operating_unit_id"], self.unit_a.id)

    def test_07_stamping_is_a_no_op_without_a_unit(self):
        config = self._make_config(
            "POS Test No Unit",
            self.env["stock.warehouse"].create({"name": "POS Test WH C", "code": "ZPC", "company_id": self.company.id}),
        )
        session = self.env["pos.session"].create({"config_id": config.id})
        self.assertFalse(session.operating_unit_id)
        self.assertNotIn("operating_unit_id", session._ou_stamp({"balance": 1.0}))
