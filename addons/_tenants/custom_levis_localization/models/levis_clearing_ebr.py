# -*- coding: utf-8 -*-
"""``levis.clearing.ebr`` — the month's clearing, in the shape Finance already reads.

Finance reconciles the month in a workbook called EBR: one ``MUTASI`` sheet per
bank whose ``MID NO``, ``MDR``, ``AMOUNT PAYMENT``, ``Store code``, ``Store Name``
and ``STATUS`` columns are filled in by hand, a ``COMPILE SALES`` sheet of every
X70D tender line, an ``AR <month>`` sheet for last month's receivable collected
this month, and a ``SUMMARY``. The clearing computes nearly all of it already and
then keeps it on screen, which is why the workbook kept being rebuilt by hand.

This writes that workbook. Two things are deliberate:

* **It changes nothing.** No Compute, no projection rebuild, no receipt touched —
  a report that mutates the thing it reports is a report nobody can run twice.
  It reads a run that has already been computed.
* **The sheet the round trip needs is a separate one.** ``UNMAPPED`` carries
  exactly the lines Odoo could not place, with five input columns and a stable
  key, so the manual half of the month has somewhere to happen and somewhere to
  come back to (see ``levis.clearing.recon.upload``).

``COMPILE SALES`` is the slow half and the only slow half: the X70D feed is read
through a SQL view over staged JSON, which costs about a minute on a real month
where every other sheet is done in two seconds. It is a switch on the wizard for
that reason, not because the sheet is optional to the reconciliation.

The ``_META`` sheet is what makes the round trip safe: it names the run and
carries a token over ``(statement line, date, amount)``, so a file filled in
against figures that have since moved is recognised rather than applied.
"""

import hashlib
import io
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - the platform image ships xlsxwriter
    xlsxwriter = None

#: ``CASH IN/ATS`` in the client's vocabulary, per parsed narrative kind.
_CASH_IN_LABEL = {
    "settlement": "CASH IN",
    "cash_deposit": "CASH IN",
    "sweep": "ATS",
    "charge": "BIAYA ADMIN",
    "interest": "BUNGA",
}
#: ``METHOD`` in the client's vocabulary, per channel.
_METHOD_LABEL = {
    "debit": "DEBIT",
    "credit": "KREDIT",
    "qris": "QRIS",
    "cash": "CASH",
    "transfer": "TRANSFER",
}
#: ``STATUS`` in the client's vocabulary, per clearing line state.
_STATUS_LABEL = {
    "ok": "REKON DONE",
    "short": "SELISIH",
    "mismatch": "SELISIH NARASI",
    "skipped": "SKIP",
    "unmapped": "",
    "unparsed": "",
}
#: Lines that are the manual half of the month — the round-trip worksheet.
_NEEDS_A_PERSON = ("unmapped", "unparsed", "short", "mismatch", "skipped")

_BANK_TOKENS = ("BCA", "BRI", "BNI", "MANDIRI", "PERMATA", "CIMB")


class LevisClearingEbr(models.AbstractModel):
    _name = "levis.clearing.ebr"
    _description = "POS Clearing EBR Workbook"

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    def _build(self, run, options=None):
        """The whole workbook for one computed run, as bytes."""
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is not installed on this server."))
        if run.state == "draft":
            raise UserError(_("%s has not been computed yet, so there is nothing to report.", run.name))
        options = options or {}
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(
            stream, {"in_memory": True, "remove_timezone": True, "default_date_format": "yyyy-mm-dd"}
        )
        fmts = self._formats(book)
        stores = self._store_index(run.company_id)
        self._sheet_meta(book, fmts, run)
        self._sheet_summary(book, fmts, run, stores)
        taken = set()
        for journal in self._journals_with_lines(run):
            self._sheet_mutasi(book, fmts, run, journal, stores, taken)
        self._sheet_unmapped(book, fmts, run, stores, receipt_gaps=options.get("receipt_gaps", False))
        if options.get("compile_sales", True):
            self._sheet_compile_sales(book, fmts, run, stores)
        if options.get("ar_sheet", True):
            self._sheet_ar(book, fmts, run, stores)
        self._sheet_ref(book, fmts, run, stores)
        book.close()
        return stream.getvalue()

    def _filename(self, run):
        return "EBR_%s_%s.xlsx" % (
            (run.period_ref or "").replace("/", "-").replace(" ", "_") or "PERIODE",
            (run.name or "").replace("/", "-"),
        )

    def _action(self, run, options=None):
        """Build it, attach it, and hand the browser the download."""
        content = self._build(run, options=options)
        attachment = self.env["ir.attachment"].create(
            {
                "name": self._filename(run),
                "res_model": run._name,
                "res_id": run.id,
                "type": "binary",
                "raw": content,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    # The token — what makes a re-upload safe
    # ------------------------------------------------------------------
    def _token(self, run):
        """A fingerprint of the figures the workbook was written from.

        Not a checksum of the file: the file is *meant* to be edited. It is a
        checksum of what the file claims about the ledger, so an upload can tell
        "someone typed in the blanks" from "the run has been recomputed since".
        """
        digest = hashlib.sha256()
        for line in run.line_ids.sorted("id"):
            digest.update(
                ("%s:%s:%.2f|" % (line.statement_line_id.id, line.settlement_date, line.statement_amount)).encode()
            )
        return digest.hexdigest()[:32]

    # ------------------------------------------------------------------
    # Shared lookups
    # ------------------------------------------------------------------
    def _store_index(self, company):
        """``{analytic id: (store code, store name, short label)}``.

        The store code is the X24 code the client keys everything on; the short
        label is what the ``REMARKS`` column spells ("PVJ", "SENCY"), which only
        the warehouse knows.
        """
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id), ("l10n_ou_analytic_id", "!=", False)]
        )
        index = {}
        for warehouse in warehouses:
            index[warehouse.l10n_ou_analytic_id.id] = (
                warehouse.l10n_store_code or warehouse.code or "",
                warehouse.l10n_ou_analytic_id.name or warehouse.name,
                # The short label Finance writes ("BIP", "SENCY") lives nowhere
                # else, so REMARKS reads as the client's own only once
                # ``levis_ebr_label`` is filled — script 125 seeds it from their
                # workbook. Until then the store code is at least a number they
                # key on; the warehouse code (34885) is not.
                warehouse.levis_ebr_label or warehouse.l10n_store_code or warehouse.code or "",
            )
        return index

    def _tender_label(self, account, company):
        """``1106000102 — POS Receivable - OFFLINE_VISA``.

        A bare code names nothing to the person filling the sheet in: the ten
        receivables differ only in their last digits. The label carries both, and
        the upload reads the code off the front of it, so either form is accepted
        back.
        """
        code = account.with_company(company).code or ""
        name = account.name or ""
        return ("%s — %s" % (code, name)).strip(" —")

    def _bank_label(self, journal):
        """``BCA`` / ``BRI`` / … from the journal, for the sheet name and REMARKS."""
        haystack = " ".join(filter(None, [journal.name or "", journal.code or "", journal.bank_id.name or ""])).upper()
        for token in _BANK_TOKENS:
            if token in haystack:
                return token
        return (journal.code or journal.name or "BANK").upper()

    def _journals_with_lines(self, run):
        journals = run.line_ids.mapped("bank_journal_id")
        return journals.sorted(lambda j: (self._bank_label(j), j.code or ""))

    def _receipts_by_ref(self, run):
        """``{X24DN ref: clearing line}`` for every receipt a person or the amount ticked."""
        out = {}
        for receipt in run.receipt_ids.filtered("matched"):
            out[receipt.ref] = receipt.line_id
        return out

    # ------------------------------------------------------------------
    # Formats
    # ------------------------------------------------------------------
    def _formats(self, book):
        return {
            "title": book.add_format({"bold": True, "font_size": 13}),
            "header": book.add_format(
                {"bold": True, "bg_color": "#D9D9D9", "border": 1, "text_wrap": True, "valign": "vcenter"}
            ),
            "header_input": book.add_format(
                {"bold": True, "bg_color": "#FFF2CC", "border": 1, "text_wrap": True, "valign": "vcenter"}
            ),
            "text": book.add_format({"border": 1}),
            "input": book.add_format({"border": 1, "bg_color": "#FFFDF0"}),
            "num": book.add_format({"border": 1, "num_format": "#,##0.00"}),
            "int": book.add_format({"border": 1, "num_format": "#,##0"}),
            "date": book.add_format({"border": 1, "num_format": "yyyy-mm-dd"}),
            "total": book.add_format({"bold": True, "border": 1, "num_format": "#,##0.00", "bg_color": "#EDEDED"}),
            "total_text": book.add_format({"bold": True, "border": 1, "bg_color": "#EDEDED"}),
            "label": book.add_format({"bold": True}),
            "warn": book.add_format({"font_color": "#B00020", "bold": True}),
        }

    def _write_header(self, sheet, fmts, columns, row=0, input_from=None):
        for index, column in enumerate(columns):
            style = fmts["header_input"] if input_from is not None and index >= input_from else fmts["header"]
            sheet.write(row, index, column[0], style)
            sheet.set_column(index, index, column[1])
        sheet.freeze_panes(row + 1, 0)
        sheet.autofilter(row, 0, row, len(columns) - 1)
        return row + 1

    def _write_row(self, sheet, fmts, row, values, styles):
        for index, value in enumerate(values):
            style = fmts[styles[index]]
            # ``value in (None, False)`` would swallow 0.0 as well — and a zero
            # MDR is a real figure here, not a missing one: QRIS is fee-free.
            if value is None or value is False:
                sheet.write_blank(row, index, None, style)
            elif styles[index] == "date":
                sheet.write_datetime(row, index, value, style)
            else:
                sheet.write(row, index, value, style)
        return row + 1

    # ------------------------------------------------------------------
    # _META
    # ------------------------------------------------------------------
    def _sheet_meta(self, book, fmts, run):
        sheet = book.add_worksheet("_META")
        sheet.hide()
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 1, 52)
        rows = [
            ("key", "value"),
            ("model", "levis.pos.clearing"),
            ("run_id", run.id),
            ("run_name", run.name or ""),
            ("company_id", run.company_id.id),
            ("company", run.company_id.display_name),
            ("date_from", str(run.date_from or "")),
            ("date_to", str(run.date_to or "")),
            ("state", run.state),
            ("token", self._token(run)),
            ("exported_at", str(fields.Datetime.now())),
            ("exported_by", self.env.user.login),
            ("note", "Jangan ubah sheet ini. Odoo membacanya saat file diupload kembali."),
        ]
        for index, (key, value) in enumerate(rows):
            sheet.write(index, 0, key, fmts["label"] if index else fmts["header"])
            sheet.write(index, 1, value, fmts["header"] if not index else None)
        return sheet

    # ------------------------------------------------------------------
    # SUMMARY — bank, sales and the variance between them
    # ------------------------------------------------------------------
    def _sheet_summary(self, book, fmts, run, stores):
        sheet = book.add_worksheet("SUMMARY")
        sheet.write(0, 0, _("Store settlement reconciliation — %s", run.name or ""), fmts["title"])
        sheet.write(1, 0, "%s  %s .. %s" % (_("Period"), run.date_from, run.date_to))
        columns = [
            ("No", 5),
            ("Store code", 12),
            ("Store name", 34),
            ("Money in", 12),
            ("Trading day", 12),
            ("Sales X70D", 16),
            ("X70D card", 16),
            ("X70D cash", 16),
            ("Bank amount", 16),
            ("Gross", 16),
            ("MDR", 14),
            ("Allocated", 16),
            ("Short", 14),
            ("Variance", 16),
            ("Proof", 14),
            ("Status", 12),
        ]
        row = self._write_header(sheet, fmts, columns, row=3)
        styles = [
            "int",
            "text",
            "text",
            "date",
            "date",
            "num",
            "num",
            "num",
            "num",
            "num",
            "num",
            "num",
            "num",
            "num",
            "text",
            "text",
        ]
        totals = defaultdict(float)
        days = run.store_day_ids.sorted(lambda d: (d.settlement_date or run.date_from, d.analytic_account_id.id))
        if not days:
            sheet.write(
                row,
                0,
                _("No store settlement days on this run — press Store Reconcile on the run first."),
                fmts["warn"],
            )
            return sheet
        for number, day in enumerate(days, start=1):
            code, name, _label = stores.get(day.analytic_account_id.id, ("", day.analytic_account_id.name or "", ""))
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    number,
                    code,
                    name,
                    day.settlement_date,
                    day.trading_date,
                    day.x70d_total,
                    day.x70d_card_total,
                    day.x70d_cash_total,
                    day.statement_total,
                    day.gross_total,
                    day.mdr_total,
                    day.allocated_total,
                    day.short_total,
                    day.variance,
                    day.proof_state or "",
                    "TALLIES" if day.is_balanced else "CHECK",
                ],
                styles,
            )
            for key, value in (
                ("x70d", day.x70d_total),
                ("statement", day.statement_total),
                ("gross", day.gross_total),
                ("mdr", day.mdr_total),
                ("allocated", day.allocated_total),
                ("short", day.short_total),
                ("variance", day.variance),
            ):
                totals[key] += value
        sheet.write(row, 2, "TOTAL", fmts["total_text"])
        for index, key in (
            (5, "x70d"),
            (8, "statement"),
            (9, "gross"),
            (10, "mdr"),
            (11, "allocated"),
            (12, "short"),
            (13, "variance"),
        ):
            sheet.write(row, index, totals[key], fmts["total"])
        return sheet

    # ------------------------------------------------------------------
    # MUTASI <BANK> — the bank's own statement, read by Odoo
    # ------------------------------------------------------------------
    def _sheet_mutasi(self, book, fmts, run, journal, stores, taken=None):
        bank = self._bank_label(journal)
        # A company routinely keeps two journals on one bank — IBCA and OBCA are
        # both "BCA" — and xlsxwriter refuses a duplicate sheet name outright.
        taken = taken if taken is not None else set()
        title = ("MUTASI %s" % bank)[:31]
        if title in taken:
            title = ("MUTASI %s %s" % (bank, journal.code or journal.id))[:31]
        taken.add(title)
        sheet = book.add_worksheet(title)
        lines = run.line_ids.filtered(lambda line: line.bank_journal_id == journal).sorted(
            lambda line: (line.settlement_date, line.id)
        )
        columns = [
            ("Tanggal Transaksi", 14),
            ("Keterangan", 52),
            # Never filled: the bank's branch code is not on the imported line.
            # The column stays so the sheet's geometry matches the one Finance
            # has been pasting into for years.
            ("Cabang", 8),
            ("Jumlah", 16),
            ("CR/DB", 7),
            ("Saldo", 16),
            ("CASH IN/ATS", 13),
            ("METHOD", 10),
            ("MID NO", 16),
            ("MDR", 13),
            ("AMOUNT PAYMENT", 16),
            ("REMARKS", 22),
            ("Store code", 11),
            ("Store Name", 32),
            ("STATUS", 14),
            ("NOTES", 42),
            ("ADJ BANK", 12),
        ]
        # The client's own preamble, with the figures computed instead of typed.
        gross_total = sum(lines.mapped("gross"))
        mdr_total = sum(lines.mapped("mdr"))
        # Per the client's own sheet, each bank quotes the sales behind it. A
        # store-day that settled into two banks is therefore quoted on both
        # sheets; the label says so rather than inventing a split the feed does
        # not support.
        sales_total = sum(
            day.x70d_total for day in run.store_day_ids if journal in day.line_ids.mapped("bank_journal_id")
        )
        preamble = [
            ("SALES X70D (store-day ke bank ini)", sales_total),
            ("SALES PER BANK", gross_total),
            ("DIFF", round(sales_total - gross_total, 2)),
            ("MDR", mdr_total),
            ("ADJUSTMENT BANK", 0.0),
            ("ADJUSTMENT SALES", 0.0),
        ]
        for index, (label, value) in enumerate(preamble):
            sheet.write(index, 8, label, fmts["label"])
            sheet.write(index, 10, value, fmts["num"])
        row = self._write_header(sheet, fmts, columns, row=7)
        styles = [
            "date",
            "text",
            "text",
            "num",
            "text",
            "num",
            "text",
            "text",
            "text",
            "num",
            "num",
            "text",
            "text",
            "text",
            "text",
            "text",
            "input",
        ]
        balance = 0.0
        prev_month = self._previous_month_label(run)
        for line in lines:
            balance += line.statement_amount
            code, name, label = stores.get(line.analytic_account_id.id, ("", line.analytic_account_id.name or "", ""))
            note = line.note or ""
            if line.block == "b" and prev_month:
                note = ("COLLECTION AR %s. %s" % (prev_month, note)).strip()
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    line.settlement_date,
                    line.payment_ref or "",
                    None,
                    abs(line.statement_amount),
                    "CR" if line.statement_amount >= 0 else "DB",
                    round(balance, 2),
                    _CASH_IN_LABEL.get(line.kind, ""),
                    _METHOD_LABEL.get(line.channel, ""),
                    line.mid_key or line.tid_key or "",
                    line.mdr,
                    self._amount_payment(line),
                    ("%s CEK (%s)" % (label, bank)) if label else "",
                    code,
                    name,
                    _STATUS_LABEL.get(line.state, ""),
                    note,
                    None,
                ],
                styles,
            )
        sheet.write(row, 1, _("TOTAL — %s lines", len(lines)), fmts["total_text"])
        sheet.write(row, 3, sum(abs(line.statement_amount) for line in lines), fmts["total"])
        sheet.write(row, 9, mdr_total, fmts["total"])
        sheet.write(row, 10, gross_total, fmts["total"])
        return sheet

    def _amount_payment(self, line):
        """What the acquirer settled — blank on a line that is not takings.

        A cash deposit quotes no gross, so its own amount is the figure. A sweep
        to the main account or a bank charge is not takings at all, and giving it
        an AMOUNT PAYMENT would have the column footing to nearly twice the
        month: measured on August 2026, the ATS sweeps alone add Rp 12,47 miliar
        to a Rp 15,42 miliar month. The client's own sheet leaves those cells at
        zero for the same reason.
        """
        if line.kind not in ("settlement", "cash_deposit"):
            return None
        return line.gross or abs(line.statement_amount)

    def _previous_month_label(self, run):
        """``AUGUST 2026`` for a September run — the name the AR sheet carries."""
        if not run.date_from:
            return ""
        return (run.date_from.replace(day=1) - timedelta(days=1)).strftime("%B %Y").upper()

    # ------------------------------------------------------------------
    # UNMAPPED — the round-trip worksheet
    # ------------------------------------------------------------------
    def _sheet_unmapped(self, book, fmts, run, stores, receipt_gaps=False):
        sheet = book.add_worksheet("UNMAPPED")
        # What the sheet is for is a decision Odoo could not make: a store, a
        # tender, a receipt. A line that is mapped, allocated and merely has
        # receipts nobody has named yet is not that — on August 2026 those are
        # 831 of 920 rows, and putting them here buries the 89 that matter. They
        # are reachable on request, and in the in-app Receipt Matching worksheet
        # where ticking them one at a time is the point.
        lines = run.line_ids.filtered(
            lambda line: (
                line.state in _NEEDS_A_PERSON or line.x24_tender_mismatch or (receipt_gaps and line.match_gap > 0.005)
            )
        ).sorted(lambda line: (line.bank_journal_id.id, line.settlement_date, line.id))
        columns = [
            ("KEY", 10),
            ("BANK", 10),
            ("ENTRY", 20),
            ("TANGGAL", 12),
            ("NARASI", 52),
            ("AMOUNT", 16),
            ("GROSS", 16),
            ("MDR", 13),
            ("CHANNEL", 11),
            ("MID/TID", 16),
            ("KIND", 14),
            ("ALASAN", 46),
            ("STORE CODE", 13),
            ("SIMPAN RULE (Y/N)", 13),
            ("TENDER", 16),
            ("NO TRANSAKSI X24DN", 40),
            ("CATATAN", 32),
        ]
        sheet.write(
            0, 0, _("Isi lima kolom berkuning, lalu upload file ini kembali lewat Upload Recon."), fmts["title"]
        )
        sheet.write(
            1,
            0,
            _(
                "Jangan ubah kolom KEY, AMOUNT dan TANGGAL — Odoo memakainya untuk mengenali baris dan menolak file basi."
            ),
        )
        row = self._write_header(sheet, fmts, columns, row=3, input_from=12)
        first_data_row = row
        styles = [
            "int",
            "text",
            "text",
            "date",
            "text",
            "num",
            "num",
            "num",
            "text",
            "text",
            "text",
            "text",
            "input",
            "input",
            "input",
            "input",
            "input",
        ]
        for line in lines:
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    line.statement_line_id.id,
                    self._bank_label(line.bank_journal_id),
                    line.move_name or "",
                    line.settlement_date,
                    line.payment_ref or "",
                    line.statement_amount,
                    line.gross,
                    line.mdr,
                    line.channel or "",
                    line.mid_key or line.tid_key or "",
                    line.kind or "",
                    self._reason(line),
                    stores.get(line.analytic_account_id.id, ("", "", ""))[0],
                    None,
                    self._tender_label(line.manual_map_id.tender_account_id, run.company_id)
                    if line.manual_map_id.tender_account_id
                    else None,
                    line.manual_map_id.receipt_refs or None,
                    line.manual_map_id.note or None,
                ],
                styles,
            )
        last = max(row - 1, first_data_row)
        # Dropdowns rather than free text: a store code typed from memory is the
        # single most common way a round trip comes back unusable.
        sheet.data_validation(
            first_data_row, 12, last, 12, {"validate": "list", "source": "=REF_STORES", "ignore_blank": True}
        )
        sheet.data_validation(
            first_data_row, 13, last, 13, {"validate": "list", "source": ["Y", "N"], "ignore_blank": True}
        )
        sheet.data_validation(
            first_data_row, 14, last, 14, {"validate": "list", "source": "=REF_TENDERS", "ignore_blank": True}
        )
        return sheet

    def _reason(self, line):
        if line.state == "unmapped":
            return _("No store mapping for this MID / terminal / wording.")
        if line.state == "unparsed":
            return _("The narrative could not be read.")
        if line.state == "short":
            return _(
                "Short by %(amount)s — no open receivable explains it.", amount="{:,.2f}".format(line.short_amount)
            )
        if line.state == "mismatch":
            return _("Bank amount disagrees with gross minus MDR.")
        if line.x24_tender_mismatch:
            return _("The receipts name %s, the allocation credited another tender.", line.x24_tender or "")
        if line.match_gap > 0.005:
            return _("%s still unmatched by named transactions.", "{:,.2f}".format(line.match_gap))
        return line.note or ""

    # ------------------------------------------------------------------
    # COMPILE SALES — the tender side
    # ------------------------------------------------------------------
    def _trading_window(self, run):
        """The trading days this period's money belongs to — ``(from, to)``.

        Money that lands on 1 September pays the day the store traded, which is
        one settlement lag earlier: 31 August. Filtering the sales side on the
        run's own dates therefore reports the wrong days at both ends — it drops
        the 31 August takings the period actually settles and adds the last day's
        takings, which will not be paid until the next period. The lag is the
        same ``settlement_lag_days`` the allocation anchors on
        (``_resolve_target``), so the two sides cannot drift apart.
        """
        lag = timedelta(days=(run.config_id.settlement_lag_days or 0))
        return run.date_from - lag, run.date_to - lag

    def _sheet_compile_sales(self, book, fmts, run, stores):
        sheet = book.add_worksheet("COMPILE SALES")
        columns = [
            ("NO", 6),
            ("STORE CODE", 11),
            ("SAP STORE CODE", 15),
            ("STORE NAME", 30),
            ("TRANS DATE", 12),
            ("REGISTER", 9),
            ("TRANSNUM", 10),
            ("CASHIER LOGIN ID", 15),
            ("CASHIER NAME", 20),
            ("TENDER TYPE", 24),
            ("TENDER AMOUNT", 16),
            ("METODE PEMBAYARAN", 22),
            ("APPROVAL CODE", 16),
            ("VOUCHER NUMBER", 16),
            ("CEK BANK", 10),
            ("STATUS", 22),
            ("CASH RECEIVED DATE", 16),
        ]
        sales_from, sales_to = self._trading_window(run)
        sheet.write(
            0,
            0,
            _(
                "Trading days %s .. %s — the days this period's settlements pay, one "
                "settlement lag before the bank dates.",
                sales_from,
                sales_to,
            ),
        )
        sheet.write(
            1,
            0,
            _("CASHIER and METODE PEMBAYARAN are not in the X70D feed — they stay blank here on purpose."),
        )
        row = self._write_header(sheet, fmts, columns, row=3)
        styles = [
            "int",
            "text",
            "text",
            "text",
            "date",
            "text",
            "text",
            "text",
            "text",
            "text",
            "num",
            "text",
            "text",
            "text",
            "text",
            "text",
            "date",
        ]
        by_ref = self._receipts_by_ref(run)
        # ``search_read`` rather than a recordset: ``levis.pos.x70d.txn`` is a SQL
        # view over the staged JSON, so every prefetch batch re-runs the whole
        # scan. Measured on prd_levis_begbal September 2026 — 3.491 rows — that
        # was 74 of the export's 89 seconds. One query instead.
        txns = self.env["levis.pos.x70d.txn"].search_read(
            [
                ("company_id", "=", run.company_id.id),
                ("trans_date", ">=", sales_from),
                ("trans_date", "<=", sales_to),
            ],
            [
                "ref",
                "store_code",
                "sap_store_code",
                "store_name",
                "trans_date",
                "register",
                "transnum",
                "tender",
                "auth",
                "voucher",
                "amount",
            ],
            order="trans_date, store_code, transnum",
        )
        total = 0.0
        for number, txn in enumerate(txns, start=1):
            line = by_ref.get(txn["ref"])
            _code, _name, label = stores.get(line.analytic_account_id.id, ("", "", "")) if line else ("", "", "")
            bank = self._bank_label(line.bank_journal_id) if line else ""
            total += txn["amount"] or 0.0
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    number,
                    txn["store_code"] or "",
                    txn["sap_store_code"] or "",
                    txn["store_name"] or "",
                    txn["trans_date"],
                    txn["register"] or "",
                    txn["transnum"] or "",
                    None,
                    None,
                    txn["tender"] or "",
                    txn["amount"],
                    None,
                    txn["auth"] or "",
                    txn["voucher"] or "",
                    bank,
                    ("%s CEK (%s)" % (label, bank)) if label and bank else "",
                    line.settlement_date if line else None,
                ],
                styles,
            )
        sheet.write(row, 9, _("TOTAL"), fmts["total_text"])
        sheet.write(row, 10, total, fmts["total"])
        return sheet

    # ------------------------------------------------------------------
    # AR <previous month> — last month's receivable, and what collected it
    # ------------------------------------------------------------------
    def _sheet_ar(self, book, fmts, run, stores):
        label = self._previous_month_label(run)
        sheet = book.add_worksheet(("AR %s" % label)[:31] if label else "AR")
        columns = [
            ("NO", 6),
            ("STORE CODE", 11),
            ("STORE NAME", 30),
            ("TRANS DATE", 12),
            ("TENDER ACCOUNT", 34),
            ("NO TRANSAKSI", 40),
            ("ENTRY", 20),
            ("AMOUNT", 16),
            ("MID", 16),
            ("MUTASI BANK", 16),
            ("MDR", 13),
            ("DIFFERENT", 14),
            ("STATUS", 12),
            ("CASH RECEIVED DATE", 16),
        ]
        row = self._write_header(sheet, fmts, columns, row=1)
        styles = [
            "int",
            "text",
            "text",
            "date",
            "text",
            "text",
            "text",
            "num",
            "text",
            "num",
            "num",
            "num",
            "text",
            "date",
        ]
        number = 0
        collected_amls = set()
        open_amls = self._open_prior_receivables(run)
        receipts_for = self._ar_receipts(run, open_amls)
        # What this run collected out of a receivable older than the period.
        allocs = run.line_ids.mapped("alloc_ids").filtered(
            lambda alloc: alloc.source_date and run.date_from and alloc.source_date < run.date_from
        )
        for alloc in allocs.sorted(lambda a: (a.source_date, a.id)):
            line = alloc.line_id
            collected_amls.add(alloc.source_aml_id.id)
            code, name, _lbl = stores.get(line.analytic_account_id.id, ("", line.analytic_account_id.name or "", ""))
            number += 1
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    number,
                    code,
                    name,
                    alloc.source_date,
                    alloc.account_id.display_name,
                    # The receipts the settling bank line names. They belong to
                    # the whole line rather than to this one leg, which is why
                    # the column is headed by the transaction numbers and not by
                    # a claim that these are the ones this leg paid.
                    line.x24_trans_refs or "",
                    line.move_name or "",
                    alloc.amount,
                    line.mid_key or line.tid_key or "",
                    line.statement_amount,
                    line.mdr_booked,
                    round(alloc.amount - line.statement_amount, 2),
                    "REKON",
                    line.settlement_date,
                ],
                styles,
            )
        # And what is still sitting there, uncollected, at the end of the period.
        for aml in open_amls:
            if aml.id in collected_amls:
                continue
            analytic = self._aml_analytic(aml)
            code, name, _lbl = stores.get(analytic, ("", "", ""))
            number += 1
            row = self._write_row(
                sheet,
                fmts,
                row,
                [
                    number,
                    code,
                    name,
                    aml.date,
                    aml.account_id.display_name,
                    receipts_for(analytic, aml.date, aml.account_id),
                    aml.move_id.name or "",
                    aml.amount_residual,
                    None,
                    None,
                    None,
                    None,
                    "AR",
                    None,
                ],
                styles,
            )
        return sheet

    def _ar_receipts(self, run, amls):
        """``f(store, day, account) -> "80435-1-1868, 80435-1-1869 (+31)"``.

        An open POS receivable is one X70D transfer line per store, per trading
        day, per tender, so it carries no transaction number at all — the numbers
        live in the staged X70D rows. This reads them once for every day the
        sheet will show and hands back the ones that match a row's own tender,
        which is the only thing that makes an AR line chaseable back to a till.

        A day can hold hundreds of transactions, so the cell lists the first ten
        and counts the rest rather than becoming unreadable.
        """
        if not amls:
            return lambda analytic, day, account: ""
        analytic_ids = {self._aml_analytic(aml) for aml in amls}
        analytic_ids.discard(False)
        dates = amls.mapped("date")
        if not analytic_ids or not dates:
            return lambda analytic, day, account: ""
        rows = self.env["levis.pos.clearing.alloc"]._x24_rows(analytic_ids, min(dates), max(dates), run.company_id)
        Alloc = self.env["levis.pos.clearing.alloc"]

        def lookup(analytic, day, account):
            if not analytic or not day:
                return ""
            wanted = Alloc._x24_tender_of_account(account)
            refs = [ref for tender, ref, _amount in rows.get((analytic, day), ()) if not wanted or tender == wanted]
            if not refs:
                return ""
            if len(refs) <= 10:
                return ", ".join(refs)
            return "%s (+%d)" % (", ".join(refs[:10]), len(refs) - 10)

        return lookup

    def _open_prior_receivables(self, run):
        config = run.config_id or self.env["levis.clearing.config"].search(
            [("company_id", "=", run.company_id.id)], limit=1
        )
        accounts = config.pos_receivable_account_ids
        if not accounts or not run.date_from:
            return self.env["account.move.line"]
        return self.env["account.move.line"].search(
            [
                ("company_id", "=", run.company_id.id),
                ("account_id", "in", accounts.ids),
                ("date", "<", run.date_from),
                ("parent_state", "=", "posted"),
                ("full_reconcile_id", "=", False),
                ("balance", ">", 0),
            ],
            order="date, id",
        )

    def _aml_analytic(self, aml):
        distribution = aml.analytic_distribution or {}
        for key in distribution:
            for part in str(key).split(","):
                if part.isdigit():
                    return int(part)
        return False

    # ------------------------------------------------------------------
    # REF — the lists the dropdowns point at (the client's ``Sheet2``, generated)
    # ------------------------------------------------------------------
    def _sheet_ref(self, book, fmts, run, stores):
        sheet = book.add_worksheet("REF")
        sheet.hide()
        columns = [("STORE CODE", 12), ("STORE NAME", 32), ("LABEL", 14), ("ANALYTIC ID", 12)]
        row = self._write_header(sheet, fmts, columns, row=0)
        codes = []
        for analytic_id, (code, name, label) in sorted(stores.items(), key=lambda item: item[1][0]):
            if not code:
                continue
            codes.append(code)
            row = self._write_row(sheet, fmts, row, [code, name, label, analytic_id], ["text", "text", "text", "int"])
        if codes:
            book.define_name("REF_STORES", "=REF!$A$2:$A$%s" % (len(codes) + 1))

        config = run.config_id or self.env["levis.clearing.config"].search(
            [("company_id", "=", run.company_id.id)], limit=1
        )
        accounts = config._pos_accounts_sorted() if config else self.env["account.account"]
        start = row + 2
        sheet.write(start - 1, 5, "TENDER (pilihan)", fmts["header"])
        sheet.write(start - 1, 6, "CODE", fmts["header"])
        sheet.write(start - 1, 7, "NAME", fmts["header"])
        sheet.set_column(5, 5, 46)
        sheet.set_column(6, 6, 16)
        sheet.set_column(7, 7, 34)
        for index, account in enumerate(accounts):
            sheet.write(start + index, 5, self._tender_label(account, run.company_id), fmts["text"])
            sheet.write(start + index, 6, account.with_company(run.company_id).code or "", fmts["text"])
            sheet.write(start + index, 7, account.name or "", fmts["text"])
        if accounts:
            book.define_name("REF_TENDERS", "=REF!$F$%s:$F$%s" % (start + 1, start + len(accounts)))

        # The client's Sheet2 in generated form: every mapping rule that resolves
        # a store today, so the person filling in the blanks can see what Odoo
        # already knows before inventing a new rule.
        rules = self.env["levis.bank.mid.map"].search([("company_id", "=", run.company_id.id)])
        head = start + len(accounts) + 2
        for index, title in enumerate(["BANK", "MATCH", "KEY", "STORE"]):
            sheet.write(head, 8 + index, title, fmts["header"])
            sheet.set_column(8 + index, 8 + index, 18)
        for index, rule in enumerate(rules, start=1):
            sheet.write(head + index, 8, self._bank_label(rule.journal_id) if rule.journal_id else "", fmts["text"])
            sheet.write(head + index, 9, rule.match_type or "", fmts["text"])
            sheet.write(head + index, 10, rule.key or "", fmts["text"])
            sheet.write(head + index, 11, rule.analytic_account_id.display_name or "", fmts["text"])
        return sheet
