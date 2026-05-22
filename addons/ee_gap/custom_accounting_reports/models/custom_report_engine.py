# -*- coding: utf-8 -*-
"""Shared abstract engine for every Custom Platform financial report.

A concrete report subclasses :class:`CustomReportEngine` and overrides
``_report_code`` / ``_report_title`` / ``_build_lines(filters)``.

The engine provides three responsibilities:

1.  **Filter normalisation** — coerce wizard input into a uniform
    ``filters`` dict every sub-report can rely on.
2.  **Raw-SQL aggregation** — high-throughput helpers
    (``_get_account_balances``, ``_get_move_lines_query``,
    ``_sum_by_account``) that read ``account_move_line`` once per
    report, parameterised, never string-concatenated.
3.  **Render context** — common header metadata + audit logging
    via :py:meth:`_log_report_run` (writes to ``pdp.audit_log``).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from odoo import _, models
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)


class CustomReportEngine(models.AbstractModel):
    """Abstract base for every ``custom.report.*`` model."""

    _name = "custom.report.engine"
    _description = "Custom Report Engine (Abstract Base)"

    # Subclasses MUST override these two.
    _report_code = None
    _report_title = None

    # ------------------------------------------------------------------
    # Filter defaults & normalisation
    # ------------------------------------------------------------------
    def _default_filters(self):
        """Return a fully-populated default filter dict.

        Keys:
            * ``date_from`` (``date``) — fiscal-year start by default.
            * ``date_to`` (``date``) — today by default.
            * ``company_ids`` (``list[int]``).
            * ``journal_ids`` (``list[int]``).
            * ``account_ids`` (``list[int]``).
            * ``partner_ids`` (``list[int]``).
            * ``posted_only`` (``bool``).
            * ``comparison`` (``bool``) plus matching comparison dates.
        """
        today = date.today()
        return {
            "date_from": today.replace(month=1, day=1),
            "date_to": today,
            "company_ids": list(self.env.companies.ids),
            "journal_ids": [],
            "account_ids": [],
            "partner_ids": [],
            "posted_only": True,
            "comparison": False,
            "comparison_date_from": None,
            "comparison_date_to": None,
        }

    def _get_query_filters(self, wizard):
        """Build a normalised filter dict from a wizard record.

        ``wizard`` is any record exposing the standard wizard fields
        (date_from, date_to, company_ids, journal_ids, partner_ids,
        posted_only). Missing fields fall back to engine defaults.
        """
        defaults = self._default_filters()
        if not wizard:
            return defaults
        getf = lambda name, default: (  # noqa: E731
            getattr(wizard, name, default) if hasattr(wizard, name) else default
        )
        filters = dict(defaults)
        filters["date_from"] = getf("date_from", defaults["date_from"])
        filters["date_to"] = getf("date_to", defaults["date_to"])
        company_ids = getf("company_ids", False)
        if company_ids:
            filters["company_ids"] = list(company_ids.ids)
        journal_ids = getf("journal_ids", False)
        if journal_ids:
            filters["journal_ids"] = list(journal_ids.ids)
        partner_ids = getf("partner_ids", False)
        if partner_ids:
            filters["partner_ids"] = list(partner_ids.ids)
        account_ids = getf("account_ids", False)
        if account_ids:
            filters["account_ids"] = list(account_ids.ids)
        posted_only = getf("posted_only", None)
        if posted_only is not None:
            filters["posted_only"] = bool(posted_only)
        return self._get_context_filters(filters)

    def _get_context_filters(self, filters=None):
        """Merge caller-supplied ``filters`` over defaults.

        Coerces string dates → ``date``; ensures ``date_from <= date_to``;
        materialises a comparison-period when ``comparison`` is set.
        """
        merged = self._default_filters()
        for key, value in (filters or {}).items():
            if value in (None, "", False) and key not in (
                "posted_only",
                "comparison",
            ):
                continue
            merged[key] = value

        for key in (
            "date_from",
            "date_to",
            "comparison_date_from",
            "comparison_date_to",
        ):
            value = merged.get(key)
            if isinstance(value, str) and value:
                merged[key] = date.fromisoformat(value)

        if merged["date_from"] and merged["date_to"] and (merged["date_from"] > merged["date_to"]):
            merged["date_from"], merged["date_to"] = (
                merged["date_to"],
                merged["date_from"],
            )

        if merged.get("comparison") and not merged.get("comparison_date_from"):
            span = (merged["date_to"] - merged["date_from"]).days + 1
            merged["comparison_date_to"] = merged["date_from"] - timedelta(days=1)
            merged["comparison_date_from"] = merged["comparison_date_to"] - timedelta(days=span - 1)

        # company_ids must always be a non-empty list — fall back to
        # current company so SQL ``IN ()`` cannot crash.
        if not merged.get("company_ids"):
            merged["company_ids"] = [self.env.company.id]

        return merged

    # ------------------------------------------------------------------
    # ORM domain helper (kept for sub-reports that need ORM iteration)
    # ------------------------------------------------------------------
    def _base_move_line_domain(self, filters):
        """ORM domain for ``account.move.line`` honouring ``filters``."""
        domain = [
            ("date", ">=", filters["date_from"]),
            ("date", "<=", filters["date_to"]),
            ("company_id", "in", list(filters["company_ids"])),
        ]
        if filters.get("posted_only", True):
            domain.append(("parent_state", "=", "posted"))
        else:
            domain.append(("parent_state", "in", ("draft", "posted")))
        if filters.get("journal_ids"):
            domain.append(("journal_id", "in", list(filters["journal_ids"])))
        if filters.get("account_ids"):
            domain.append(("account_id", "in", list(filters["account_ids"])))
        if filters.get("partner_ids"):
            domain.append(("partner_id", "in", list(filters["partner_ids"])))
        return domain

    # ------------------------------------------------------------------
    # Raw SQL helpers — parameterised, never string-concatenated
    # ------------------------------------------------------------------
    def _get_move_lines_query(self, filters):
        """Return ``(query, params)`` selecting move-line rows.

        Subclasses may wrap this in their own aggregation. We rely on
        ``parent_state`` so the filter applies without an explicit JOIN.
        """
        params = [
            filters["date_from"],
            filters["date_to"],
            tuple(filters["company_ids"]) or (0,),
        ]
        query = """
            SELECT aml.id,
                   aml.account_id,
                   aml.partner_id,
                   aml.journal_id,
                   aml.move_id,
                   aml.date,
                   aml.name,
                   aml.ref,
                   aml.debit,
                   aml.credit,
                   aml.balance,
                   aml.amount_residual,
                   aml.date_maturity,
                   aml.company_id,
                   aml.parent_state
            FROM account_move_line aml
            WHERE aml.date >= %s
              AND aml.date <= %s
              AND aml.company_id IN %s
        """
        if filters.get("posted_only", True):
            query += " AND aml.parent_state = %s"
            params.append("posted")
        else:
            query += " AND aml.parent_state IN %s"
            params.append(("draft", "posted"))

        if filters.get("journal_ids"):
            query += " AND aml.journal_id IN %s"
            params.append(tuple(filters["journal_ids"]))
        if filters.get("account_ids"):
            query += " AND aml.account_id IN %s"
            params.append(tuple(filters["account_ids"]))
        if filters.get("partner_ids"):
            query += " AND aml.partner_id IN %s"
            params.append(tuple(filters["partner_ids"]))

        query += " ORDER BY aml.account_id, aml.date, aml.id"
        return query, tuple(params)

    def _get_account_balances(
        self,
        date_from=None,
        date_to=None,
        company_ids=None,
        journal_ids=None,
        *,
        filters=None,
    ):
        """Aggregate debit/credit/balance per account for the period.

        Three call shapes are accepted:

        * ``_get_account_balances(filters_dict)`` — pass the whole
          filter envelope as the single positional argument. Used by
          every concrete sub-report in this module.
        * ``_get_account_balances(date_from, date_to, company_ids,
          journal_ids)`` — positional, matches the spec.
        * ``_get_account_balances(filters=filters_dict)`` — keyword.

        Returns ``{account_id: {'account_id', 'account_code',
        'account_name', 'account_type', 'debit', 'credit', 'balance'}}``.
        """
        # Auto-detect the "single dict" shape so sub-reports can stay
        # terse: ``self._get_account_balances(filters)``.
        if filters is None and isinstance(date_from, dict):
            filters = date_from
        if filters is None:
            filters = self._get_context_filters(
                {
                    "date_from": date_from,
                    "date_to": date_to,
                    "company_ids": company_ids,
                    "journal_ids": journal_ids or [],
                }
            )
        return self._sum_by_account(filters)

    def _sum_by_account(self, filters, account_domain=None):
        """Raw-SQL per-account aggregation. Hot path for TB / GL / BS.

        ``account_domain`` is an optional extra ORM domain restricting
        the account set (resolved via a fast ``account.account`` search).
        """
        params = [
            filters["date_from"],
            filters["date_to"],
            tuple(filters["company_ids"]) or (0,),
        ]
        sql = """
            SELECT aml.account_id,
                   acc.code AS account_code,
                   acc.name AS account_name,
                   acc.account_type AS account_type,
                   COALESCE(SUM(aml.debit), 0.0) AS debit,
                   COALESCE(SUM(aml.credit), 0.0) AS credit,
                   COALESCE(SUM(aml.balance), 0.0) AS balance
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             WHERE aml.date >= %s
               AND aml.date <= %s
               AND aml.company_id IN %s
        """
        if filters.get("posted_only", True):
            sql += " AND aml.parent_state = %s"
            params.append("posted")
        else:
            sql += " AND aml.parent_state IN %s"
            params.append(("draft", "posted"))

        if filters.get("journal_ids"):
            sql += " AND aml.journal_id IN %s"
            params.append(tuple(filters["journal_ids"]))
        if filters.get("account_ids"):
            sql += " AND aml.account_id IN %s"
            params.append(tuple(filters["account_ids"]))
        if filters.get("partner_ids"):
            sql += " AND aml.partner_id IN %s"
            params.append(tuple(filters["partner_ids"]))

        if account_domain:
            account_ids = self.env["account.account"].search(account_domain).ids
            if not account_ids:
                return {}
            sql += " AND aml.account_id IN %s"
            params.append(tuple(account_ids))

        sql += """
            GROUP BY aml.account_id, acc.code, acc.name, acc.account_type
            ORDER BY acc.code
        """
        self.env.cr.execute(sql, tuple(params))
        result = {}
        for row in self.env.cr.dictfetchall():
            result[row["account_id"]] = {
                "account_id": row["account_id"],
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "account_type": row["account_type"],
                "debit": row["debit"] or 0.0,
                "credit": row["credit"] or 0.0,
                "balance": row["balance"] or 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # Render-context helpers
    # ------------------------------------------------------------------
    def _get_company_currency(self, filters=None):
        filters = filters or {}
        if filters.get("company_ids"):
            company = self.env["res.company"].browse(filters["company_ids"][0])
            if company.exists():
                return company.currency_id
        return self.env.company.currency_id

    def _format_amount(self, value, currency=None):
        """Locale-aware monetary formatting.

        Falls back to a plain two-decimal string if no currency.
        """
        if currency is None:
            currency = self._get_company_currency()
        value = value or 0.0
        if currency:
            rounded = currency.round(value)
            symbol = currency.symbol or ""
            position = currency.position or "before"
            formatted = f"{rounded:,.{currency.decimal_places}f}"
            if position == "before":
                return f"{symbol} {formatted}".strip()
            return f"{formatted} {symbol}".strip()
        return f"{value:,.2f}"

    def _format_date_id(self, value):
        """Format ``value`` as Indonesian ``dd/mm/yyyy``."""
        if not value:
            return ""
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                return value
        return value.strftime("%d/%m/%Y")

    def _coverage_banner(self, filters):
        """Header row consumed by QWeb templates."""
        return [
            {
                "type": "coverage",
                "date_from": filters["date_from"],
                "date_to": filters["date_to"],
                "date_from_str": self._format_date_id(filters["date_from"]),
                "date_to_str": self._format_date_id(filters["date_to"]),
                "posted_only": filters.get("posted_only", True),
            }
        ]

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    def _build_lines(self, filters):
        raise NotImplementedError(
            _(
                "Report %(code)s must override _build_lines().",
                code=self._report_code or self._name,
            )
        )

    def _compute(self, filters=None):
        """Public entry point used by wizards.

        Returns the render context dict (header metadata + lines).
        Also writes a PDP audit row so we know who ran which report.
        """
        filters = self._get_context_filters(filters)
        companies = self.env["res.company"].browse(filters["company_ids"])
        currency = self._get_company_currency(filters)
        lines = self._build_lines(filters)
        self._log_report_run(filters)
        return {
            "report_code": self._report_code,
            "report_title": self._report_title or self._name,
            "filters": filters,
            "options": filters,
            "lines": lines,
            "company_names": ", ".join(companies.mapped("name")),
            "currency": currency,
            "date_from": filters["date_from"],
            "date_to": filters["date_to"],
            "date_from_str": format_date(self.env, filters["date_from"]),
            "date_to_str": format_date(self.env, filters["date_to"]),
            "date_from_id": self._format_date_id(filters["date_from"]),
            "date_to_id": self._format_date_id(filters["date_to"]),
        }

    # ------------------------------------------------------------------
    # PDP audit hook — record every report run
    # ------------------------------------------------------------------
    def _log_report_run(self, filters):
        """Insert a row into ``pdp.audit_log`` (best-effort).

        Mirrors the raw-SQL pattern used by ``pdp.audited.mixin``. Never
        raises — a logging failure must not abort the report.
        """
        try:
            user = self.env.user
            payload = {
                "report_code": self._report_code,
                "report_title": self._report_title,
                "date_from": (filters["date_from"].isoformat() if filters.get("date_from") else None),
                "date_to": (filters["date_to"].isoformat() if filters.get("date_to") else None),
                "company_ids": list(filters.get("company_ids") or []),
                "journal_ids": list(filters.get("journal_ids") or []),
                "partner_ids": list(filters.get("partner_ids") or []),
                "posted_only": bool(filters.get("posted_only", True)),
            }
            self.env.cr.execute(
                """
                INSERT INTO pdp.audit_log (
                    actor_user_id, actor_login, tenant_db,
                    model_name, res_id, action,
                    field_changes, classification,
                    ip_address, user_agent, request_id, reason
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                    NULL, NULL, NULL, %s
                )
                """,
                (
                    user.id if user else None,
                    user.login if user else None,
                    self.env.cr.dbname,
                    self._name,
                    None,
                    "export",
                    json.dumps(payload, default=str),
                    "financial",
                    "Report run: %s" % (self._report_title or self._name),
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning(
                "custom_accounting_reports: PDP audit log skipped for %s: %s",
                self._name,
                exc,
            )
