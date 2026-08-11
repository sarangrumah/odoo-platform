# -*- coding: utf-8 -*-
"""Reading gross, fee and transaction date out of a bank statement narrative.

This is what removes the client workbook from the monthly clearing. The
acquirer already prints, on every settlement line, the three numbers the
clearing needs:

    BCA debit   KR OTOMATIS MID : 885004608387 LEVIS SENAYAN CITY
                TGH: 4722112.00 DDR: 32755.60
    BCA credit  KARTU KREDIT MID:004608375 LEVIS GRAND INDONE
                TGH:00023226564.00 ADM:00000260192.00
    BCA QRIS    KR OTOMATIS TANGGAL :09/07 MID : 885004608375 ...
                QR : 40021190.00 DDR: 0.00
    BRI         OnUs 1 260707 001999632288 LEVIS PONDOK
                AMT:2.301.775,00MDR:23.018,00

``TGH``/``QR``/``AMT`` is the gross billed to the acquirer, ``DDR``/``ADM``/``MDR``
the fee it withheld, and the money that actually landed is the difference. The
old host script could not use this: it took MDR from the client's monthly bank
sheet and had to spread it across a store's settlement dates pro-rata, because
the two sources were on different grains. Here the fee is exact per settlement.

Three rules hold everywhere in this module:

* **A number that cannot be read is never zero.** Both normalisers return an
  ``ok`` flag, and a failure raises the line to ``kind="unknown"`` so it is
  counted and shown. An understated MDR nobody notices is worse than a visible gap.
* **The narrative must agree with the money.** ``gross - mdr`` is checked against
  the statement line's own amount by the caller; a mismatch is a finding, not a
  rounding to be absorbed.
* **Ambiguity stays ambiguous.** ``CAIR CEK UNTUK RTGS`` — a cheque clearing
  whose destination Treasury never confirmed — is deliberately classified
  ``unknown`` so it remains visible on suspense instead of being booked
  somewhere plausible.

Adding a bank is one ``_parse_<format>`` method plus one value on
``account.journal.levis_clearing_format``.
"""

import re

from dateutil.relativedelta import relativedelta

from odoo import api, models

# --- BCA ------------------------------------------------------------------
# "MID : 885004608387" and "MID:004608375" are the same field, spaced differently.
_BCA_MID = re.compile(r"MID\s*:?\s*(\d+)")
# "TANGGAL :09/07" — the transaction date, present on QRIS and on some card rows.
_BCA_TANGGAL = re.compile(r"TANGGAL\s*:?\s*(\d{1,2})\s*/\s*(\d{1,2})")
_BCA_GROSS = re.compile(r"(?:TGH|QR)\s*:?\s*([\d.,]+)")
_BCA_FEE = re.compile(r"(?:DDR|ADM)\s*:?\s*([\d.,]+)")

# --- BRI ------------------------------------------------------------------
# Fields are separated by spaces or underscores depending on the channel, and
# the colons after AMT/MDR are unreliable: the real data contains "AMT13.807.000,00"
# (no colon) and "MDR::145.172,00" (two), so the separator is optional/repeatable.
_BRI_SETTLE = re.compile(
    r"(?P<qris>QRIS)?(?P<onus>OnUs|OffUs)[\s_]+\d+[\s_]+"
    r"(?P<yymmdd>\d{6})[\s_]+(?P<tid>\d{6,})[\s_]+"
    r"(?P<store>.*?)"
    r"AMT[:\s]*(?P<gross>[\d.,]+)\s*MDR[:\s]*(?P<fee>[\d.,]+)",
    re.IGNORECASE,
)

# Noise stripped before a free-text cash deposit is offered as a keyword rule.
_NOISE = (
    re.compile(r"\b\d{1,4}/[A-Z]+/[A-Z0-9]+\b"),  # 0107/FTSCY/WS95031
    re.compile(r"\b\d{1,2}/\d{1,2}\b"),  # 07/25
    re.compile(r"\bWS\d+\b"),
    re.compile(r"\b(?:FTSCY|SWBCA|ZC\d+)\b"),
    # Transfer reference codes: a short alphanumeric blob with both letters and
    # digits (ZL6H, ZKB1, Z6FR). Left in, every deposit becomes its own group.
    re.compile(r"\b(?=[A-Z0-9]{4,8}\b)(?=[A-Z0-9]*\d)[A-Z][A-Z0-9]*\b"),
    re.compile(r"\b\d{1,2}[.\-/ ]\s*\d{1,2}[.\-/ ]\s*\d{2,4}\b"),  # 30. 06.2026
    re.compile(r"\b[\d.,]+\b"),
)

# A transaction date more than this far after its statement date means the
# narrative's bare dd/mm belongs to the previous year.
_YEAR_ROLLBACK_DAYS = 60


class LevisBankNarrative(models.AbstractModel):
    _name = "levis.bank.narrative"
    _description = "Bank Narrative Parser"

    # ------------------------------------------------------------------
    # Number formats — deliberately two functions, never one that guesses
    # ------------------------------------------------------------------
    @api.model
    def _num_en(self, raw):
        """``1234567.00``, possibly zero-padded to ``00023226564.00``."""
        cleaned = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == ".")
        if not any(ch.isdigit() for ch in cleaned):
            return 0.0, False
        whole, _sep, frac = cleaned.rpartition(".")
        if not whole:
            whole, frac = frac, ""
        return float("%s.%s" % (whole.replace(".", "") or "0", (frac + "00")[:2])), True

    @api.model
    def _num_id(self, raw):
        """``2.301.775,00`` — and the malformations BRI really emits.

        Every dot is discarded rather than validated as a thousands group,
        because ``MDR:1.3473,00`` (a misplaced separator, seen in the July data)
        means 13.473 and would otherwise have to be rejected.
        """
        cleaned = "".join(ch for ch in (raw or "") if ch.isdigit() or ch in ".,")
        if not any(ch.isdigit() for ch in cleaned):
            return 0.0, False
        whole, _sep, frac = cleaned.rpartition(",")
        if not whole:
            whole, frac = frac, ""
        return float("%s.%s" % (whole.replace(".", "") or "0", (frac + "00")[:2])), True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _blank(self, payment_ref, **overrides):
        parsed = {
            "kind": "unknown",
            "mid": None,
            "tid": None,
            "keyword": None,
            "gross": 0.0,
            "mdr": 0.0,
            "trans_date": None,
            "channel": "other",
            "confidence": "derived",
            "note": None,
            "raw": payment_ref or "",
        }
        parsed.update(overrides)
        return parsed

    @api.model
    def _strip_noise(self, text):
        """A cash-deposit narrative reduced to the words that identify a store."""
        out = text or ""
        for pattern in _NOISE:
            out = pattern.sub(" ", out)
        return " ".join(out.split())

    @api.model
    def _day_month_date(self, day, month, statement_date):
        """A bare ``dd/mm`` resolved against the statement date's year."""
        if not statement_date:
            return None
        try:
            candidate = statement_date.replace(month=int(month), day=int(day))
        except ValueError:
            return None
        if (candidate - statement_date).days > _YEAR_ROLLBACK_DAYS:
            candidate -= relativedelta(years=1)
        return candidate

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    @api.model
    def parse(self, journal, payment_ref, amount, statement_date):
        """One statement line -> one parsed dict. Never raises, never returns None."""
        handler = getattr(self, "_parse_%s" % (journal.levis_clearing_format or "none"), None)
        if not handler:
            return self._blank(payment_ref, note="No narrative format set on journal %s" % journal.code)
        return handler(payment_ref or "", amount, statement_date) or self._blank(payment_ref)

    @api.model
    def _parse_none(self, payment_ref, amount, statement_date):
        return self._blank(payment_ref, note="Journal is not set up for narrative parsing")

    # ------------------------------------------------------------------
    # BCA
    # ------------------------------------------------------------------
    @api.model
    def _parse_bca(self, payment_ref, amount, statement_date):
        text = " ".join((payment_ref or "").split())
        upper = text.upper()

        gross_match = _BCA_GROSS.search(upper)
        if gross_match and _BCA_MID.search(upper):
            gross, gross_ok = self._num_en(gross_match.group(1))
            fee_match = _BCA_FEE.search(upper)
            mdr, mdr_ok = self._num_en(fee_match.group(1)) if fee_match else (0.0, True)
            if not (gross_ok and mdr_ok):
                return self._blank(payment_ref, note="Unreadable amount in settlement narrative")
            if re.search(r"QR\s*:", upper):
                channel = "qris"
            elif "KARTU KREDIT" in upper:
                channel = "credit"
            else:
                channel = "debit"
            tanggal = _BCA_TANGGAL.search(upper)
            trans_date = self._day_month_date(tanggal.group(1), tanggal.group(2), statement_date) if tanggal else None
            return self._blank(
                payment_ref,
                kind="settlement",
                mid=_BCA_MID.search(upper).group(1),
                gross=gross,
                mdr=mdr,
                trans_date=trans_date,
                channel=channel,
                confidence="exact" if trans_date else "derived",
            )

        # A debit sweep to the pooling account: money leaving the collection
        # account, not a settlement.
        if re.search(r"TRSF E-BANKING DB", upper) and "SWBCA" in upper:
            return self._blank(payment_ref, kind="sweep", gross=abs(amount or 0.0), channel="transfer")

        if re.search(r"^(BIAYA|ADM\b|PAJAK)", upper):
            return self._blank(payment_ref, kind="charge", gross=abs(amount or 0.0))

        if re.search(r"\bBUNGA\b", upper):
            return self._blank(payment_ref, kind="interest", gross=abs(amount or 0.0))

        if re.search(r"^(TRSF E-BANKING CR|SETORAN TUNAI|SETORAN VIA CDM|BI-FAST CR)", upper):
            return self._blank(
                payment_ref,
                kind="cash_deposit",
                keyword=self._strip_noise(text),
                gross=abs(amount or 0.0),
                channel="cash",
            )

        return self._blank(payment_ref, note="Unrecognised BCA narrative")

    # ------------------------------------------------------------------
    # BRI
    # ------------------------------------------------------------------
    @api.model
    def _parse_bri(self, payment_ref, amount, statement_date):
        text = " ".join((payment_ref or "").split())
        upper = text.upper()

        match = _BRI_SETTLE.search(text)
        if match:
            gross, gross_ok = self._num_id(match.group("gross"))
            mdr, mdr_ok = self._num_id(match.group("fee"))
            if not (gross_ok and mdr_ok):
                return self._blank(payment_ref, note="Unreadable amount in BRI settlement narrative")
            yymmdd = match.group("yymmdd")
            trans_date = None
            try:
                trans_date = statement_date.replace(
                    year=2000 + int(yymmdd[0:2]), month=int(yymmdd[2:4]), day=int(yymmdd[4:6])
                )
            except (ValueError, AttributeError):
                trans_date = None
            return self._blank(
                payment_ref,
                kind="settlement",
                tid=match.group("tid"),
                gross=gross,
                mdr=mdr,
                trans_date=trans_date,
                channel="qris" if match.group("qris") else "debit",
                confidence="exact" if trans_date else "derived",
            )

        if "INTEREST ON ACCOUNT" in upper:
            return self._blank(payment_ref, kind="interest", gross=abs(amount or 0.0))

        if re.search(r"^(TAX\b|METERAI|BUKU CEK|DEBET BY CEK|BIAYA)", upper):
            return self._blank(payment_ref, kind="charge", gross=abs(amount or 0.0))

        # Left unknown on purpose: a cheque clearing whose counterparty is not
        # stated. Booking it anywhere would hide a 1.5bn question.
        if "CAIR CEK" in upper:
            return self._blank(payment_ref, note="Cheque clearing — destination not stated in the narrative")

        return self._blank(payment_ref, note="Unrecognised BRI narrative")

    # ------------------------------------------------------------------
    # BNI / Mandiri — only fee and QR pass-through rows exist today
    # ------------------------------------------------------------------
    @api.model
    def _parse_bni(self, payment_ref, amount, statement_date):
        return self._parse_minor(payment_ref, amount)

    @api.model
    def _parse_mandiri(self, payment_ref, amount, statement_date):
        return self._parse_minor(payment_ref, amount)

    @api.model
    def _parse_minor(self, payment_ref, amount):
        upper = " ".join((payment_ref or "").split()).upper()
        if re.search(r"^(METERAI|BUKU CEK|BIAYA|ADM\b|PAJAK)", upper):
            return self._blank(payment_ref, kind="charge", gross=abs(amount or 0.0))
        return self._blank(payment_ref, note="No settlement grammar known for this feed")
