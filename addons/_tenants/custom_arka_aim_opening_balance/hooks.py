"""Post-init hook: create missing bank accounts and post the 31-May-2026 opening
balances for the AIM and ARKA companies.

Data lives in data/*.csv and is read directly by this hook (NOT loaded as ORM
records), because the target accounts are resolved by (company, code) at runtime
rather than by fixed external ids -- the two companies use different account
namespaces (AIM: arka_aim.coa_*, ARKA: account.2_erajaya_*) and this keeps the
module portable across the clone/UAT/prod databases.
"""

import csv
import logging
from datetime import date

from odoo.fields import Command
from odoo.exceptions import UserError
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

MODULE = "custom_arka_aim_opening_balance"
OPEN_DATE = date(2026, 5, 31)
REF = "Saldo Awal 31 Mei 2026"

# (company display name, opening-balance CSV) -- one posted move per company.
COMPANY_FILES = [
    ("PT Aero Inovasi Media", "data/opening_balance_aim.csv"),
    ("PT Aero Reksa Kreasi Angkasa", "data/opening_balance_arka.csv"),
]

_TRUE = {"1", "true", "yes", "t", "y"}


def _read_csv(relpath):
    with file_open(f"{MODULE}/{relpath}", "r") as fh:
        return list(csv.DictReader(fh))


def _resolve(env, code, company):
    """Find the single account with this code that belongs to `company`."""
    return (
        env["account.account"]
        .with_company(company)
        .search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    )


def _ensure_missing_accounts(env):
    Company = env["res.company"]
    for row in _read_csv("data/missing_accounts.csv"):
        company = Company.search([("name", "=", row["company_name"])], limit=1)
        if not company:
            _logger.warning(
                "opening_balance: company %r not found, skip account %s",
                row["company_name"], row["code"],
            )
            continue
        if _resolve(env, row["code"], company):
            continue
        env["account.account"].with_company(company).create({
            "code": row["code"],
            "name": row["name"],
            "account_type": row["account_type"],
            "reconcile": row["reconcile"].strip().lower() in _TRUE,
            "company_ids": [Command.link(company.id)],
        })
        _logger.info(
            "opening_balance: created account %s (%s) for %s",
            row["code"], row["account_type"], company.name,
        )


def _post_company_opening(env, company, relpath):
    Move = env["account.move"].with_company(company)
    existing = Move.search(
        [("ref", "=", REF), ("company_id", "=", company.id)], limit=1
    )
    if existing:
        _logger.info(
            "opening_balance: move %r already exists for %s (id=%s, state=%s) -> skip",
            REF, company.name, existing.id, existing.state,
        )
        return

    journal = (
        env["account.journal"]
        .with_company(company)
        .search([("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
    )
    if not journal:
        raise UserError(
            f"opening_balance: no general (Miscellaneous) journal for {company.name}"
        )

    lines, unresolved = [], []
    for row in _read_csv(relpath):
        acc = _resolve(env, row["code"], company)
        if not acc:
            unresolved.append(row["code"])
            continue
        lines.append(Command.create({
            "account_id": acc.id,
            "name": "Saldo Awal " + row["code"],
            "debit": float(row["debit"] or 0),
            "credit": float(row["credit"] or 0),
        }))
    if unresolved:
        raise UserError(
            f"opening_balance: unresolved account codes for {company.name}: {unresolved}"
        )

    move = Move.create({
        "move_type": "entry",
        "journal_id": journal.id,
        "date": OPEN_DATE,
        "ref": REF,
        "line_ids": lines,
    })
    move.action_post()
    total = sum(l[2]["debit"] for l in lines)
    _logger.info(
        "opening_balance: posted %s move id=%s lines=%s total=%.0f",
        company.name, move.id, len(lines), total,
    )


def post_init_hook(env):
    _ensure_missing_accounts(env)
    Company = env["res.company"]
    for company_name, relpath in COMPANY_FILES:
        company = Company.search([("name", "=", company_name)], limit=1)
        if not company:
            _logger.warning(
                "opening_balance: company %r not found, skip opening move", company_name
            )
            continue
        _post_company_opening(env, company, relpath)
    _logger.info("opening_balance: post_init_hook done")
