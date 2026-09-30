# -*- coding: utf-8 -*-
"""What the MDR view must get right, and what it must refuse to guess.

The arithmetic is trivial. The judgement is not, and these tests pin the
judgement: an unpriced transaction reads as unknown rather than free, a resent
week supersedes rather than doubles, and a rate that changed does not restate
the days before it changed.
"""

from __future__ import annotations

import json

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

#: A store code that cannot exist in a restored database. The fixtures must not
#: collide with whatever real feed rows the test database happens to carry, and a
#: clone of a working tenant carries plenty.
_STORE = "TESTMDR"


@tagged("post_install", "-at_install", "levis", "mdr")
class TestLevisMdr(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.nightly = cls.env.ref("custom_retail_import.profile_levis_x70d")
        cls.store = cls.env.ref("custom_retail_import.profile_levis_x70d_store")
        cls.Txn = cls.env["levis.mdr.txn"]
        cls.Rate = cls.env["levis.mdr.rate"]

    # -- helpers -------------------------------------------------------
    def _stage(self, profile, rows):
        log = self.env["retail.import.log"].create(
            {"profile_id": profile.id, "filename": f"{profile.code}.xlsx", "company_id": self.company.id}
        )
        self.env["retail.import.line"].create(
            [{"log_id": log.id, "row_number": i, "raw_data_json": json.dumps(r)} for i, r in enumerate(rows, 1)]
        )
        return log

    def _nightly_row(self, transnum, amount, date="2026-09-17", tender="OFFLINE_OTHER_CREDITCARD"):
        return {
            "store_code": _STORE,
            "trans_date": date,
            "register": "1",
            "transnum": str(transnum),
            "tender_type": tender,
            "tender_amount": str(amount),
        }

    def _store_row(self, transnum, amount, payment, date="2026-09-17", appr="113512"):
        row = self._nightly_row(transnum, amount, date)
        row.update({"payment": payment, "appr_code": appr})
        return row

    def _txn(self, transnum, date="2026-09-17"):
        return self.Txn.search(
            [("store_code", "=", _STORE), ("transnum", "=", str(transnum)), ("trans_date", "=", date)]
        )

    # -- tests ---------------------------------------------------------
    def test_01_rate_is_applied_to_the_matching_transaction(self):
        self._stage(self.nightly, [self._nightly_row(5372, 2649700)])
        self._stage(self.store, [self._store_row(5372, 2649700, "BCA - DEBIT BCA / BCA GPN")])
        txn = self._txn(5372)
        self.assertEqual(len(txn), 1)
        self.assertEqual(txn.payment, "BCA - DEBIT BCA / BCA GPN")
        self.assertEqual(txn.mdr_percent, 0.15)
        # 2.649.700 x 0,15% = 3.974,55
        self.assertAlmostEqual(txn.mdr_amount, 3974.55, places=2)
        self.assertAlmostEqual(txn.net_settlement, 2649700 - 3974.55, places=2)

    def test_02_a_zero_rate_is_a_rate(self):
        """QRIS really is 0% at BCA. It must price, not read as unknown."""
        self._stage(self.nightly, [self._nightly_row(5379, 1550900)])
        self._stage(self.store, [self._store_row(5379, 1550900, "BCA - QRIS")])
        txn = self._txn(5379)
        self.assertTrue(txn.rate_id, "a 0% rate must still resolve to a rate")
        self.assertEqual(txn.mdr_amount, 0.0)
        self.assertEqual(txn.net_settlement, 1550900)

    def test_03_unlabelled_transaction_is_unknown_not_free(self):
        """A store that has not sent its export must not look like a zero fee."""
        self._stage(self.nightly, [self._nightly_row(5388, 1050900)])
        txn = self._txn(5388)
        self.assertEqual(len(txn), 1, "the nightly file is the population; the row must still be there")
        self.assertFalse(txn.payment)
        self.assertFalse(txn.rate_id)
        # Read the column raw: the ORM presents a NULL Monetary as 0.0, which is
        # exactly the confusion this test exists to prevent.
        self.assertIsNone(
            self._raw_mdr(5388),
            "MDR must be NULL, not 0, so a SUM over the day cannot silently understate",
        )

    def _raw_mdr(self, transnum):
        self.env.cr.execute(
            "SELECT mdr_amount FROM levis_mdr_txn WHERE store_code = %s AND transnum = %s",
            (_STORE, str(transnum)),
        )
        row = self.env.cr.fetchone()
        return row[0] if row else False

    def test_04_a_resent_week_supersedes_it_does_not_double(self):
        """Stores resend the whole month weekly; the latest import wins."""
        self._stage(self.nightly, [self._nightly_row(5391, 3200900)])
        self._stage(self.store, [self._store_row(5391, 3200900, "BCA - QRIS")])
        # The store spots the mistake and resends the week with the real tender.
        self._stage(self.store, [self._store_row(5391, 3200900, "BCA - REGULAR OFF US")])
        txn = self._txn(5391)
        self.assertEqual(len(txn), 1, "a resent week must not multiply the transaction")
        self.assertEqual(txn.payment, "BCA - REGULAR OFF US")
        self.assertEqual(txn.mdr_percent, 1.2)

    def test_05_a_rate_change_does_not_restate_earlier_days(self):
        self.Rate.create(
            {
                "payment": "BCA - QRIS",
                "acquirer": "BCA",
                "percent": 0.7,
                "date_from": "2026-09-15",
                "company_id": self.company.id,
            }
        )
        self._stage(
            self.nightly,
            [self._nightly_row(4671, 2000800, date="2026-09-01"), self._nightly_row(5379, 1550900)],
        )
        self._stage(
            self.store,
            [
                self._store_row(4671, 2000800, "BCA - QRIS", date="2026-09-01"),
                self._store_row(5379, 1550900, "BCA - QRIS"),
            ],
        )
        before = self._txn(4671, date="2026-09-01")
        after = self._txn(5379)
        self.assertEqual(before.mdr_percent, 0.0, "1 September predates the new rate")
        self.assertEqual(after.mdr_percent, 0.7, "17 September is after it")

    def test_06_cash_approval_code_zero_reads_as_absent(self):
        self._stage(self.nightly, [self._nightly_row(4678, 749900, tender="CASH")])
        self._stage(self.store, [self._store_row(4678, 749900, "CASH", appr="0")])
        self.assertFalse(self._txn(4678).appr_code)

    def test_07_seeded_rates_cover_every_label_the_stores_write(self):
        """The 39 PAYMENT values of the client's own dropdown must all price."""
        labels = [
            "CASH",
            "TRANSFER",
            "CANCEL",
            "BCA - QRIS",
            "BCA - DEBIT BCA / BCA GPN",
            "BCA - DEBIT OTHER",
            "BCA - BCA Card",
            "BCA - REGULAR ON US",
            "BCA - REGULAR OFF US",
            "BCA - 0% 3 Bln",
            "BCA - 0% 6 Bln",
            "BCA - 0% 12 Bln",
            "BCA - JCB On Us",
            "BCA - JCB Off Us",
            "BCA - AMEX On Us",
            "BCA - AMEX Off Us",
            "BCA - UNION PAY On Us",
            "BCA - UNION PAY Off Us",
            "BNI - QRIS",
            "BNI - DEBIT BNI / BNI GPN",
            "BNI - DEBIT OTHER",
            "BNI - REGULAR ON US",
            "BNI - REGULAR OFF US",
            "BNI - 0% 3 Bln",
            "BNI - 0% 6 Bln",
            "BNI - 0% 12 Bln",
            "MANDIRI - QRIS",
            "MANDIRI - DEBIT MANDIRI/MANDIRI GPN",
            "MANDIRI - DEBIT OTHER",
            "MANDIRI - REGULAR ON US",
            "MANDIRI - REGULAR OFF US",
            "MANDIRI - 0% 3 BLN",
            "MANDIRI - 0% 6 Bln",
            "MANDIRI - 0% 12 Bln",
            "BRI - QRIS",
            "BRI - DEBIT BRI / BRI GPN",
            "BRI - DEBIT OTHER",
            "BRI - REGULAR ON US",
            "BRI - REGULAR OFF US",
        ]
        self.assertEqual(len(labels), 39)
        on_file = set(self.Rate.search([]).mapped("payment"))
        self.assertFalse(set(labels) - on_file, "a tender type the stores can write has no rate")

    def test_08_qris_stays_zero_at_bca_bni_bri_and_is_not_zero_at_mandiri(self):
        """Confirmed with the client on 2026-09-18; the contrast is the evidence."""
        rate = lambda label: self.Rate.search([("payment", "=", label)], limit=1).percent  # noqa: E731
        self.assertEqual(rate("BCA - QRIS"), 0.0)
        self.assertEqual(rate("BNI - QRIS"), 0.0)
        self.assertEqual(rate("BRI - QRIS"), 0.0)
        self.assertEqual(rate("MANDIRI - QRIS"), 0.7)

    def test_09_percent_is_a_percent(self):
        with self.assertRaises(ValidationError):
            self.Rate.create({"payment": "TEST - UNIT", "percent": 15.0 * 100})
        with self.assertRaises(ValidationError):
            self.Rate.create({"payment": "TEST - NEGATIVE", "percent": -1.0})

    # -- the store vocabularies ----------------------------------------
    def test_10_punctuation_and_case_need_no_alias(self):
        """Four stores, one tender, four spellings -- and no rows to maintain."""
        for i, written in enumerate(("BCA-QRIS", "bca qris", "BCA _ QRIS", "  BCA - QRIS  "), start=1):
            transnum = 7100 + i
            self._stage(self.nightly, [self._nightly_row(transnum, 1000000)])
            self._stage(self.store, [self._store_row(transnum, 1000000, written)])
            txn = self._txn(transnum)
            self.assertEqual(txn.payment, "BCA - QRIS", f"{written!r} must resolve without an alias")
            self.assertEqual(txn.mdr_percent, 0.0)
            self.assertIsNotNone(self._raw_mdr(transnum), f"{written!r} priced as unknown")

    def test_11_alias_maps_a_store_wording_to_the_rate_label(self):
        """'QRIS BCA' is the single biggest gap in Sep-2026: 798 trx, Rp 1,27 M."""
        self._stage(self.nightly, [self._nightly_row(7201, 2000000)])
        self._stage(self.store, [self._store_row(7201, 2000000, "QRIS BCA")])
        txn = self._txn(7201)
        self.assertEqual(txn.payment, "BCA - QRIS", "the seeded alias must resolve the word order")
        self.assertEqual(txn.mdr_percent, 0.0)
        self.assertEqual(self._raw_mdr(7201), 0, "a QRIS fee is a real zero, not unknown")

    def test_12_on_us_and_off_us_debit_are_not_the_same_rate(self):
        """0,15% against 1,00%: reading these two the same way costs real money."""
        self._stage(self.nightly, [self._nightly_row(7301, 1000000), self._nightly_row(7302, 1000000)])
        self._stage(
            self.store,
            [
                self._store_row(7301, 1000000, "DEBIT BCA ON US"),
                self._store_row(7302, 1000000, "DEBIT BCA OFF US"),
            ],
        )
        self.assertEqual(self._txn(7301).payment, "BCA - DEBIT BCA / BCA GPN")
        self.assertEqual(self._txn(7301).mdr_percent, 0.15)
        self.assertEqual(self._txn(7302).payment, "BCA - DEBIT OTHER")
        self.assertEqual(self._txn(7302).mdr_percent, 1.0)

    def test_13_swapped_columns_still_price(self):
        """Four stores export PAYMENT and APPR CODE the other way round."""
        self._stage(self.nightly, [self._nightly_row(7401, 3000000)])
        self._stage(self.store, [self._store_row(7401, 3000000, "544088", appr="BCA - REGULAR ON US")])
        txn = self._txn(7401)
        self.assertEqual(txn.payment, "BCA - REGULAR ON US", "the label was in the approval-code column")
        self.assertEqual(txn.appr_code, "544088", "and the approval code in the label column")
        self.assertTrue(txn.label_swapped)
        self.assertEqual(txn.mdr_percent, 1.0)

    def test_14_an_unknown_wording_is_still_unknown(self):
        """The alias table must not become a licence to guess.

        A tender type typed into the acquirer column spans three rates; an approval
        code names no acquirer at all. Both have to stay null, or a store-day total
        would read as complete when it is not.
        """
        for transnum, payment, appr in (
            (7501, "OFFLINE_OTHER_CREDITCARD", "113512"),
            (7502, "DEBIT CARD OTHER", "463827"),
            (7503, "-", ""),
            (7504, "A78E9B", "OFFLINE_VISA"),
        ):
            self._stage(self.nightly, [self._nightly_row(transnum, 999900)])
            self._stage(self.store, [self._store_row(transnum, 999900, payment, appr=appr)])
            self.assertFalse(self._txn(transnum).rate_id, f"{payment!r} must not resolve to a rate")
            self.assertIsNone(self._raw_mdr(transnum), f"{payment!r} must price as unknown, not zero")

    def test_15_alias_target_must_be_a_real_rate_label(self):
        Alias = self.env["levis.mdr.alias"]
        with self.assertRaises(ValidationError):
            Alias.create({"alias": "QRIS BCAA", "payment": "BCA - QRIZ"})
        # And two aliases that differ only by punctuation are the same key.
        Alias.create({"alias": "TEST QRIS ONE", "payment": "BCA - QRIS"})
        with self.assertRaises(ValidationError):
            Alias.create({"alias": "TEST-QRIS-ONE", "payment": "BCA - QRIS"})

    def test_16_seeded_aliases_all_resolve(self):
        """Every alias shipped must point at a label that exists, or it is dead weight."""
        Alias = self.env["levis.mdr.alias"]
        on_file = {
            "".join(ch for ch in (p or "").upper() if ch.isalnum()) for p in self.Rate.search([]).mapped("payment")
        }
        for rec in Alias.search([]):
            key = "".join(ch for ch in (rec.payment or "").upper() if ch.isalnum())
            self.assertIn(key, on_file, f"alias {rec.alias!r} points at a label with no rate")
