"""Replace the aggregate ARKA/AIM opening balance with the per-transaction detail.

Tenant: PT Aero Inovasi Media (company 1) + PT Aero Reksa Kreasi Angkasa
(company 2). DBs: ``trn_arkaaim_begbal`` (test) then ``prd_arkaaim`` (prod).

Background: the opening balance was first posted as two aggregate moves, one
line per TB account, ref "Saldo Awal 31 Mei 2026". The client's "TB & Detail"
workbook carries the same trial balance with the underlying transactions, so
this script swaps the aggregate moves for detail moves. Balances do not change
-- only their granularity. Every line stays dated 31-May-2026 (the cutover);
each line label keeps the original transaction date and document number.

Input CSVs are produced by ``tools/parse_arkaaim_begbal_detail.py`` and live in
``addons/_tenants/custom_arka_aim_opening_balance/data/``.

Run inside the Odoo container::

    odoo shell -d trn_arkaaim_begbal --no-http < scripts/tenants/arkaaim/load_begbal_detail.py

Dry run by default. Set ``BEGBAL_REPLACE=1`` to actually delete the aggregate
moves and post the detail ones.
"""

import csv
import logging
import os

from odoo.fields import Command

# Account/journal resolution and the move's identity live in the module, so a
# fresh install and this replacement cannot drift apart.
from odoo.addons.custom_arka_aim_opening_balance.hooks import (
    LEGACY_REF as OLD_REF,
    OPEN_DATE,
    REF as NEW_REF,
    _general_journal,
    _resolve as _resolve_module_account,
)

_logger = logging.getLogger(__name__)
# Defaults to the module's data dir as mounted in the container; override with
# BEGBAL_DATA_DIR to test CSVs that have not been copied to /opt yet.
DATA_DIR = os.environ.get(
    "BEGBAL_DATA_DIR", "/mnt/extra-addons/_tenants/custom_arka_aim_opening_balance/data"
)

COMPANIES = [
    ("PT Aero Inovasi Media", "opening_detail_aim.csv"),
    ("PT Aero Reksa Kreasi Angkasa", "opening_detail_arka.csv"),
]

REPLACE = os.environ.get("BEGBAL_REPLACE") == "1"


def _partner_cache(env):
    cache = {}

    def resolve(name):
        if not name:
            return False
        key = name.strip().lower()
        if key not in cache:
            partner = env["res.partner"].search([("name", "=ilike", name.strip())], limit=1)
            cache[key] = partner.id if partner else False
        return cache[key]

    return resolve


def _load_company(env, company_name, filename, resolve_partner):
    company = env["res.company"].search([("name", "=", company_name)], limit=1)
    if not company:
        _logger.error("begbal_detail: company %r not found", company_name)
        return False

    Move = env["account.move"].with_company(company)
    if Move.search([("ref", "=", NEW_REF), ("company_id", "=", company.id)], limit=1):
        _logger.info("begbal_detail: %s already has %r -> skip", company.name, NEW_REF)
        return True

    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    lines, unresolved, missing_partners = [], set(), set()
    debit_total = credit_total = 0.0
    for row in rows:
        account = _resolve_module_account(env, row["code"], company)
        if not account:
            unresolved.add(row["code"])
            continue
        partner_id = resolve_partner(row.get("partner"))
        if row.get("partner") and not partner_id:
            missing_partners.add(row["partner"].strip())
        debit, credit = float(row["debit"] or 0), float(row["credit"] or 0)
        debit_total += debit
        credit_total += credit
        # The label carries the original transaction date, document number and
        # counterparty, because an account.move.line has no date of its own and
        # not every "Company BP" name matches a partner record.
        label = " | ".join(
            part for part in (row["txn_date"], row["doc_no"], row["notes"], row.get("partner")) if part
        )
        lines.append(
            Command.create(
                {
                    "account_id": account.id,
                    "name": label[:500] or f"Saldo Awal {row['code']}",
                    "partner_id": partner_id,
                    "debit": debit,
                    "credit": credit,
                }
            )
        )

    if unresolved:
        _logger.error("begbal_detail: %s unresolved account codes: %s", company.name, sorted(unresolved))
        return False
    if missing_partners:
        _logger.warning(
            "begbal_detail: %s %s partner names not matched (lines posted without partner): %s",
            company.name,
            len(missing_partners),
            sorted(missing_partners),
        )
    if round(debit_total - credit_total, 2):
        _logger.error(
            "begbal_detail: %s does not balance: debit %.2f credit %.2f",
            company.name,
            debit_total,
            credit_total,
        )
        return False

    journal = _general_journal(env, company)
    if not journal:
        _logger.error("begbal_detail: no general journal for %s", company.name)
        return False

    old = Move.search([("ref", "=", OLD_REF), ("company_id", "=", company.id)])
    _logger.info(
        "begbal_detail: %s -> %s lines, debit %.2f; replaces %s (ids %s); journal %s",
        company.name,
        len(lines),
        debit_total,
        len(old),
        old.ids,
        journal.code,
    )
    if not REPLACE:
        _logger.info("begbal_detail: dry run, set BEGBAL_REPLACE=1 to apply")
        return True

    if old:
        old.filtered(lambda move: move.state == "posted").button_draft()
        old.unlink()

    move = Move.create(
        {
            "move_type": "entry",
            "journal_id": journal.id,
            "date": OPEN_DATE,
            "ref": NEW_REF,
            "line_ids": lines,
        }
    )
    move.action_post()
    _logger.info(
        "begbal_detail: posted %s move id=%s lines=%s total=%.2f",
        company.name,
        move.id,
        len(move.line_ids),
        move.amount_total,
    )
    return True


def main(env):
    resolve_partner = _partner_cache(env)
    ok = True
    for company_name, filename in COMPANIES:
        ok &= bool(_load_company(env, company_name, filename, resolve_partner))
    if ok and REPLACE:
        env.cr.commit()
        _logger.info("begbal_detail: committed")
    elif not ok:
        env.cr.rollback()
        _logger.error("begbal_detail: FAILED, rolled back")
    return ok


main(env)  # noqa: F821 -- `env` is provided by `odoo shell`
