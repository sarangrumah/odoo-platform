# -*- coding: utf-8 -*-
"""The group's defaults have to *follow* the group, not merely seed it once.

Mirrors the Levi's chart: FA-OFFC (48 months, its own cost/accum/expense
accounts) and FA-VEH (96 months, a different trio). Every scenario the client
reported on row #55 of the issue sheet is pinned here.
"""

from datetime import date

from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAssetGroupDefaults(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env["account.account"]
        Journal = cls.env["account.journal"]

        def account(name, code, atype):
            return Account.create(
                {
                    "name": name,
                    "code": code,
                    "account_type": atype,
                    "company_ids": [(6, 0, [cls.company.id])],
                }
            )

        # FA-OFFC trio
        cls.offc_asset = account("Office equipment", "150210", "asset_fixed")
        cls.offc_accum = account("Accum. dep. office equipment", "150910", "asset_fixed")
        cls.offc_expense = account("Dep. expense office equipment", "610210", "expense")
        # FA-VEH trio
        cls.veh_asset = account("Vehicles", "150220", "asset_fixed")
        cls.veh_accum = account("Accum. dep. vehicles", "150920", "asset_fixed")
        cls.veh_expense = account("Dep. expense vehicles", "610220", "expense")

        cls.journal = Journal.search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)],
            limit=1,
        ) or Journal.create(
            {
                "name": "Misc Operations",
                "code": "MISCA",
                "type": "general",
                "company_id": cls.company.id,
            }
        )

        Group = cls.env["custom.fixed.asset.group"]
        cls.group_offc = Group.create(
            {
                "name": "Office and outlet equipment",
                "code": "T06-OFFC",
                "default_useful_life_months": 48,
                "default_asset_account_id": cls.offc_asset.id,
                "default_depreciation_account_id": cls.offc_accum.id,
                "default_expense_account_id": cls.offc_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )
        cls.group_veh = Group.create(
            {
                "name": "Vehicles",
                "code": "T06-VEH",
                "default_useful_life_months": 96,
                "default_asset_account_id": cls.veh_asset.id,
                "default_depreciation_account_id": cls.veh_accum.id,
                "default_expense_account_id": cls.veh_expense.id,
                "default_journal_id": cls.journal.id,
            }
        )
        # A group with no opinion at all (note: the group's own
        # default_useful_life_months defaults to 60, so a "bare" group has to
        # say 0 explicitly). Picking it must not blank the asset.
        cls.group_bare = Group.create(
            {
                "name": "Bare",
                "code": "T06-BARE",
                "default_useful_life_months": 0,
            }
        )

    def _new_form(self, group=None):
        form = Form(self.env["custom.fixed.asset"])
        form.name = "Scenario asset"
        form.acquisition_date = date(2026, 9, 15)
        form.acquisition_value = 12000.0
        if group is not None:
            form.group_id = group
        return form

    # -- 1. picking a group fills life and the four accounts -----------------
    def test_01_group_seeds_life_and_accounts(self):
        form = self._new_form(self.group_offc)
        self.assertEqual(form.useful_life_months, 48)
        self.assertEqual(form.asset_account_id, self.offc_asset)
        self.assertEqual(form.depreciation_account_id, self.offc_accum)
        self.assertEqual(form.expense_account_id, self.offc_expense)
        self.assertEqual(form.journal_id, self.journal)

    # -- 2. changing the group moves life AND the accounts -------------------
    def test_02_changing_group_moves_everything_saved_record(self):
        """The user's actual complaint: an existing asset, group swapped."""
        form = self._new_form(self.group_offc)
        asset = form.save()
        self.assertEqual(asset.useful_life_months, 48)

        with Form(asset) as edit:
            edit.group_id = self.group_veh
        self.assertEqual(asset.useful_life_months, 96)
        self.assertEqual(asset.asset_account_id, self.veh_asset)
        self.assertEqual(asset.depreciation_account_id, self.veh_accum)
        self.assertEqual(asset.expense_account_id, self.veh_expense)

    def test_03_changing_group_moves_everything_unsaved_record(self):
        """Same, but the group is flipped twice before the first save."""
        form = self._new_form(self.group_offc)
        self.assertEqual(form.useful_life_months, 48)
        form.group_id = self.group_veh
        self.assertEqual(form.useful_life_months, 96)
        self.assertEqual(form.asset_account_id, self.veh_asset)
        self.assertEqual(form.depreciation_account_id, self.veh_accum)
        self.assertEqual(form.expense_account_id, self.veh_expense)

    # -- 3. a hand-typed life survives a later group change ------------------
    def test_04_manual_useful_life_is_kept(self):
        form = self._new_form(self.group_offc)
        form.useful_life_months = 72
        asset = form.save()
        self.assertEqual(asset.useful_life_months, 72)

        with Form(asset) as edit:
            edit.group_id = self.group_veh
        # The override the accountant typed stays; the accounts still follow.
        self.assertEqual(asset.useful_life_months, 72)
        self.assertEqual(asset.asset_account_id, self.veh_asset)
        self.assertEqual(asset.depreciation_account_id, self.veh_accum)
        self.assertEqual(asset.expense_account_id, self.veh_expense)

    def test_05_manual_expense_account_is_kept(self):
        form = self._new_form(self.group_offc)
        asset = form.save()
        asset.expense_account_id = self.veh_expense  # deliberate override

        with Form(asset) as edit:
            edit.group_id = self.group_veh
        self.assertEqual(asset.expense_account_id, self.veh_expense)
        # The untouched ones still move.
        self.assertEqual(asset.asset_account_id, self.veh_asset)
        self.assertEqual(asset.useful_life_months, 96)

    # -- 4. create() cascades the same way -----------------------------------
    def test_06_create_with_group_only(self):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Imported asset",
                "group_id": self.group_offc.id,
                "acquisition_date": date(2026, 9, 15),
                "acquisition_value": 24000.0,
            }
        )
        self.assertEqual(asset.useful_life_months, 48)
        self.assertEqual(asset.asset_account_id, self.offc_asset)
        self.assertEqual(asset.depreciation_account_id, self.offc_accum)
        self.assertEqual(asset.expense_account_id, self.offc_expense)
        self.assertEqual(asset.journal_id, self.journal)
        asset.action_confirm()
        self.assertEqual(asset.state, "running")
        self.assertEqual(len(asset.depreciation_line_ids), 48)

    def test_07_create_honours_an_explicit_value(self):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Imported asset with override",
                "group_id": self.group_offc.id,
                "acquisition_date": date(2026, 9, 15),
                "acquisition_value": 24000.0,
                "useful_life_months": 72,
                "expense_account_id": self.veh_expense.id,
            }
        )
        self.assertEqual(asset.useful_life_months, 72)
        self.assertEqual(asset.expense_account_id, self.veh_expense)
        # Untouched keys still come from the group.
        self.assertEqual(asset.asset_account_id, self.offc_asset)

    # -- 5. a 0-based loaded schedule is never rebuilt into a duplicate ------
    def test_08_zero_based_schedule_not_duplicated(self):
        """The 60 FA-OFFC assets in prd_levis_begbal carry sequence 0..47 with
        the August line already posted. A rebuild must not issue a second line
        on that same date."""
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Legacy NVR",
                "group_id": self.group_offc.id,
                "acquisition_date": date(2026, 8, 27),
                "posting_date": date(2026, 8, 27),
                "depreciation_date_mode": "end_following_month",
                "acquisition_value": 4800.0,
                "useful_life_months": 48,
            }
        )
        Line = self.env["custom.fixed.asset.depreciation.line"]
        Line.create(
            [
                {
                    "asset_id": asset.id,
                    "sequence": seq,
                    "date": asset._depreciation_date_for(seq),
                    "amount": 100.0,
                    "posted": seq == 0,
                }
                for seq in range(48)
            ]
        )
        before = len(asset.depreciation_line_ids)
        august = asset.depreciation_line_ids.filtered(lambda line: line.date == date(2026, 8, 31))
        self.assertEqual(len(august), 1)

        asset._build_schedule()

        self.assertEqual(len(asset.depreciation_line_ids), before)
        august = asset.depreciation_line_ids.filtered(lambda line: line.date == date(2026, 8, 31))
        self.assertEqual(len(august), 1, "rebuild duplicated the already-posted August line")

    def test_09_normal_schedule_still_rebuilds(self):
        """The guard must not stop a 1-based schedule from being rebuilt."""
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Normal asset",
                "group_id": self.group_offc.id,
                "acquisition_date": date(2026, 9, 15),
                "acquisition_value": 4800.0,
            }
        )
        asset.action_confirm()
        self.assertEqual(len(asset.depreciation_line_ids), 48)
        asset.useful_life_months = 24
        asset._build_schedule()
        self.assertEqual(len(asset.depreciation_line_ids), 24)

    # -- 6. no group, and a group without defaults ---------------------------
    def test_10_asset_without_group_is_fine(self):
        form = self._new_form()
        form.useful_life_months = 36
        asset = form.save()
        self.assertFalse(asset.group_id)
        self.assertEqual(asset.useful_life_months, 36)

        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "No group at all",
                "acquisition_date": date(2026, 9, 15),
                "acquisition_value": 1000.0,
            }
        )
        self.assertEqual(asset.useful_life_months, 60)

    def test_11_group_without_defaults_keeps_current_values(self):
        form = self._new_form(self.group_offc)
        asset = form.save()
        with Form(asset) as edit:
            edit.group_id = self.group_bare
        self.assertEqual(asset.useful_life_months, 48)
        self.assertEqual(asset.expense_account_id, self.offc_expense)
        self.assertEqual(asset.asset_account_id, self.offc_asset)
        self.assertEqual(asset.journal_id, self.journal)

    def test_11b_group_life_of_sixty_still_follows(self):
        """A group that leaves default_useful_life_months at the model default
        (60) still has an opinion, and the asset takes it."""
        group_sixty = self.env["custom.fixed.asset.group"].create({"name": "Sixty", "code": "T06-SIXTY"})
        self.assertEqual(group_sixty.default_useful_life_months, 60)
        form = self._new_form(self.group_offc)
        asset = form.save()
        with Form(asset) as edit:
            edit.group_id = group_sixty
        self.assertEqual(asset.useful_life_months, 60)

    # -- the new schedule mode, off by default -------------------------------
    def test_12_end_acquisition_month_mode(self):
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "End of acquisition month",
                "group_id": self.group_offc.id,
                "acquisition_date": date(2026, 9, 15),
                "posting_date": date(2026, 9, 15),
                "depreciation_date_mode": "end_acquisition_month",
                "acquisition_value": 4800.0,
            }
        )
        self.assertEqual(asset._depreciation_date_for(1), date(2026, 9, 30))
        self.assertEqual(asset._depreciation_date_for(2), date(2026, 10, 31))
        asset.action_confirm()
        first = asset.depreciation_line_ids.sorted("sequence")[0]
        self.assertEqual(first.date, date(2026, 9, 30))

    def test_13_default_mode_stays_next_month(self):
        """The new mode ships switched off; the tenant parameter turns it on."""
        self.assertEqual(self.env["custom.fixed.asset"]._default_depreciation_date_mode(), "next_month")
        asset = self.env["custom.fixed.asset"].create(
            {
                "name": "Default mode",
                "acquisition_date": date(2026, 9, 15),
                "acquisition_value": 1000.0,
            }
        )
        self.assertEqual(asset.depreciation_date_mode, "next_month")

        self.env["ir.config_parameter"].sudo().set_param(
            "custom_accounting_asset.default_depreciation_date_mode", "end_acquisition_month"
        )
        self.assertEqual(
            self.env["custom.fixed.asset"]._default_depreciation_date_mode(),
            "end_acquisition_month",
        )
        # Rubbish in the parameter falls back rather than breaking creation.
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_accounting_asset.default_depreciation_date_mode", "nonsense"
        )
        self.assertEqual(self.env["custom.fixed.asset"]._default_depreciation_date_mode(), "next_month")
