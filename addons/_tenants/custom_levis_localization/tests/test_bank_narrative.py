# -*- coding: utf-8 -*-
"""The bank narrative parser (``levis.bank.narrative``).

Table-driven over the exact strings prd_levis_begbal contains, including the
malformed BRI values — a parser tested only on tidy input is a parser that will
silently return zero on the real feed.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBankNarrative(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parser = cls.env["levis.bank.narrative"]
        Journal = cls.env["account.journal"]
        cls.bca = Journal.create({"name": "BCA test", "code": "TBCA", "type": "bank", "levis_clearing_format": "bca"})
        cls.bri = Journal.create({"name": "BRI test", "code": "TBRI", "type": "bank", "levis_clearing_format": "bri"})
        cls.mute = Journal.create({"name": "Quiet", "code": "TQUI", "type": "bank"})
        cls.day = date(2026, 7, 10)

    def parse(self, journal, ref, amount=0.0, when=None):
        return self.parser.parse(journal, ref, amount, when or self.day)

    # --- BCA -----------------------------------------------------------
    def test_bca_debit_card(self):
        parsed = self.parse(
            self.bca,
            "KR OTOMATIS MID : 885004608387 LEVIS SENAYAN CITY TGH: 4722112.00 DDR: 32755.60",
            4689356.40,
        )
        self.assertEqual(parsed["kind"], "settlement")
        self.assertEqual(parsed["channel"], "debit")
        self.assertEqual(parsed["mid"], "885004608387")
        self.assertEqual(parsed["gross"], 4722112.00)
        self.assertEqual(parsed["mdr"], 32755.60)
        self.assertIsNone(parsed["trans_date"])
        self.assertEqual(parsed["confidence"], "derived")

    def test_bca_credit_card_zero_padded(self):
        parsed = self.parse(
            self.bca,
            "KARTU KREDIT MID:004608375 LEVIS GRAND INDONE TGH:00023226564.00 ADM:00000260192.00",
            22966372.00,
        )
        self.assertEqual(parsed["channel"], "credit")
        self.assertEqual(parsed["gross"], 23226564.00)
        self.assertEqual(parsed["mdr"], 260192.00)

    def test_bca_qris_carries_transaction_date(self):
        parsed = self.parse(
            self.bca,
            "KR OTOMATIS TANGGAL :09/07 MID : 885004608375 LEVIS GRAND INDONE QR : 40021190.00 DDR: 0.00",
            40021190.00,
        )
        self.assertEqual(parsed["channel"], "qris")
        self.assertEqual(parsed["gross"], 40021190.00)
        self.assertEqual(parsed["mdr"], 0.0)
        self.assertEqual(parsed["trans_date"], date(2026, 7, 9))
        self.assertEqual(parsed["confidence"], "exact")

    def test_bca_nfc_is_a_settlement_on_a_card_channel(self):
        """Contactless: the debit row shape with NFC where TGH would be.

        Both real examples from prd_levis_begbal July 2026. The second one is
        padded with runs of spaces, which is how the feed actually prints it.
        """
        for ref, gross in (
            ("KR OTOMATIS TANGGAL :11/07 MID : 885004648615 LEVIS GANCIT NFC: 875925.00 DDR: 0.00", 875925.00),
            (
                "KR OTOMATIS TANGGAL :28/07 MID : 885004608391  LEVIS PIM 2 NFC:     649900.00  DDR:          0.00",
                649900.00,
            ),
        ):
            parsed = self.parse(self.bca, ref, gross)
            self.assertEqual(parsed["kind"], "settlement", ref)
            self.assertEqual(parsed["gross"], gross)
            self.assertEqual(parsed["mdr"], 0.0)
            # gross - mdr must equal what the bank moved, or the caller reports a
            # mismatch and the line is not booked.
            self.assertEqual(parsed["gross"] - parsed["mdr"], gross)
            self.assertTrue(parsed["mid"])
            # Not "other": an unrecognised channel would be allowed to settle the
            # CASH receivable, which a card settlement must never do.
            self.assertIn(parsed["channel"], ("debit", "credit", "qris"))

    def test_bca_bare_day_month_rolls_back_a_year(self):
        """A December trading day on a January statement is last year's."""
        parsed = self.parse(
            self.bca,
            "KR OTOMATIS TANGGAL :31/12 MID : 885004608375 LEVIS X QR : 100.00 DDR: 0.00",
            100.0,
            when=date(2027, 1, 2),
        )
        self.assertEqual(parsed["trans_date"], date(2026, 12, 31))

    def test_bca_cash_deposit_keeps_the_words_that_name_a_store(self):
        parsed = self.parse(
            self.bca,
            "TRSF E-BANKING CR 0107/FTSCY/WS95031 1725850.00 cash sales pvj 30. 06.2026 ENDANG SAHLAN",
            1725850.00,
        )
        self.assertEqual(parsed["kind"], "cash_deposit")
        self.assertEqual(parsed["channel"], "cash")
        self.assertEqual(parsed["gross"], 1725850.00)
        self.assertIn("pvj", parsed["keyword"])
        # The serial and the amount must be gone, or every deposit is its own key.
        self.assertNotIn("WS95031", parsed["keyword"])
        self.assertNotIn("1725850", parsed["keyword"])

    def test_bca_charge_and_sweep(self):
        self.assertEqual(self.parse(self.bca, "BIAYA ADM", -30000.0)["kind"], "charge")
        swept = self.parse(self.bca, "TRSF E-BANKING DB 0107/SWBCA/WS95431 15000000000.00 ERA BUSANA RETAILI", -15e9)
        self.assertEqual(swept["kind"], "sweep")
        self.assertEqual(swept["gross"], 15e9)

    def test_bca_interest_is_not_a_clearing_item(self):
        self.assertEqual(self.parse(self.bca, "BUNGA", 801866.0)["kind"], "interest")
        self.assertEqual(self.parse(self.bca, "CR KOREKSI BUNGA", 100.0)["kind"], "interest")

    # --- BRI -----------------------------------------------------------
    def test_bri_settlement(self):
        parsed = self.parse(
            self.bri, "OnUs 1 260707 001999632288 LEVIS PONDOK AMT:2.301.775,00MDR:23.018,00", 2278757.0
        )
        self.assertEqual(parsed["kind"], "settlement")
        self.assertEqual(parsed["tid"], "001999632288")
        self.assertEqual(parsed["gross"], 2301775.00)
        self.assertEqual(parsed["mdr"], 23018.00)
        self.assertEqual(parsed["trans_date"], date(2026, 7, 7))

    def test_bri_missing_and_doubled_colons(self):
        """``AMT13.807.000,00MDR::145.172,00`` is what the feed really sends."""
        parsed = self.parse(
            self.bri, "OffUs 1 260707 001999632289 LEVIS PONDOK AMT13.807.000,00MDR::145.172,00", 13661828.0
        )
        self.assertEqual(parsed["gross"], 13807000.00)
        self.assertEqual(parsed["mdr"], 145172.00)

    def test_bri_misplaced_thousands_separator(self):
        """``MDR:1.3473,00`` means 13 473, not 1,3 or zero."""
        parsed = self.parse(self.bri, "OnUs 1 260707 001999632288 LEVIS X AMT:1.100.900,00MDR:1.3473,00", 1087427.0)
        self.assertEqual(parsed["mdr"], 13473.00)

    def test_bri_qris_channel(self):
        parsed = self.parse(self.bri, "QRISOffUs_3_260707_001999632292_LEVIS KE AMT:1.176.925,00MDR:0,00", 1176925.0)
        self.assertEqual(parsed["channel"], "qris")
        self.assertEqual(parsed["gross"], 1176925.00)

    def test_bri_prior_month_trading_day(self):
        """A June trading day settling in July, which really occurs in the data."""
        parsed = self.parse(self.bri, "OnUs 1 260630 001999632288 LEVIS PONDOK AMT:1.000.900,00MDR:1.501,00", 999399.0)
        self.assertEqual(parsed["trans_date"], date(2026, 6, 30))

    def test_bri_cheque_clearing_stays_unknown(self):
        """Its destination is not in the narrative, so it must stay visible."""
        parsed = self.parse(self.bri, "CAIR CEK UNTUK RTGS ESB INDS", -1533030000.0)
        self.assertEqual(parsed["kind"], "unknown")
        self.assertEqual(parsed["gross"], 0.0)

    def test_bri_interest(self):
        self.assertEqual(self.parse(self.bri, "Interest on Account", 801866.0)["kind"], "interest")

    # --- refusals ------------------------------------------------------
    def test_unreadable_never_becomes_zero_silently(self):
        for ref in ("", "   ", "TOTAL GIBBERISH 1234", "KR OTOMATIS MID : 1 LEVIS X TGH: DDR:"):
            parsed = self.parse(self.bca, ref, 0.0)
            self.assertEqual(parsed["kind"], "unknown", ref)
            self.assertTrue(parsed["note"], "an unparsed line must say why")

    def test_journal_without_a_format_parses_nothing(self):
        parsed = self.parse(self.mute, "KR OTOMATIS MID : 885004608387 X TGH: 100.00 DDR: 1.00")
        self.assertEqual(parsed["kind"], "unknown")

    def test_number_normalisers_report_failure(self):
        self.assertEqual(self.parser._num_en("1234567.00"), (1234567.00, True))
        self.assertEqual(self.parser._num_en("00023226564.00"), (23226564.00, True))
        self.assertEqual(self.parser._num_en("1725850"), (1725850.00, True))
        self.assertEqual(self.parser._num_id("2.301.775,00"), (2301775.00, True))
        self.assertEqual(self.parser._num_id("1.3473,00"), (13473.00, True))
        self.assertEqual(self.parser._num_en("-")[1], False)
        self.assertEqual(self.parser._num_id("")[1], False)
